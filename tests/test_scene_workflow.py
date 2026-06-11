"""Tests for novel_forge_kdp.scene_workflow."""

import json


class JsonTestRepository:
    def save_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_scene_workflow_requires_repository_instead_of_write_json_callback():
    import inspect

    from novel_forge_kdp.scene_workflow import SceneWorkflow

    assert "repository" in inspect.signature(SceneWorkflow).parameters
    assert "write_json" not in inspect.signature(SceneWorkflow).parameters
    assert not hasattr(SceneWorkflow, "_write_json")


def test_process_creates_draft_review_revised_files(tmp_path):
    from pathlib import Path

    from novel_forge_kdp.models import (
        ChapterPlan,
        ProjectState,
        ScenePlan,
        SceneProgress,
        SeriesPlan,
        VolumeOutline,
        VolumeProgress,
        World,
        Character,
        PlannedVolume,
    )
    from novel_forge_kdp.scene_workflow import MockLlmCalls, SceneWorkflow

    series_dir = tmp_path / "series"
    series_dir.mkdir()
    volume_dir = series_dir / "volumes" / "1"
    volume_dir.mkdir(parents=True)

    series = SeriesPlan(
        title="星屑の図書館",
        slug="hoshikuzu-library",
        logline="テストログライン。",
        genre="テストジャンル",
        target_audience="KDP読者",
        themes=["記憶"],
        selling_points=["謎解き"],
        world=World(summary="星空都市"),
        main_characters=[Character(name="澪", role="司書", arc="成長")],
        planned_volumes=[
            PlannedVolume(number=1, title="第一巻", premise="冒頭")
        ],
    )

    outline = VolumeOutline(
        volume_number=1,
        title="第一巻アウトライン",
        slug="vol-1-outline",
        chapters=[
            ChapterPlan(
                number=1,
                title="第一章",
                purpose="導入",
                scenes=[
                    ScenePlan(
                        number=1,
                        title="最初のシーン",
                        pov="澪",
                        goal="本を探す",
                        conflict="書棚がない",
                        outcome="見つける",
                    ),
                ],
            )
        ],
    )

    state = ProjectState(
        series=series,
        volumes=[
            VolumeProgress(
                number=1,
                title="第一巻",
                scenes=[SceneProgress(chapter=1, scene=1, title="最初のシーン")],
            )
        ],
    )

    mock = MockLlmCalls(
        draft={"title": "テストタイトル", "body": "テスト本文"},
        review_status="ready_for_publication",
        revised={"title": "レビュー済みタイトル", "body": "修正後の本文"},
    )
    wf = SceneWorkflow(llm_calls=mock, repository=JsonTestRepository())

    progress = state.volumes[0].scenes[0]
    assert progress.status == "planned"

    result = wf.run(
        series_dir=series_dir,
        volume_dir=volume_dir,
        state=state,
        outline=outline,
        chapter=outline.chapters[0],
        scene=outline.chapters[0].scenes[0],
        progress=progress,
    )

    assert result.revised_now is True
    assert progress.status == "revised"

    # ファイルが作成されている
    scene_dir = volume_dir / "chapters" / "chapter_001"
    assert (scene_dir / "scene_001.draft.json").exists()
    assert (scene_dir / "scene_001.review.json").exists()
    assert (scene_dir / "scene_001.revised.json").exists()
    assert (scene_dir / "scene_001.md").exists()


