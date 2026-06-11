from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .artifact_paths import SeriesPaths
from .models import ChapterPlan, ProjectState, VolumeOutline, VolumeProgress
from .paths import ensure_dir


class VolumeWritingWorkflow:
    def __init__(
        self,
        *,
        ensure_volume_progress: Callable[[ProjectState, int], VolumeProgress],
        load_or_create_outline: Callable[[Path, Path, ProjectState, VolumeProgress, int], VolumeOutline],
        process_outline_scenes: Callable[[Path, Path, ProjectState, VolumeProgress, VolumeOutline, int | None], bool],
        write_chapter_markdown: Callable[[Path, ChapterPlan], None],
        save_state: Callable[[Path, ProjectState], None],
    ) -> None:
        self.ensure_volume_progress = ensure_volume_progress
        self.load_or_create_outline = load_or_create_outline
        self.process_outline_scenes = process_outline_scenes
        self.write_chapter_markdown = write_chapter_markdown
        self.save_state = save_state

    def run(
        self,
        *,
        series_dir: Path,
        state: ProjectState,
        volume_number: int | None,
        max_scenes: int | None,
    ) -> ProjectState:
        number = volume_number or state.current_volume
        volume = self.ensure_volume_progress(state, number)
        volume_dir = ensure_dir(SeriesPaths(series_dir).volume(number).root)
        outline = self.load_or_create_outline(series_dir, volume_dir, state, volume, number)

        if self.process_outline_scenes(series_dir, volume_dir, state, volume, outline, max_scenes):
            return state
        for chapter in outline.chapters:
            self.write_chapter_markdown(volume_dir, chapter)
        volume.status = "drafted"
        self.save_state(series_dir, state)
        return state
