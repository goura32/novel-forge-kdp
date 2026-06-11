import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from novel_forge_kdp.llm import LLMClientError, parse_json_content
from novel_forge_kdp.schemas import load_schema
from novel_forge_kdp.paths import safe_slug
from novel_forge_kdp.prompts import PromptStore
from novel_forge_kdp.workflow import NovelForge


from tests.fakes import FakeLLM


class FourSceneLLM(FakeLLM):
    def complete_json(self, *, task, messages, schema, temperature=0.4, max_tokens=None):
        if task == "volume_outline":
            self.calls.append({"task": task, "messages": messages, "schema": schema})
            return {
                "volume_number": 1,
                "title": "夜明けの禁書",
                "chapters": [
                    {
                        "number": 1,
                        "title": "第一章",
                        "purpose": "導入",
                        "scenes": [
                            {"number": 1, "title": "一", "pov": "澪", "goal": "g", "conflict": "c", "outcome": "o"},
                            {"number": 2, "title": "二", "pov": "澪", "goal": "g", "conflict": "c", "outcome": "o"},
                        ],
                    },
                    {
                        "number": 2,
                        "title": "第二章",
                        "purpose": "転換",
                        "scenes": [
                            {"number": 1, "title": "三", "pov": "澪", "goal": "g", "conflict": "c", "outcome": "o"},
                            {"number": 2, "title": "四", "pov": "澪", "goal": "g", "conflict": "c", "outcome": "o"},
                        ],
                    },
                ],
            }
        return super().complete_json(task=task, messages=messages, schema=schema, temperature=temperature, max_tokens=max_tokens)


def revised_scene_keys(state):
    return [(scene.chapter, scene.scene) for scene in state.volumes[0].scenes if scene.status == "revised"]


def test_write_volume_max_scenes_counts_only_newly_processed_scenes_on_resume(tmp_path):
    llm = FourSceneLLM()
    forge = NovelForge(workspace=tmp_path, llm=llm)
    forge.plan_series("星 図書館")

    first = forge.write_volume("hoshikuzu-library", max_scenes=2)
    assert revised_scene_keys(first) == [(1, 1), (1, 2)]
    assert first.volumes[0].status == "outlined"

    second = forge.write_volume("hoshikuzu-library", max_scenes=1)
    assert revised_scene_keys(second) == [(1, 1), (1, 2), (2, 1)]
    assert second.volumes[0].status == "outlined"

    final = forge.write_volume("hoshikuzu-library")
    assert revised_scene_keys(final) == [(1, 1), (1, 2), (2, 1), (2, 2)]
    assert final.volumes[0].status == "drafted"


def test_safe_slug_normalizes_names():
    assert safe_slug(" 星屑の図書館!! KDP ") == "kdp"
    assert safe_slug("Novel Forge 01") == "novel-forge-01"
    assert safe_slug("   ") == "series"


def test_parse_json_content_accepts_plain_json_and_code_fences():
    assert parse_json_content('{"ok": true}') == {"ok": True}
    assert parse_json_content('```json\n{"ok": true}\n```') == {"ok": True}
    with pytest.raises(LLMClientError):
        parse_json_content('not json')


def test_prompt_store_renders_markdown_templates(tmp_path):
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "demo.md").write_text("# Demo\nKeyword: {{ keyword }}", encoding="utf-8")
    store = PromptStore(prompts)
    assert "Keyword: 魔法" in store.render("demo", keyword="魔法")


def test_generation_schemas_bound_production_workload():
    series_schema = load_schema("series_plan")
    volume_schema = load_schema("volume_outline")
    assert series_schema["properties"]["planned_volumes"]["maxItems"] == 3
    assert volume_schema["properties"]["chapters"]["maxItems"] == 2
    assert volume_schema["properties"]["chapters"]["items"]["properties"]["scenes"]["maxItems"] == 2

    too_many_chapters = {
        "volume_number": 1,
        "title": "Too Long",
        "chapters": [
            {"number": i, "title": f"Chapter {i}", "purpose": "p", "scenes": [{"number": 1, "title": "S", "pov": "p", "goal": "g", "conflict": "c", "outcome": "o"}]}
            for i in range(1, 6)
        ],
    }
    assert list(Draft202012Validator(volume_schema).iter_errors(too_many_chapters))


