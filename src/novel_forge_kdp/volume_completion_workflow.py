from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .artifact_paths import SeriesPaths
from .quality import QualityGate, QualityGateError

ReviewVolume = Callable[[Path, Any, str], dict[str, Any]]
ReviseVolume = Callable[[Path, str, dict[str, Any], int], dict[str, Any]]
FinalReview = Callable[[Path, Path, Any, dict[str, Any], str], dict[str, Any]]
EnsurePublication = Callable[[Path, Any, Any, dict[str, Any], bool], None]
UpdateBible = Callable[[Path, str], None]
ExportKdp = Callable[[Path, str, str], None]
SaveState = Callable[[Path, Any], None]
SaveVolumeReview = Callable[[Path, dict[str, Any]], None]
SaveVolumeRevised = Callable[[Path, dict[str, Any]], None]


class VolumeCompletionLlmCallsError(RuntimeError):
    pass


@dataclass(frozen=True)
class VolumeCompletionLlmCalls:
    """Production LLM calls for volume review, revision, and bible update."""

    runner: Any
    repository: Any

    def review_volume(self, series_dir: Path, state: Any, manuscript: str) -> dict[str, Any]:
        return self.runner.complete(
            "volume_review",
            series=state.series.model_dump_json(),
            manuscript=manuscript,
        )

    def revise_volume(self, series_dir: Path, manuscript: str, review: dict[str, Any], expected_chapter_count: int) -> dict[str, Any]:
        revised = self.runner.complete(
            "revise_volume",
            manuscript=manuscript,
            review=json.dumps(review, ensure_ascii=False),
            chapter_count=expected_chapter_count,
        )
        try:
            QualityGate().ensure_revised_volume_structure(revised["body"], expected_chapter_count)
        except QualityGateError as exc:
            raise VolumeCompletionLlmCallsError(str(exc)) from exc
        return revised

    def final_review_if_needed(self, series_dir: Path, volume_dir: Path, state: Any, review: dict[str, Any], revised_md: str) -> dict[str, Any]:
        if review.get("ready_for_publication", False):
            return review
        final_review = self.review_volume(series_dir, state, revised_md)
        self.repository.save_volume_review(volume_dir, final_review, final=True)
        return final_review

    def update_bible(self, series_dir: Path, manuscript: str) -> None:
        bible_path = SeriesPaths(series_dir).bible
        existing = bible_path.read_text(encoding="utf-8") if bible_path.exists() else "{}"
        bible = self.runner.complete(
            "bible_update",
            existing_bible=existing,
            manuscript=manuscript,
        )
        self.repository.save_bible(series_dir, bible)


@dataclass(frozen=True)
class VolumeCompletionWorkflow:
    """Completes a volume from revised scenes to KDP export."""

    review_volume: ReviewVolume
    revise_volume: ReviseVolume
    final_review_if_needed: FinalReview
    ensure_publication_allowed: EnsurePublication
    update_bible: UpdateBible
    export_kdp: ExportKdp
    save_state: SaveState
    save_volume_review: SaveVolumeReview
    save_volume_revised: SaveVolumeRevised

    def run(
        self,
        *,
        series_dir: Path,
        volume_dir: Path,
        state: Any,
        volume: Any,
        outline: Any,
        manuscript: str,
        force: bool,
    ) -> Any:
        review = self.review_volume(series_dir, state, manuscript)
        self.save_volume_review(volume_dir, review)

        revised = self.revise_volume(series_dir, manuscript, review, len(outline.chapters))
        self.save_volume_revised(volume_dir, revised)

        volume.title = revised["title"]
        revised_md = f"# {revised['title']}\n\n{revised['body'].strip()}\n"
        (volume_dir / "volume_revised.md").write_text(revised_md, encoding="utf-8")

        final_review = self.final_review_if_needed(series_dir, volume_dir, state, review, revised_md)
        self.ensure_publication_allowed(series_dir, state, volume, final_review, force)

        self.update_bible(series_dir, revised_md)
        self.export_kdp(volume_dir, revised["title"], revised_md)
        volume.status = "revised"
        self.save_state(series_dir, state)
        return state
