import json
import zipfile

from novel_forge_kdp.exporter import KdpExporter, chapter_heading_count


def test_kdp_exporter_writes_expected_draft_files(tmp_path):
    KdpExporter().export(tmp_path, "Title", "# Title\n\n## 第1章\n\n### Scene\n\n本文 #タグ\n")

    exports = tmp_path / "exports"
    assert (exports / "manuscript.md").read_text(encoding="utf-8").startswith("# Title")
    assert (exports / "kdp.txt").read_text(encoding="utf-8").splitlines() == ["Title", "", "第1章", "", "Scene", "", "本文 #タグ"]
    assert json.loads((exports / "metadata.json").read_text(encoding="utf-8"))["title"] == "Title"
    assert (exports / "chapters" / "chapter_001.md").read_text(encoding="utf-8").startswith("## 第1章")
    with zipfile.ZipFile(exports / "book.epub") as zf:
        assert set(zf.namelist()) == {"mimetype", "META-INF/container.xml", "OEBPS/content.opf", "OEBPS/nav.xhtml", "OEBPS/chapter.xhtml"}


def test_chapter_heading_count_counts_only_level_two_headings():
    assert chapter_heading_count("# Title\n\n## A\n\n### Scene\n\n## B\n") == 2