def test_new_series_creates_resumeable_scene_workflow(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM(planned_volume_count=2))
    state = forge.plan_series("星 図書館")
    assert state.series.title == "星屑の図書館"
    assert (tmp_path / "hoshikuzu-library" / "state.json").exists()
    assert (tmp_path / "hoshikuzu-library" / "raw_logs").is_dir()

    state = forge.write_volume("hoshikuzu-library")
    volume_dir = tmp_path / "hoshikuzu-library" / "volume_001"
    assert (volume_dir / "outline.json").exists()
    assert (volume_dir / "chapters" / "chapter_001" / "scene_001.md").read_text(encoding="utf-8").startswith("# 禁書の囁き")
    chapter_md = (volume_dir / "chapters" / "chapter_001" / "chapter.md").read_text(encoding="utf-8")
    assert chapter_md.startswith("## 星の降る閲覧室")
    assert "# 禁書の囁き" in chapter_md
    assert state.volumes[0].status == "drafted"

    loaded = forge.status("hoshikuzu-library")
    assert loaded.volumes[0].scenes[0].status == "revised"


def test_complete_volume_reviews_revises_exports_and_updates_bible(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM(planned_volume_count=2))
    forge.plan_series("星 図書館")
    forge.write_volume("hoshikuzu-library")

    state = forge.complete_volume("hoshikuzu-library")
    series_dir = tmp_path / "hoshikuzu-library"
    volume_dir = series_dir / "volume_001"

    assert state.volumes[0].status == "revised"
    assert (volume_dir / "volume_review.json").exists()
    assert (volume_dir / "volume_revised.md").read_text(encoding="utf-8").startswith("# 夜明けの禁書")
    assert (volume_dir / "exports" / "manuscript.md").exists()
    assert (volume_dir / "exports" / "kdp.txt").read_text(encoding="utf-8").startswith("夜明けの禁書")
    assert (volume_dir / "exports" / "book.epub").read_bytes().startswith(b"PK")
    exported_chapter = (volume_dir / "exports" / "chapters" / "chapter_001.md").read_text(encoding="utf-8")
    assert exported_chapter.startswith("## 星の降る閲覧室")
    assert "# 禁書の囁き" in exported_chapter
    bible = json.loads((series_dir / "bible.json").read_text(encoding="utf-8"))
    assert bible["characters"][0]["name"] == "澪"


def test_continue_series_revises_unfinished_or_starts_next_volume(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM(planned_volume_count=2))
    forge.plan_series("星 図書館")
    first = forge.continue_series("hoshikuzu-library")
    assert first.volumes[0].status == "revised"

    second = forge.continue_series("hoshikuzu-library")
    assert second.current_volume == 2
    assert any(v.number == 2 for v in second.volumes)
    assert (tmp_path / "hoshikuzu-library" / "volume_002" / "outline.json").exists()



def test_load_or_create_outline_delegates_to_volume_outline_workflow(tmp_path, monkeypatch):
    import novel_forge_kdp.workflow as workflow_module

    calls = []

    class SpyVolumeOutlineWorkflow:
        def __init__(self, **kwargs):
            calls.append(("init", sorted(kwargs.keys())))

        def load_or_create(self, *, series_dir, volume_dir, state, volume, number):
            calls.append(("load_or_create", series_dir.name, volume_dir.name, number))
            return workflow_module.VolumeOutline(
                volume_number=number,
                title="Spy Outline",
                chapters=[
                    workflow_module.ChapterPlan(
                        number=1,
                        title="Spy Chapter",
                        purpose="verify delegation",
                        scenes=[workflow_module.ScenePlan(number=1, title="Spy Scene", pov="澪", goal="g", conflict="c", outcome="o")],
                    )
                ],
            )

    monkeypatch.setattr(workflow_module, "VolumeOutlineWorkflow", SpyVolumeOutlineWorkflow, raising=False)

    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    state = forge.plan_series("星 図書館")
    volume = state.volumes[0]
    series_dir = tmp_path / "hoshikuzu-library"
    volume_dir = series_dir / "volume_001"

    outline = forge._load_or_create_outline(series_dir, volume_dir, state, volume, 1)

    assert outline.title == "Spy Outline"
    assert calls[0][0] == "init"
    assert calls[0][1] == ["repository", "save_state", "sync_volume_scenes", "task_runner", "validate_volume_outline"]
    assert calls[1] == ("load_or_create", "hoshikuzu-library", "volume_001", 1)


