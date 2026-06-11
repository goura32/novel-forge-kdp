from novel_forge_kdp.chapter_manuscript_assembler import ChapterManuscriptAssembler
from novel_forge_kdp.models import ChapterPlan, ScenePlan


def scene(number: int, title: str = "Scene") -> ScenePlan:
    return ScenePlan(number=number, title=title, pov="澪", goal="g", conflict="c", outcome="o")


def test_chapter_manuscript_assembler_joins_existing_scene_markdown(tmp_path):
    volume_dir = tmp_path / "volume_001"
    chapter = ChapterPlan(number=1, title="第一章", purpose="導入", scenes=[scene(1), scene(2)])
    chapter_dir = volume_dir / "chapters" / "chapter_001"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "scene_001.md").write_text("# S1\n\n本文1\n", encoding="utf-8")
    (chapter_dir / "scene_002.md").write_text("# S2\n\n本文2\n", encoding="utf-8")

    path = ChapterManuscriptAssembler().write_chapter_markdown(volume_dir, chapter)

    assert path == chapter_dir / "chapter.md"
    assert path.read_text(encoding="utf-8") == "## 第一章\n\n# S1\n\n本文1\n\n# S2\n\n本文2\n"


def test_chapter_manuscript_assembler_skips_missing_or_empty_scene_markdown(tmp_path):
    volume_dir = tmp_path / "volume_001"
    chapter = ChapterPlan(number=2, title="第二章", purpose="転換", scenes=[scene(1), scene(2)])
    chapter_dir = volume_dir / "chapters" / "chapter_002"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "scene_001.md").write_text("   \n", encoding="utf-8")

    path = ChapterManuscriptAssembler().write_chapter_markdown(volume_dir, chapter)

    assert path.read_text(encoding="utf-8") == "## 第二章\n"
