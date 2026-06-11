from __future__ import annotations

import html
import json
import re
import zipfile
from pathlib import Path

from .paths import ensure_dir


class KdpExporter:
    def export(self, volume_dir: Path, title: str, manuscript: str) -> None:
        exports = ensure_dir(volume_dir / "exports")
        clean = manuscript.strip() + "\n"
        (exports / "manuscript.md").write_text(clean, encoding="utf-8")
        (exports / "kdp.txt").write_text(strip_markdown_heading_markers(clean).strip() + "\n", encoding="utf-8")
        (exports / "metadata.json").write_text(json.dumps({"title": title, "format": "KDP text/markdown/EPUB draft"}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_epub(exports / "book.epub", title, clean)
        write_export_chapters(exports, clean)


def strip_markdown_heading_markers(markdown: str) -> str:
    return re.sub(r"^#{1,6}\s+", "", markdown, flags=re.MULTILINE)


def chapter_heading_count(markdown: str) -> int:
    return len(re.findall(r"^##\s+.+$", markdown, re.MULTILINE))


def write_export_chapters(exports: Path, manuscript: str) -> None:
    chapter_root = ensure_dir(exports / "chapters")
    matches = list(re.finditer(r"^##\s+.+$", manuscript, re.MULTILINE))
    for old in chapter_root.glob("chapter_*.md"):
        old.unlink()
    for index, match in enumerate(matches, start=1):
        end = matches[index].start() if index < len(matches) else len(manuscript)
        chapter_text = manuscript[match.start():end].strip() + "\n"
        (chapter_root / f"chapter_{index:03d}.md").write_text(chapter_text, encoding="utf-8")


def write_epub(path: Path, title: str, manuscript: str) -> None:
    paragraphs = [p.strip() for p in manuscript.split("\n\n") if p.strip()]
    body = "\n".join(f"<p>{html.escape(p).replace(chr(10), '<br/>')}</p>" for p in paragraphs)
    chapter = f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ja">
<head><title>{html.escape(title)}</title></head>
<body>{body}</body>
</html>
'''
    nav = f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ja">
<head><title>{html.escape(title)}</title></head>
<body><nav epub:type="toc"><ol><li><a href="chapter.xhtml">{html.escape(title)}</a></li></ol></nav></body>
</html>
'''
    opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="ja">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="bookid">novel-forge-kdp</dc:identifier><dc:title>{html.escape(title)}</dc:title><dc:language>ja</dc:language></metadata>
  <manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="chapter"/></spine>
</package>
'''
    container = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>
'''
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/nav.xhtml", nav)
        zf.writestr("OEBPS/chapter.xhtml", chapter)
