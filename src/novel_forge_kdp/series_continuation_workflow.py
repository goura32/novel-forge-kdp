from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .models import ProjectState, VolumeProgress


class SeriesContinuationWorkflow:
    def __init__(
        self,
        *,
        status: Callable[[str], ProjectState],
        complete_volume: Callable[[str, int | None], ProjectState],
        write_volume: Callable[[str, int | None], ProjectState],
        series_dir_for: Callable[[str], Path],
        save_state: Callable[[Path, ProjectState], None],
        find_volume: Callable[[ProjectState, int], VolumeProgress | None],
        ensure_planned_volume_number: Callable[[ProjectState, int], None],
        ensure_volume_progress: Callable[[ProjectState, int], VolumeProgress],
    ) -> None:
        self.status = status
        self.complete_volume = complete_volume
        self.write_volume = write_volume
        self.series_dir_for = series_dir_for
        self.save_state = save_state
        self.find_volume = find_volume
        self.ensure_planned_volume_number = ensure_planned_volume_number
        self.ensure_volume_progress = ensure_volume_progress

    def continue_series(self, *, slug: str) -> ProjectState:
        state = self.status(slug)
        self.ensure_planned_volume_number(state, state.current_volume)
        current = self.find_volume(state, state.current_volume)
        if current is None or current.status != "revised":
            return self.complete_volume(slug, state.current_volume)

        next_number = state.current_volume + 1
        self.ensure_planned_volume_number(state, next_number)
        state.current_volume = next_number
        self.ensure_volume_progress(state, next_number)
        self.save_state(self.series_dir_for(slug), state)
        return self.write_volume(slug, next_number)
