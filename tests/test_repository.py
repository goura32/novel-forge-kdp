"""Tests for novel_forge_kdp.repository."""

import json

from novel_forge_kdp.models import (
    ProjectState,
    SeriesPlan,
    VolumeProgress,
)


def test_state_load_and_save(tmp_path):
    from novel_forge_kdp.repository import StateStore

    ss = StateStore()
    data = {"ok": True}
    path = tmp_path / "state.json"
    ss.save(path, data)
    loaded = ss.load(path)
    assert loaded == data


def test_state_load_missing_file_raises(tmp_path):
    from novel_forge_kdp.repository import StateStore

    ss = StateStore()
    path = tmp_path / "no_such_file.json"

    try:
        ss.load(path)
        raise AssertionError("should have raised")
    except FileNotFoundError:
        pass


def test_state_repo_load_and_save(tmp_path):
    from pathlib import Path
    from novel_forge_kdp.repository import StateRepository

    sdir = tmp_path / "series"
    sdir.mkdir()
    repo = StateRepository()

    try:
        repo.load_state(sdir)
        raise AssertionError("should have raised")
    except FileNotFoundError:
        pass


def test_state_repo_save_and_load(tmp_path):
    from pathlib import Path
    from novel_forge_kdp.repository import StateRepository

    sdir = tmp_path / "new-series"
    sdir.mkdir()
    repo = StateRepository()

    series = SeriesPlan(
        title="星屑の図書館",
        slug="hoshikuzu-library",
        logline="失われた物語を取り戻す司書の冒険。",
        genre="文学ファンタジー",
        target_audience="KDP読者",
        themes=["記憶", "再生"],
        selling_points=["謎解き", "成長"],
        world={"summary": "本が星になる都市。", "rules": ["禁書は夜に目覚める"]},
        main_characters=[{"name": "澪", "role": "司書", "arc": "孤独から連帯へ"}],
        planned_volumes=[
            {"number": 1, "title": "夜明けの禁書", "premise": "禁書を巡る第一巻。"}
        ],
    )
    state = ProjectState(
        series=series,
        volumes=[VolumeProgress(number=1, title="夜明けの禁書")],
    )

    repo.save_state(sdir, state)
    loaded = repo.load_state(sdir)
    assert loaded.series.title == "星屑の図書館"
    assert len(loaded.volumes) == 1
    assert loaded.current_volume == 1


def test_ensure_series_dir_and_raw_logs(tmp_path):
    from pathlib import Path
    from novel_forge_kdp.repository import StateRepository

    sdir = tmp_path / "new-series"
    assert not sdir.exists()
    repo = StateRepository()
    result = repo.ensure_series_dir(sdir)
    assert result == sdir
    assert sdir.exists()

    raw = sdir / "raw_logs"
    assert not raw.exists()
    raw_result = repo.ensure_raw_logs(sdir)
    assert raw_result == raw
    assert raw.exists()


def test_state_repo_loads_valid_json_into_ProjectState(tmp_path):
    from pathlib import Path
    from novel_forge_kdp.repository import StateRepository

    sdir = tmp_path / "series"
    sdir.mkdir()
    state_file = sdir / "state.json"

    repo = StateRepository()

    state_json = {
        "series": {
            "title": "テストシリーズ",
            "slug": "test-series",
            "logline": "テストレジライン",
            "genre": "テストジャンル",
            "target_audience": "テスト",
            "themes": ["テスト"],
            "selling_points": ["テスト"],
            "world": {"summary": "テスト", "rules": []},
            "main_characters": [{"name": "A", "role": "B", "arc": "C"}],
            "planned_volumes": [
                {"number": 1, "title": "第一巻", "premise": "D"}
            ],
        },
        "volumes": [
            {
                "number": 1,
                "title": "第一巻",
                "status": "drafted",
                "scenes": [],
            }
        ],
    }
    state_file.write_text(json.dumps(state_json), encoding="utf-8")

    loaded = repo.load_state(sdir)
    assert isinstance(loaded, ProjectState)
    assert loaded.series.title == "テストシリーズ"
    assert len(loaded.volumes) == 1
    assert loaded.current_volume == 1
