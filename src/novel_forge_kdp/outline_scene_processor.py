from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .models import ProjectState, VolumeProgress, VolumeOutline


class OutlineSceneProcessor:
    """Outline chapters → scenes に対する scene processing の orchestrator."""

    def __init__(self, *, process_scene, save_state):
        # type signatures intentionally omitted for DI flexibility;
        # the two callables have the exact same shape as NovelForge._process_outline_scenes + _process_scene.
        self.process_scene = process_scene
        self.save_state = save_state

    def process(
        self,*,
        series_dir: Path,
        volume_dir: Path,
        state: ProjectState,
        outline: VolumeOutline,
        volume: VolumeProgress,
        max_scenes: int | None
    ) -> bool:
        """Run ``process_scene`` for every scene in the outline.

        Returns True when *max_scenes* was reached (partial progress saved), False when all scenes completed.
        """
        processed = 0
        for chapter in outline.chapters:
            for scene in chapter.scenes:
                if max_scenes is not None and processed >= max_scenes:
                    self.save_state(series_dir, state)
                    return True

                progress = next(
                    (s for s in volume.scenes if s.chapter == chapter.number and s.scene == scene.number),
                    None,
                )
                if progress is None:
                    continue

                revised_now = self.process_scene(series_dir, volume_dir, state, outline, chapter, scene, progress)
                if revised_now:
                    chapter_md_path = (volume_dir / "chapters" / f"chapter_{chapter.number:03d}" / "chapter.md")
                    from .paths import ensure_dir

                    chapter_dir = ensure_dir(chapter_md_path.parent)
                    parts = [f"## {chapter.title}"]
                    for sc in chapter.scenes:
                        scene_md = chapter_dir / f"scene_{sc.number:03d}.md"
                        if scene_md.exists():
                            text = scene_md.read_text(encoding="utf-8").strip()
                            if text:
                                parts.append(text)
                    (chapter_md_path).write_text("\n\n".join(parts).strip() + "\n", encoding="utf-8")

                if revised_now:
                    processed += 1
        return False


class OutlineSceneProcessorError(RuntimeError):
    pass