def test_write_volume_delegates_to_volume_writing_workflow(tmp_path, monkeypatch):
    import novel_forge_kdp.workflow as workflow_module

    calls = []

    class SpyVolumeWritingWorkflow:
        def __init__(self, **kwargs):
            calls.append(("init", sorted(kwargs.keys())))

        def run(self, *, series_dir, state, volume_number, max_scenes):
            calls.append(("run", series_dir.name, volume_number, max_scenes))
            state.volumes[0].status = "drafted"
            return state

    monkeypatch.setattr(workflow_module, "VolumeWritingWorkflow", SpyVolumeWritingWorkflow, raising=False)

    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    forge.plan_series("星 図書館")
    state = forge.write_volume("hoshikuzu-library", volume_number=1, max_scenes=2)

    assert state.volumes[0].status == "drafted"
    assert calls[0][0] == "init"
    assert calls[0][1] == [
        "ensure_volume_progress",
        "load_or_create_outline",
        "outline_scene_processor",
        "save_state",
        "write_chapter_markdown",
    ]
    assert calls[1] == ("run", "hoshikuzu-library", 1, 2)



def test_write_volume_process_scene_delegates_to_scene_workflow(tmp_path, monkeypatch):
    import novel_forge_kdp.workflow as workflow_module

    calls = []

    class SpySceneWorkflow:
        def __init__(self, *args, **kwargs):
            calls.append(("init", args, kwargs))

        def run(self, *, series_dir, volume_dir, state, outline, chapter, scene, progress):
            calls.append(("run", chapter.number, scene.number, progress.status))
            scene_dir = volume_dir / "chapters" / f"chapter_{chapter.number:03d}"
            scene_dir.mkdir(parents=True, exist_ok=True)
            scene_md = scene_dir / f"scene_{scene.number:03d}.md"
            scene_md.write_text("# Spy Scene\n\nBody from spy.\n", encoding="utf-8")
            progress.status = "revised"
            progress.path = str(scene_md.relative_to(series_dir))
            return workflow_module.SceneResult(revised_now=True)

    monkeypatch.setattr(workflow_module, "SceneWorkflow", SpySceneWorkflow, raising=False)

    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    forge.plan_series("星 図書館")
    state = forge.write_volume("hoshikuzu-library", max_scenes=1)

    assert calls[0][0] == "init"
    assert calls[1] == ("run", 1, 1, "planned")
    assert state.volumes[0].scenes[0].status == "revised"
    assert (tmp_path / "hoshikuzu-library" / "volume_001" / "chapters" / "chapter_001" / "scene_001.md").read_text(encoding="utf-8").startswith("# Spy Scene")


def test_plan_series_saves_state_through_state_repository(tmp_path, monkeypatch):
    import novel_forge_kdp.workflow as workflow_module

    calls = []

    class SpyRepository:
        def __init__(self):
            calls.append(("init",))

        def load_state(self, series_dir):
            raise FileNotFoundError(series_dir)

        def save_series_plan(self, series_dir, data):
            calls.append(("save_series_plan", series_dir.name, data["slug"]))
            (series_dir / "series_plan.json").write_text(json.dumps(data), encoding="utf-8")

        def save_state(self, series_dir, state):
            calls.append(("save_state", series_dir.name, state.series.slug))
            (series_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")

    monkeypatch.setattr(workflow_module, "ProjectRepository", SpyRepository, raising=False)

    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    state = forge.plan_series("星 図書館")

    assert state.series.slug == "hoshikuzu-library"
    assert calls == [
        ("init",),
        ("save_series_plan", "hoshikuzu-library", "hoshikuzu-library"),
        ("save_state", "hoshikuzu-library", "hoshikuzu-library"),
    ]


def test_plan_series_delegates_to_series_planner(tmp_path, monkeypatch):
    import novel_forge_kdp.workflow as workflow_module

    calls = []

    class SpySeriesPlanner:
        def __init__(self, **kwargs):
            calls.append(("init", sorted(kwargs.keys())))

        def plan(self, *, keyword):
            calls.append(("plan", keyword))
            data = FakeLLM().complete_json(task="series_plan", messages=[], schema={})
            series = workflow_module.SeriesPlan.model_validate(data)
            return workflow_module.ProjectState(
                series=series,
                volumes=[workflow_module.VolumeProgress(number=1, title=series.planned_volumes[0].title)],
            )

    monkeypatch.setattr(workflow_module, "SeriesPlanner", SpySeriesPlanner, raising=False)

    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    state = forge.plan_series("星 図書館")

    assert state.series.slug == "hoshikuzu-library"
    assert calls[0][0] == "init"
    assert calls[0][1] == ["repository", "series_dir_for", "task_runner"]
    assert calls[1] == ("plan", "星 図書館")


def test_status_loads_state_through_state_repository(tmp_path, monkeypatch):
    import novel_forge_kdp.workflow as workflow_module

    calls = []

    class SpyRepository:
        def __init__(self):
            calls.append(("init",))

        def load_state(self, series_dir):
            calls.append(("load_state", series_dir.name))
            return "LOADED_STATE"

        def save_state(self, series_dir, state):
            calls.append(("save_state", series_dir.name))

    monkeypatch.setattr(workflow_module, "ProjectRepository", SpyRepository, raising=False)
    series_dir = tmp_path / "hoshikuzu-library"
    series_dir.mkdir()

    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())

    assert forge.status("hoshikuzu-library") == "LOADED_STATE"
    assert calls == [("init",), ("load_state", "hoshikuzu-library")]