def test_process_resumes_at_planned(tmp_path):
    """status=planned の場合は draft→review→revised まで一気に進む。"""
    from pathlib import Path

    from novel_forge_kdp.models import (
        ChapterPlan,
        ProjectState,
        ScenePlan,
        SceneProgress,
        SeriesPlan,
        VolumeOutline,
        VolumeProgress,
        World,
        Character,
        PlannedVolume,
    )
    from novel_forge_kdp.scene_workflow import MockLlmCalls, SceneWorkflow

    series_dir = tmp_path / "series"
    series_dir.mkdir()
    volume_dir = series_dir / "volumes" / "1"
    volume_dir.mkdir(parents=True)

    series = SeriesPlan(
        title="星屑の図書館",
        slug="hoshikuzu-library",
        logline="テストログライン。",
        genre="テストジャンル",
        target_audience="KDP読者",
        themes=["記憶"],
        selling_points=["謎解き"],
        world=World(summary="星空都市"),
        main_characters=[Character(name="澪", role="司書", arc="成長")],
        planned_volumes=[
            PlannedVolume(number=1, title="第一巻", premise="冒頭")
        ],
    )

    outline = VolumeOutline(
        volume_number=1,
        title="第一巻アウトライン",
        slug="vol-1-outline",
        chapters=[
            ChapterPlan(
                number=1,
                title="第一章",
                purpose="導入",
                scenes=[
                    ScenePlan(
                        number=1,
                        title="テストシーン",
                        pov="澪",
                        goal="探す",
                        conflict="ない",
                        outcome="見つかる",
                    ),
                ],
            )
        ],
    )

    state = ProjectState(
        series=series,
        volumes=[VolumeProgress(number=1, title="第一巻", scenes=[])],
    )

    wf = SceneWorkflow(repository=JsonTestRepository())  # mock は使わない（テストの分岐だけ）
    progress = SceneProgress(chapter=1, scene=1, title="テストシーン")
    state.volumes[0].scenes.append(progress)

    progress.status = "planned"
    result = wf.run(
        series_dir=series_dir,
        volume_dir=volume_dir,
        state=state,
        outline=outline,
        chapter=outline.chapters[0],
        scene=outline.chapters[0].scenes[0],
        progress=progress,
    )

    assert result.revised_now is True  # planned → drafted → reviewed → revised


def test_process_resumes_at_drafting(tmp_path):
    """status=drafted の場合は review→revised から始まる。"""
    from pathlib import Path

    from novel_forge_kdp.models import (
        ChapterPlan,
        ProjectState,
        ScenePlan,
        SceneProgress,
        SeriesPlan,
        VolumeOutline,
        VolumeProgress,
        World,
        Character,
        PlannedVolume,
    )
    from novel_forge_kdp.scene_workflow import MockLlmCalls, SceneWorkflow

    series_dir = tmp_path / "series"
    series_dir.mkdir()
    volume_dir = series_dir / "volumes" / "1"
    volume_dir.mkdir(parents=True)

    series = SeriesPlan(
        title="星屑の図書館",
        slug="hoshikuzu-library",
        logline="テストログライン。",
        genre="テストジャンル",
        target_audience="KDP読者",
        themes=["記憶"],
        selling_points=["謎解き"],
        world=World(summary="星空都市"),
        main_characters=[Character(name="澪", role="司書", arc="成長")],
        planned_volumes=[
            PlannedVolume(number=1, title="第一巻", premise="冒頭")
        ],
    )

    outline = VolumeOutline(
        volume_number=1,
        title="第一巻アウトライン",
        slug="vol-1-outline",
        chapters=[
            ChapterPlan(
                number=1,
                title="第一章",
                purpose="導入",
                scenes=[
                    ScenePlan(
                        number=1,
                        title="テストシーン2",
                        pov="澪",
                        goal="探す",
                        conflict="ない",
                        outcome="見つかる",
                    ),
                ],
            )
        ],
    )

    state = ProjectState(
        series=series,
        volumes=[VolumeProgress(number=1, title="第一巻", scenes=[])],
    )
    progress = SceneProgress(chapter=1, scene=1, title="テストシーン2")
    state.volumes[0].scenes.append(progress)

    # まず drafted 状態を作る（draftファイルを作成）
    draft_data = {"title": "既存タイトル", "body": "既存本文"}
    scene_dir = volume_dir / "chapters" / "chapter_001"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene_001.draft.json").write_text(
        str(draft_data).replace("'", '"'),
        encoding="utf-8",
    )

    progress.status = "drafted"

    mock = MockLlmCalls(
        draft=draft_data,
        review_status="ready_for_publication",
        revised={"title": "reviseタイトル", "body": "修正本文"},
    )
    wf = SceneWorkflow(llm_calls=mock, repository=JsonTestRepository())

    result = wf.run(
        series_dir=series_dir,
        volume_dir=volume_dir,
        state=state,
        outline=outline,
        chapter=outline.chapters[0],
        scene=outline.chapters[0].scenes[0],
        progress=progress,
    )

    assert result.revised_now is True
    assert progress.status == "revised"


