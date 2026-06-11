from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ReviewVolume = Callable[[Path, Any, str], dict[str, Any]]
ReviseVolume = Callable[[Path, str, dict[str, Any], int], dict[str, Any]]
FinalReview = Callable[[Path, Path, Any, dict[str, Any], str], dict[str, Any]]
EnsurePublication = Callable[[Path, Any, Any, dict[str, Any], bool], None]
UpdateBible = Callable[[Path, str], None]
ExportKdp = Callable[[Path, str, str], None]
SaveState = Callable[[Path, Any], None]
SaveVolumeReview = Callable[[Path, dict[str, Any]], None]
SaveVolumeRevised = Callable[[Path, dict[str, Any]], None]


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