def test_plan_series_and_outline_use_task_runner(tmp_path, monkeypatch):
    calls = []
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())

    class Runner:
        def complete(self, task_name, **context):
            calls.append((task_name, context))
            if task_name == "series_plan":
                return FakeLLM().complete_json(task="series_plan", messages=[], schema={})
            if task_name == "volume_outline":
                return FakeLLM().complete_json(task="volume_outline", messages=[{"content": f"対象巻: {context['volume_number']}"}], schema={})
            raise AssertionError(task_name)

    monkeypatch.setattr(forge, "_task_runner_for", lambda series_dir=None: Runner())

    forge.plan_series("星 図書館")
    forge.write_volume("hoshikuzu-library", max_scenes=0)

    assert calls[0] == ("series_plan", {"keyword": "星 図書館"})
    assert calls[1][0] == "volume_outline"
    assert calls[1][1]["volume_number"] == 1
    assert "series" in calls[1][1]



def test_complete_volume_uses_task_runner_for_volume_review_revise_and_bible(tmp_path, monkeypatch):
    calls = []
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    forge.plan_series("星 図書館")
    forge.write_volume("hoshikuzu-library")

    class Runner:
        def complete(self, task_name, **context):
            calls.append((task_name, context))
            if task_name == "volume_review":
                return FakeLLM().complete_json(task="volume_review", messages=[], schema={})
            if task_name == "revise_volume":
                return FakeLLM().complete_json(task="revise_volume", messages=[], schema={})
            if task_name == "bible_update":
                return FakeLLM().complete_json(task="bible_update", messages=[], schema={})
            raise AssertionError(task_name)

    monkeypatch.setattr(forge, "_task_runner_for", lambda series_dir=None: Runner())

    forge.complete_volume("hoshikuzu-library")

    task_names = [name for name, _ in calls]
    assert task_names == ["volume_review", "revise_volume", "bible_update"]
    assert "series" in calls[0][1]
    assert "manuscript" in calls[0][1]
    assert calls[1][1]["chapter_count"] == 1
    assert "existing_bible" in calls[2][1]



def test_continue_series_delegates_to_series_continuation_workflow(tmp_path, monkeypatch):
    import novel_forge_kdp.workflow as workflow_module

    calls = []

    class SpySeriesContinuationWorkflow:
        def __init__(self, **kwargs):
            calls.append(("init", sorted(kwargs.keys())))

        def continue_series(self, *, slug):
            calls.append(("continue_series", slug))
            state = workflow_module.ProjectState(
                series=workflow_module.SeriesPlan.model_validate(FakeLLM().complete_json(task="series_plan", messages=[], schema={})),
                volumes=[],
            )
            state.series.slug = slug
            return state

    monkeypatch.setattr(workflow_module, "SeriesContinuationWorkflow", SpySeriesContinuationWorkflow, raising=False)

    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    state = forge.continue_series("hoshikuzu-library")

    assert state.series.slug == "hoshikuzu-library"
    assert calls[0][0] == "init"
    assert calls[0][1] == [
        "complete_volume",
        "ensure_planned_volume_number",
        "ensure_volume_progress",
        "find_volume",
        "save_state",
        "series_dir_for",
        "status",
        "write_volume",
    ]
    assert calls[1] == ("continue_series", "hoshikuzu-library")