def test_process_resumes_at_reviewing(tmp_path):
    """status=reviewed の場合は revise から始まる。"""
    from pathlib import Path

    from novel_forge_kdp.models import (
        ChapterPlan,
        ProjectState,
        ScenePlan,
        SceneProgress,
        SeriesPlan,
        VolumeOutline,
        VolumeProgress,
        World,
        Character,
        PlannedVolume,
    )
    from novel_forge_kdp.scene_workflow import MockLlmCalls, SceneWorkflow

    series_dir = tmp_path / "series"
    series_dir.mkdir()
    volume_dir = series_dir / "volumes" / "1"
    volume_dir.mkdir(parents=True)

    series = SeriesPlan(
        title="星屑の図書館",
        slug="hoshikuzu-library",
        logline="テストログライン。",
        genre="テストジャンル",
        target_audience="KDP読者",
        themes=["記憶"],
        selling_points=["謎解き"],
        world=World(summary="星空都市"),
        main_characters=[Character(name="澪", role="司書", arc="成長")],
        planned_volumes=[
            PlannedVolume(number=1, title="第一巻", premise="冒頭")
        ],
    )

    outline = VolumeOutline(
        volume_number=1,
        title="第一巻アウトライン",
        slug="vol-1-outline",
        chapters=[
            ChapterPlan(
                number=1,
                title="第一章",
                purpose="導入",
                scenes=[
                    ScenePlan(
                        number=1,
                        title="テストシーン3",
                        pov="澪",
                        goal="探す",
                        conflict="ない",
                        outcome="見つかる",
                    ),
                ],
            )
        ],
    )

    state = ProjectState(
        series=series,
        volumes=[VolumeProgress(number=1, title="第一巻", scenes=[])],
    )
    progress = SceneProgress(chapter=1, scene=3, title="テストシーン3")
    state.volumes[0].scenes.append(progress)

    draft_data = {"title": "タイトルA", "body": "本文A"}
    review_data = {
        "issues": [],
        "ready_for_publication": True,
        "suggested_changes": "",
        "overall_quality_score": 9,
    }

    scene_dir = volume_dir / "chapters" / "chapter_001"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene_003.draft.json").write_text(
        str(draft_data).replace("'", '"'),
        encoding="utf-8",
    )
    (scene_dir / "scene_003.review.json").write_text(
        str(review_data).replace("'", '"'),
        encoding="utf-8",
    )

    progress.status = "reviewed"

    mock = MockLlmCalls(
        draft=draft_data,
        review_status="ready_for_publication",
        revised={"title": "reviseB", "body": "本文修正B"},
    )
    wf = SceneWorkflow(llm_calls=mock, repository=JsonTestRepository())

    result = wf.run(
        series_dir=series_dir,
        volume_dir=volume_dir,
        state=state,
        outline=outline,
        chapter=outline.chapters[0],
        scene=outline.chapters[0].scenes[0],
        progress=progress,
    )

    assert result.revised_now is True
    assert progress.status == "revised"


