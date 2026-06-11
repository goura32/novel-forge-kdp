from __future__ import annotations

from typing import Any

from .exporter import chapter_heading_count


class QualityGateError(RuntimeError):
    pass


class QualityGate:
    def ensure_revised_volume_structure(self, body: str, expected_chapter_count: int) -> None:
        heading_count = chapter_heading_count(body)
        if heading_count < 1:
            raise QualityGateError("revised volume has no chapter headings: expected at least one '## ' chapter heading")
        if heading_count != expected_chapter_count:
            raise QualityGateError(f"revised volume chapter count mismatch: expected={expected_chapter_count} actual={heading_count}")

    def ensure_export_allowed(self, review: dict[str, Any], *, force: bool = False) -> None:
        if force:
            return
        if not review.get("ready_for_publication", False):
            raise QualityGateError("volume review says not ready for publication after revision; revised draft saved, rerun with force=True to export anyway")
        if review_has_blocking_issues(review):
            raise QualityGateError("volume review has major final review issues; revised draft saved, rerun with force=True to export anyway")


def review_has_blocking_issues(review: dict[str, Any]) -> bool:
    return any(str(issue.get("severity", "")).lower() in {"major", "critical", "blocker"} for issue in review.get("issues", []) if isinstance(issue, dict))
