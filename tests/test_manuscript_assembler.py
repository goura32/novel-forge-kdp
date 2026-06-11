import pytest

from novel_forge_kdp.manuscript_assembler import ManuscriptAssembler, ManuscriptAssemblyError
from novel_forge_kdp.models import SceneProgress, VolumeProgress
from novel_forge_kdp.paths import PathSafetyError


def revised_scene(chapter, scene, path):
    return SceneProgress(chapter=chapter, scene=scene, title=f"Scene {chapter}-{scene}", status="revised", path=path)


def test_manuscript_assembler_orders_revised_scenes_and_joins_text(tmp_path):
    series_dir = tmp_path / "series"
    chapter_dir = series_dir / "volume_001" / "chapters" / "chapter_001"
    chapter_dir.mkdir(parents=True)
    first = chapter_dir / "scene_001.md"
    second = chapter_dir / "scene_002.md"
    first.write_text("# First\n\nA.\n", encoding="utf-8")
    second.write_text("# Second\n\nB.\n", encoding="utf-8")
    volume = VolumeProgress(
        number=1,
        title="Volume Title",
        scenes=[
            revised_scene(1, 2, str(second.relative_to(series_dir))),
            revised_scene(1, 1, str(first.relative_to(series_dir))),
        ],
    )

    manuscript = ManuscriptAssembler().assemble_volume(series_dir=series_dir, volume=volume)

    assert manuscript == "# Volume Title\n\n# First\n\nA.\n\n# Second\n\nB.\n"


def test_manuscript_assembler_rejects_unrevised_scene(tmp_path):
    volume = VolumeProgress(
        number=1,
        title="Volume Title",
        scenes=[SceneProgress(chapter=1, scene=1, title="Draft", status="drafted", path="scene.md")],
    )

    with pytest.raises(ManuscriptAssemblyError, match="scene is not revised"):
        ManuscriptAssembler().assemble_volume(series_dir=tmp_path, volume=volume)


def test_manuscript_assembler_rejects_paths_that_escape_series_dir(tmp_path):
    volume = VolumeProgress(number=1, title="Volume Title", scenes=[revised_scene(1, 1, "../escape.md")])

    with pytest.raises(PathSafetyError, match="escapes series directory"):
        ManuscriptAssembler().assemble_volume(series_dir=tmp_path, volume=volume)


def test_manuscript_assembler_rejects_missing_empty_and_absent_scene_paths(tmp_path):
    assembler = ManuscriptAssembler()
    series_dir = tmp_path / "series"
    series_dir.mkdir()
    empty = series_dir / "empty.md"
    empty.write_text("   \n", encoding="utf-8")

    with pytest.raises(ManuscriptAssemblyError, match="missing scene manuscript path"):
        assembler.assemble_volume(
            series_dir=series_dir,
            volume=VolumeProgress(number=1, title="V", scenes=[revised_scene(1, 1, None)]),
        )

    with pytest.raises(ManuscriptAssemblyError, match="missing scene manuscript"):
        assembler.assemble_volume(
            series_dir=series_dir,
            volume=VolumeProgress(number=1, title="V", scenes=[revised_scene(1, 1, "missing.md")]),
        )

    with pytest.raises(ManuscriptAssemblyError, match="empty scene manuscript"):
        assembler.assemble_volume(
            series_dir=series_dir,
            volume=VolumeProgress(number=1, title="V", scenes=[revised_scene(1, 1, "empty.md")]),
        )