def test_process_outline_scenes_delegates_to_outline_scene_processor(tmp_path, monkeypatch):
    import novel_forge_kdp.workflow as workflow_module

    calls = []

    class SpyOutlineSceneProcessor:
        def __init__(self, **kwargs):
            calls.append(("init", sorted(kwargs.keys())))

        def process(self, *, series_dir, volume_dir, state, outline, volume, max_scenes):
            calls.append(
                (
                    "process",
                    series_dir.name,
                    len(outline.chapters),
                    volume.number,
                    max_scenes,
                )
            )
            return False

    monkeypatch.setattr(workflow_module, "OutlineSceneProcessor", SpyOutlineSceneProcessor, raising=False)

    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    state = forge.plan_series("星 図書館")
    volume_dir = tmp_path / "hoshikuzu-library" / "volume_001"
    volume_dir.mkdir(parents=True)
    outline_data = FakeLLM().complete_json(task="volume_outline", messages=[], schema={})
    outline = workflow_module.VolumeOutline.model_validate(outline_data)

    result = forge._process_outline_scenes(
        tmp_path / "hoshikuzu-library", volume_dir, state, state.volumes[0], outline, max_scenes=1
    )

    assert result is False
    assert calls[0][0] == "init"
    assert calls[0][1] == ["process_scene", "save_state"]
    assert calls[1] == ("process", "hoshikuzu-library", len(outline.chapters), 1, 1)


def test_write_volume_injects_outline_scene_processor_into_volume_writing_workflow(tmp_path, monkeypatch):
    """write_volume は OutlineSceneProcessor を VolumeWritingWorkflow に注入するべき"""
    import novel_forge_kdp.workflow as workflow_module

    calls = []

    class SpyOutlineSceneProcessor:
        def __init__(self, **kwargs):
            calls.append(("__init__", sorted(kwargs.keys())))

        def process(self, *, series_dir, volume_dir, state, outline, volume, max_scenes):
            calls.append(("process", series_dir.name))
            return False

    monkeypatch.setattr(workflow_module, "OutlineSceneProcessor", SpyOutlineSceneProcessor, raising=False)

    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    forge.plan_series("星 図書館")
    forge.write_volume("hoshikuzu-library")

    assert any(c[0] == "__init__" for c in calls), \
        "write_volume should inject OutlineSceneProcessor, not a raw process callback"


def test_safe_series_file_delegates_to_manuscript_assembler(tmp_path, monkeypatch):
    import novel_forge_kdp.workflow as workflow_module

    calls = []

    class SpyManuscriptAssembler:
        def safe_series_file(self, series_dir, relative_path):
            calls.append((series_dir.name, relative_path))
            return series_dir / "safe.md"

    monkeypatch.setattr(workflow_module, "ManuscriptAssembler", SpyManuscriptAssembler, raising=False)

    result = NovelForge._safe_series_file(tmp_path / "series", "scene.md")

    assert result == tmp_path / "series" / "safe.md"
    assert calls == [("series", "scene.md")]


def test_assemble_volume_manuscript_delegates_to_manuscript_assembler(tmp_path, monkeypatch):
    import novel_forge_kdp.workflow as workflow_module

    calls = []

    class SpyManuscriptAssembler:
        def assemble_volume(self, *, series_dir, volume):
            calls.append(("assemble_volume", series_dir.name, volume.number))
            return "# Spy Manuscript\n\nBody.\n"

    monkeypatch.setattr(workflow_module, "ManuscriptAssembler", SpyManuscriptAssembler, raising=False)

    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    state = forge.plan_series("星 図書館")
    manuscript = forge._assemble_volume_manuscript(tmp_path / "hoshikuzu-library", state.volumes[0])

    assert manuscript == "# Spy Manuscript\n\nBody.\n"
    assert calls == [("assemble_volume", "hoshikuzu-library", 1)]


def test_complete_volume_delegates_to_volume_completion_workflow(tmp_path, monkeypatch):
    import novel_forge_kdp.workflow as workflow_module

    calls = []

    class SpyCompletionWorkflow:
        def __init__(self, **kwargs):
            calls.append(("init", sorted(kwargs.keys())))

        def run(self, *, series_dir, volume_dir, state, volume, outline, manuscript, force):
            calls.append(("run", series_dir.name, volume_dir.name, volume.number, outline.volume_number, force))
            volume.status = "revised"
            return state

    monkeypatch.setattr(workflow_module, "VolumeCompletionWorkflow", SpyCompletionWorkflow, raising=False)

    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    forge.plan_series("星 図書館")
    forge.write_volume("hoshikuzu-library")

    state = forge.complete_volume("hoshikuzu-library", force=True)

    assert state.volumes[0].status == "revised"
    assert calls[0][0] == "init"
    assert calls[1] == ("run", "hoshikuzu-library", "volume_001", 1, 1, True)
