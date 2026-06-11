from pathlib import Path

from novel_forge_kdp.artifact_paths import SeriesPaths


def test_series_paths_builds_volume_and_scene_artifact_paths(tmp_path):
    paths = SeriesPaths(tmp_path / "series")
    volume = paths.volume(1)
    scene = volume.scene(2, 3)

    assert paths.state == tmp_path / "series" / "state.json"
    assert paths.series_plan == tmp_path / "series" / "series_plan.json"
    assert paths.raw_logs == tmp_path / "series" / "raw_logs"
    assert volume.root == tmp_path / "series" / "volume_001"
    assert volume.outline == volume.root / "outline.json"
    assert volume.revised_markdown == volume.root / "volume_revised.md"
    assert volume.exports == volume.root / "exports"
    assert scene.root == volume.root / "chapters" / "chapter_002"
    assert scene.draft == scene.root / "scene_003.draft.json"
    assert scene.review == scene.root / "scene_003.review.json"
    assert scene.revised == scene.root / "scene_003.revised.json"
    assert scene.markdown == scene.root / "scene_003.md"
    assert scene.chapter_markdown == scene.root / "chapter.md"