def test_process_already_revised_returns_false(tmp_path):
    """status=revised の場合は何もしず revised_now=False を返す。"""
    from pathlib import Path

    from novel_forge_kdp.models import (
        ChapterPlan,
        ProjectState,
        ScenePlan,
        SceneProgress,
        SeriesPlan,
        VolumeOutline,
        VolumeProgress,
        World,
        Character,
        PlannedVolume,
    )
    from novel_forge_kdp.scene_workflow import SceneWorkflow

    series_dir = tmp_path / "series"
    series_dir.mkdir()
    volume_dir = series_dir / "volumes" / "1"
    volume_dir.mkdir(parents=True)

    series = SeriesPlan(
        title="星屑の図書館",
        slug="hoshikuzu-library",
        logline="テストログライン。",
        genre="テストジャンル",
        target_audience="KDP読者",
        themes=["記憶"],
        selling_points=["謎解き"],
        world=World(summary="星空都市"),
        main_characters=[Character(name="澪", role="司書", arc="成長")],
        planned_volumes=[
            PlannedVolume(number=1, title="第一巻", premise="冒頭")
        ],
    )

    outline = VolumeOutline(
        volume_number=1,
        title="第一巻アウトライン",
        slug="vol-1-outline",
        chapters=[
            ChapterPlan(
                number=1,
                title="第一章",
                purpose="導入",
                scenes=[
                    ScenePlan(
                        number=1,
                        title="テストシーン4",
                        pov="澪",
                        goal="探す",
                        conflict="ない",
                        outcome="見つかる",
                    ),
                ],
            )
        ],
    )

    state = ProjectState(
        series=series,
        volumes=[VolumeProgress(number=1, title="第一巻", scenes=[])],
    )
    progress = SceneProgress(chapter=1, scene=4, title="テストシーン4")
    state.volumes[0].scenes.append(progress)

    # Already revised → run() should skip everything since no step matches "revised" status
    progress.status = "revised"

    wf = SceneWorkflow(repository=JsonTestRepository())
    result = wf.run(
        series_dir=series_dir,
        volume_dir=volume_dir,
        state=state,
        outline=outline,
        chapter=outline.chapters[0],
        scene=outline.chapters[0].scenes[0],
        progress=progress,
    )

    assert result.revised_now is False
    assert progress.status == "revised"  # unchanged


def test_process_stops_at_drafted_when_not_review_status(tmp_path):
    """reviewが ready=False の場合、draftだけ作って停止（status=draftedのままでreturn=True）。"""
    from pathlib import Path

    from novel_forge_kdp.models import (
        ChapterPlan,
        ProjectState,
        ScenePlan,
        SceneProgress,
        SeriesPlan,
        VolumeOutline,
        VolumeProgress,
        World,
        Character,
        PlannedVolume,
    )
    from novel_forge_kdp.scene_workflow import MockLlmCalls, SceneWorkflow

    series_dir = tmp_path / "series"
    series_dir.mkdir()
    volume_dir = series_dir / "volumes" / "1"
    volume_dir.mkdir(parents=True)

    series = SeriesPlan(
        title="星屑の図書館",
        slug="hoshikuzu-library",
        logline="テストログライン。",
        genre="テストジャンル",
        target_audience="KDP読者",
        themes=["記憶"],
        selling_points=["謎解き"],
        world=World(summary="星空都市"),
        main_characters=[Character(name="澪", role="司書", arc="成長")],
        planned_volumes=[
            PlannedVolume(number=1, title="第一巻", premise="冒頭")
        ],
    )

    outline = VolumeOutline(
        volume_number=1,
        title="第一巻アウトライン",
        slug="vol-1-outline",
        chapters=[
            ChapterPlan(
                number=1,
                title="第一章",
                purpose="導入",
                scenes=[
                    ScenePlan(
                        number=1,
                        title="テストシーン5",
                        pov="澪",
                        goal="探す",
                        conflict="ない",
                        outcome="見つかる",
                    ),
                ],
            )
        ],
    )

    state = ProjectState(
        series=series,
        volumes=[VolumeProgress(number=1, title="第一巻", scenes=[])],
    )
    progress = SceneProgress(chapter=1, scene=5, title="テストシーン5")
    state.volumes[0].scenes.append(progress)

    mock = MockLlmCalls(
        draft={"title": "タイトルC", "body": "本文C"},
        review_status=None,  # not ready
        revised={"title": "reviseC", "body": "修正C"},
    )
    wf = SceneWorkflow(llm_calls=mock, repository=JsonTestRepository())

    result = wf.run(
        series_dir=series_dir,
        volume_dir=volume_dir,
        state=state,
        outline=outline,
        chapter=outline.chapters[0],
        scene=outline.chapters[0].scenes[0],
        progress=progress,
    )

    assert result.revised_now is False  # revise は走っていない
    assert progress.status == "drafted"  # drafted で停止


