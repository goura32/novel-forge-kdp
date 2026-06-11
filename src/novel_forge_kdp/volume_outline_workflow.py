from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .artifact_paths import SeriesPaths
from .models import ProjectState, VolumeOutline, VolumeProgress


class VolumeOutlineRepository(Protocol):
    def save_volume_outline(self, volume_dir: Path, data: dict) -> None: ...


class VolumeOutlineTaskRunner(Protocol):
    def complete(self, task_name: str, **context) -> dict: ...


class VolumeOutlineWorkflow:
    def __init__(
        self,
        *,
        task_runner: VolumeOutlineTaskRunner,
        repository: VolumeOutlineRepository,
        validate_volume_outline: Callable[[VolumeOutline, int], None],
        sync_volume_scenes: Callable[[VolumeProgress, VolumeOutline], None],
        save_state: Callable[[Path, ProjectState], None],
    ) -> None:
        self.task_runner = task_runner
        self.repository = repository
        self.validate_volume_outline = validate_volume_outline
        self.sync_volume_scenes = sync_volume_scenes
        self.save_state = save_state

    def load_or_create(
        self,
        *,
        series_dir: Path,
        volume_dir: Path,
        state: ProjectState,
        volume: VolumeProgress,
        number: int,
    ) -> VolumeOutline:
        outline_path = SeriesPaths(series_dir).volume(number).outline
        if outline_path.exists():
            outline = VolumeOutline.model_validate_json(outline_path.read_text(encoding="utf-8"))
            self.validate_volume_outline(outline, number)
            self.sync_volume_scenes(volume, outline)
            return outline

        outline_data = self.task_runner.complete(
            "volume_outline",
            series=json.dumps(state.series.model_dump(), ensure_ascii=False),
            volume_number=number,
        )
        outline = VolumeOutline.model_validate(outline_data)
        self.validate_volume_outline(outline, number)
        self.repository.save_volume_outline(volume_dir, outline.model_dump())
        volume.status = "outlined"
        self.sync_volume_scenes(volume, outline)
        self.save_state(series_dir, state)
        return outline
