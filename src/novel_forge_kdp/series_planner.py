from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .artifact_paths import SeriesPaths
from .models import ProjectState, SeriesPlan, VolumeProgress
from .paths import ensure_dir, safe_slug


class SeriesPlannerRepository(Protocol):
    def save_series_plan(self, series_dir: Path, data: dict) -> None: ...

    def save_state(self, series_dir: Path, state: ProjectState) -> None: ...


class SeriesTaskRunner(Protocol):
    def complete(self, task_name: str, **context) -> dict: ...


class SeriesPlanner:
    def __init__(
        self,
        *,
        task_runner: SeriesTaskRunner,
        repository: SeriesPlannerRepository,
        series_dir_for: Callable[[str], Path],
    ) -> None:
        self.task_runner = task_runner
        self.repository = repository
        self.series_dir_for = series_dir_for

    def plan(self, *, keyword: str) -> ProjectState:
        data = self.task_runner.complete("series_plan", keyword=keyword)
        data["slug"] = safe_slug(data.get("slug") or data.get("title") or keyword)
        series = SeriesPlan.model_validate(data)
        state = ProjectState(
            series=series,
            volumes=[VolumeProgress(number=v.number, title=v.title) for v in series.planned_volumes[:1]],
        )
        series_dir = self.series_dir_for(series.slug)
        ensure_dir(series_dir)
        ensure_dir(SeriesPaths(series_dir).raw_logs)
        self.repository.save_series_plan(series_dir, series.model_dump())
        self.repository.save_state(series_dir, state)
        return state