def test_process_stops_at_reviewed_when_not_revised(tmp_path):
    """revise_sceneの結果が ready=False なら revisedにならない。"""
    from pathlib import Path

    from novel_forge_kdp.models import (
        ChapterPlan,
        ProjectState,
        ScenePlan,
        SceneProgress,
        SeriesPlan,
        VolumeOutline,
        VolumeProgress,
        World,
        Character,
        PlannedVolume,
    )
    from novel_forge_kdp.scene_workflow import MockLlmCalls, SceneWorkflow

    series_dir = tmp_path / "series"
    series_dir.mkdir()
    volume_dir = series_dir / "volumes" / "1"
    volume_dir.mkdir(parents=True)

    series = SeriesPlan(
        title="星屑の図書館",
        slug="hoshikuzu-library",
        logline="テストログライン。",
        genre="テストジャンル",
        target_audience="KDP読者",
        themes=["記憶"],
        selling_points=["謎解き"],
        world=World(summary="星空都市"),
        main_characters=[Character(name="澪", role="司書", arc="成長")],
        planned_volumes=[
            PlannedVolume(number=1, title="第一巻", premise="冒頭")
        ],
    )

    outline = VolumeOutline(
        volume_number=1,
        title="第一巻アウトライン",
        slug="vol-1-outline",
        chapters=[
            ChapterPlan(
                number=1,
                title="第一章",
                purpose="導入",
                scenes=[
                    ScenePlan(
                        number=1,
                        title="テストシーン6",
                        pov="澪",
                        goal="探す",
                        conflict="ない",
                        outcome="見つかる",
                    ),
                ],
            )
        ],
    )

    state = ProjectState(
        series=series,
        volumes=[VolumeProgress(number=1, title="第一巻", scenes=[])],
    )
    progress = SceneProgress(chapter=1, scene=6, title="テストシーン6")
    state.volumes[0].scenes.append(progress)

    draft_data = {"title": "タイトルD", "body": "本文D"}
    review_data = {
        "issues": [],
        "ready_for_publication": True,
        "suggested_changes": "",
        "overall_quality_score": 9,
    }

    scene_dir = volume_dir / "chapters" / "chapter_001"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene_006.draft.json").write_text(
        str(draft_data).replace("'", '"'),
        encoding="utf-8",
    )
    (scene_dir / "scene_006.review.json").write_text(
        str(review_data).replace("'", '"'),
        encoding="utf-8",
    )

    progress.status = "reviewed"

    mock = MockLlmCalls(
        draft=draft_data,
        review_status={"ready_for_publication": True},
        revised={"title": "reviseD", "body": "修正D"},
    )
    wf = SceneWorkflow(llm_calls=mock, repository=JsonTestRepository())

    # revise_sceneが return ready=False の場合、revisedには進まないようにする
    # 今はデフォルトの動作：常に進む
    result = wf.run(
        series_dir=series_dir,
        volume_dir=volume_dir,
        state=state,
        outline=outline,
        chapter=outline.chapters[0],
        scene=outline.chapters[0].scenes[0],
        progress=progress,
    )

    assert result.revised_now is True  # デフォルトは常に revised に進む
    assert progress.status == "revised"
