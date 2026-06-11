from __future__ import annotations

from pathlib import Path

from .models import ChapterPlan
from .paths import ensure_dir


class ChapterManuscriptAssembler:
    """Writes chapter-level Markdown from revised scene Markdown files."""

    def write_chapter_markdown(self, volume_dir: Path, chapter: ChapterPlan) -> Path:
        chapter_dir = ensure_dir(volume_dir / "chapters" / f"chapter_{chapter.number:03d}")
        parts = [f"## {chapter.title}"]
        for scene in chapter.scenes:
            scene_md = chapter_dir / f"scene_{scene.number:03d}.md"
            if scene_md.exists():
                text = scene_md.read_text(encoding="utf-8").strip()
                if text:
                    parts.append(text)
        path = chapter_dir / "chapter.md"
        path.write_text("\n\n".join(parts).strip() + "\n", encoding="utf-8")
        return path
