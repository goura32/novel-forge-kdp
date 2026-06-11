from __future__ import annotations

from pathlib import Path

from .models import ProjectState, VolumeProgress, VolumeOutline


class OutlineSceneProcessor:
    """Outline chapters → scenes に対する scene processing の orchestrator."""

    def __init__(self, *, process_scene, save_state, chapter_manuscript_assembler):
        # process_scene keeps the same shape as NovelForge._process_scene.
        self.process_scene = process_scene
        self.save_state = save_state
        self.chapter_manuscript_assembler = chapter_manuscript_assembler

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
                    self.chapter_manuscript_assembler.write_chapter_markdown(volume_dir, chapter)
                    processed += 1
        return False


class OutlineSceneProcessorError(RuntimeError):
    pass
