from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScenePaths:
    volume_root: Path
    chapter: int
    scene: int

    @property
    def root(self) -> Path:
        return self.volume_root / "chapters" / f"chapter_{self.chapter:03d}"

    @property
    def draft(self) -> Path:
        return self.root / f"scene_{self.scene:03d}.draft.json"

    @property
    def review(self) -> Path:
        return self.root / f"scene_{self.scene:03d}.review.json"

    @property
    def revised(self) -> Path:
        return self.root / f"scene_{self.scene:03d}.revised.json"

    @property
    def markdown(self) -> Path:
        return self.root / f"scene_{self.scene:03d}.md"

    @property
    def chapter_markdown(self) -> Path:
        return self.root / "chapter.md"


@dataclass(frozen=True)
class VolumePaths:
    series_root: Path
    number: int

    @property
    def root(self) -> Path:
        return self.series_root / f"volume_{self.number:03d}"

    @property
    def outline(self) -> Path:
        return self.root / "outline.json"

    @property
    def review(self) -> Path:
        return self.root / "volume_review.json"

    @property
    def final_review(self) -> Path:
        return self.root / "volume_review_final.json"

    @property
    def revised_json(self) -> Path:
        return self.root / "volume_revised.json"

    @property
    def revised_markdown(self) -> Path:
        return self.root / "volume_revised.md"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    def scene(self, chapter: int, scene: int) -> ScenePaths:
        return ScenePaths(self.root, chapter, scene)


@dataclass(frozen=True)
class SeriesPaths:
    root: Path

    @property
    def state(self) -> Path:
        return self.root / "state.json"

    @property
    def series_plan(self) -> Path:
        return self.root / "series_plan.json"

    @property
    def bible(self) -> Path:
        return self.root / "bible.json"

    @property
    def raw_logs(self) -> Path:
        return self.root / "raw_logs"

    def volume(self, number: int) -> VolumePaths:
        return VolumePaths(self.root, number)
