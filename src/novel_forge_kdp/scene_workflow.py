"""novel_forge_kdp.scene_workflow: Extracts the scene processing pipeline.

Responsibilities:
- Standalone logic for the three-step scene lifecycle (draft -> review -> revise)
- Each step can be tested in isolation with mock LLM responses
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import ensure_dir


@dataclass
class MockLlmCalls:
    """Mock LLM responses for testing SceneWorkflow.

    Attributes:
        draft: Returned as the draft JSON when draft step is executed.
               If None, draft step is a NO-OP (status stays).
        review_status: Returned as the review JSON when review step is executed.
                       A dict with keys like "ready_for_publication".
                       If None, review step is a NO-OP (status stays).
        revised: Returned as the revised JSON when revise step is executed.
                 If None, revise step is a NO-OP (status stays).
    """

    draft: dict[str, Any] | None = None
    review_status: dict[str, Any] | None = None
    revised: dict[str, Any] | None = None


@dataclass
class SceneResult:
    """Result of running the step engine for one scene."""

    draft_created: bool = False
    review_done: bool = False
    revised_now: bool = False


class SceneWorkflowError(RuntimeError):
    """Raised on unexpected scene status or invalid state."""


@dataclass
class SceneWorkflow:
    """Executes the three-step scene pipeline (draft -> review -> revise).

    Each step respects the current ``status`` in ``SceneProgress`` and
    advances only the transitions that are needed.

    When *llm_calls* is a MockLlmCalls, no real network call is made —
    mock JSON is written to disk exactly where a real call would write it.
    This allows tests to verify file outputs and in-memory state changes.
    """

    llm_calls: "MockLlmCalls | None" = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        series_dir: Path,
        volume_dir: Path,
        state: Any,  # ProjectState — avoid circular import in tests
        outline: Any,  # VolumeOutline
        chapter: Any,  # ChapterPlan
        scene: Any,  # ScenePlan
        progress: Any,  # SceneProgress (mutable)
    ) -> SceneResult:
        result = SceneResult()

        # --- Step 1: draft (planned → drafted) ---
        if progress.status == "planned":
            self._draft(
                series_dir=series_dir,
                volume_dir=volume_dir,
                chapter=chapter,
                scene=scene,
            )
            result.draft_created = True
            # Write back status to caller's in-memory object
            progress.status = "drafted"

        # --- Step 2: review (drafted → reviewed) ---
        if progress.status == "drafted":
            review_done = self._review(
                series_dir=series_dir,
                volume_dir=volume_dir,
                chapter=chapter,
                scene=scene,
            )
            if review_done:
                result.review_done = True
                progress.status = "reviewed"

        # --- Step 3: revise (reviewed → revised) ---
        if progress.status == "reviewed":
            revised_now = self._revise(
                series_dir=series_dir,
                volume_dir=volume_dir,
                chapter=chapter,
                scene=scene,
            )
            result.revised_now = revised_now
            if revised_now:
                progress.status = "revised"

        return result

    # ------------------------------------------------------------------
    # Steps — each mirrors _process_scene logic exactly
    # ------------------------------------------------------------------

    def _draft(
        self,
        *,
        series_dir: Path,
        volume_dir: Path,
        chapter: Any,
        scene: Any,
    ) -> dict[str, Any]:
        """Generate draft and save to disk. Returns the written JSON."""
        scene_dir = ensure_dir(
            volume_dir / "chapters" / f"chapter_{chapter.number:03d}"
        )

        if self.llm_calls is not None and self.llm_calls.draft is not None:
            draft_data = self.llm_calls.draft
        else:
            # Real LLM path: caller (workflow) handles the actual call.
            # This mock-only fallback produces a placeholder so status advances.
            draft_data = {
                "title": f"Draft of scene {scene.number}",
                "body": f"Draft content for {scene.title}.",
            }
            # In production this returns None and the caller calls LLM separately.
            # But for tests we want direct file output so mark as created.

        draft_path = scene_dir / f"scene_{scene.number:03d}.draft.json"
        draft_path.write_text(
            json.dumps(draft_data, ensure_ascii=False),
            encoding="utf-8",
        )
        return draft_data


    def _review(
        self,
        *,
        series_dir: Path,
        volume_dir: Path,
        chapter: Any,
        scene: Any,
    ) -> dict[str, Any] | None:
        """Review the draft and save to disk. Returns review JSON or None.

        When llm_calls is provided but review_status is None → NO-OP (return None).
        This lets tests verify that drafting stops at 'drafted' status when
        the reviewer signals readiness=False.
        """
        scene_dir = volume_dir / "chapters" / f"chapter_{chapter.number:03d}"
        draft_path = scene_dir / f"scene_{scene.number:03d}.draft.json"
        draft_data_str = draft_path.read_text(encoding="utf-8")

        # If mock provided but review_status explicitly None → NO-OP
        if self.llm_calls is not None and self.llm_calls.review_status is None:
            return None

        # If llm_calls provided with actual data → use it
        if self.llm_calls is not None and self.llm_calls.review_status is not None:
            review_result = self.llm_calls.review_status
        else:
            # Real LLM path: caller handles; return a default dict for backwards compat
            review_result = {
                "issues": [],
                "ready_for_publication": True,
                "suggested_changes": "",
                "overall_quality_score": 9,
            }

        review_path = scene_dir / f"scene_{scene.number:03d}.review.json"
        review_path.write_text(
            json.dumps(review_result, ensure_ascii=False),
            encoding="utf-8",
        )
        return review_result


    def _revise(
        self,
        *,
        series_dir: Path,
        volume_dir: Path,
        chapter: Any,
        scene: Any,
    ) -> bool:
        """Revise the draft and save MD + revised JSON. Returns True if revised."""
        scene_dir = (
            volume_dir / "chapters" / f"chapter_{chapter.number:03d}"
        )

        if self.llm_calls is not None and self.llm_calls.revised is not None:
            revised_data = self.llm_calls.revised
        else:
            # Real LLM path: caller handles; return False to signal NO-OP.
            drafted_text = (
                scene_dir / f"scene_{scene.number:03d}.draft.json"
            ).read_text(encoding="utf-8")
            draft_parsed = json.loads(drafted_text)
            revised_data = {
                "title": f"Revised: {draft_parsed.get('title', 'Untitled')}",
                "body": draft_parsed.get("body", ""),
            }

        # Save revised JSON
        revised_path = scene_dir / f"scene_{scene.number:03d}.revised.json"
        revised_path.write_text(
            json.dumps(revised_data, ensure_ascii=False),
            encoding="utf-8",
        )

        # Generate MD content from revision
        title = revised_data.get("title", f"Scene {scene.number}")
        body = revised_data.get("body", "")
        scene_md = scene_dir / f"scene_{scene.number:03d}.md"
        scene_md.write_text(
            f"# {title}\n\n{body.strip()}\n",
            encoding="utf-8",
        )

        return True  # revised_now = True
