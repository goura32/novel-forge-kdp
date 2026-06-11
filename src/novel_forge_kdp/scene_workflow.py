"""Scene processing pipeline for draft -> review -> revise lifecycle."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .paths import ensure_dir

JsonWriter = Callable[[Path, dict[str, Any]], None]
StateSaver = Callable[[Path, Any], None]


class SceneLlmCallsProtocol(Protocol):
    def draft(self, *, state: Any, outline: Any, scene: Any) -> dict[str, Any]: ...

    def review(self, *, draft_data: dict[str, Any]) -> dict[str, Any] | None: ...

    def revise(self, *, draft_text: str, review_text: str) -> dict[str, Any] | None: ...


class JsonRepositoryProtocol(Protocol):
    def save_json(self, path: Path, data: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class SceneLlmCalls:
    """Production LLM calls for scene drafting, reviewing, and revision."""

    runner: Any

    def draft(self, *, state: Any, outline: Any, scene: Any) -> dict[str, Any]:
        return self.runner.complete(
            "scene_draft",
            series=state.series.model_dump_json(),
            outline=outline.model_dump_json(),
            scene=scene.model_dump_json(),
        )

    def review(self, *, draft_data: dict[str, Any]) -> dict[str, Any] | None:
        return self.runner.complete("review", text=json.dumps(draft_data, ensure_ascii=False))

    def revise(self, *, draft_text: str, review_text: str) -> dict[str, Any] | None:
        return self.runner.complete("revise_scene", draft=draft_text, review=review_text)


@dataclass
class MockLlmCalls:
    """Mock responses for standalone SceneWorkflow tests."""

    draft: dict[str, Any] | None = None
    review_status: dict[str, Any] | str | None = None
    revised: dict[str, Any] | None = None


@dataclass
class SceneResult:
    draft_created: bool = False
    review_done: bool = False
    revised_now: bool = False


class SceneWorkflowError(RuntimeError):
    pass


@dataclass
class SceneWorkflow:
    """Executes one scene through the draft -> review -> revise lifecycle."""

    llm_calls: SceneLlmCallsProtocol | MockLlmCalls | None = None
    repository: JsonRepositoryProtocol | None = None
    write_json: JsonWriter | None = None
    save_state: StateSaver | None = None

    def run(
        self,
        *,
        series_dir: Path,
        volume_dir: Path,
        state: Any,
        outline: Any,
        chapter: Any,
        scene: Any,
        progress: Any,
    ) -> SceneResult:
        result = SceneResult()

        if progress.status == "planned":
            self._draft(volume_dir=volume_dir, state=state, outline=outline, chapter=chapter, scene=scene)
            result.draft_created = True
            progress.status = "drafted"
            self._save_state(series_dir, state)

        if progress.status == "drafted":
            review_done = self._review(volume_dir=volume_dir, chapter=chapter, scene=scene)
            if review_done:
                result.review_done = True
                progress.status = "reviewed"
                self._save_state(series_dir, state)

        if progress.status == "reviewed":
            revised_now = self._revise(volume_dir=volume_dir, chapter=chapter, scene=scene)
            result.revised_now = revised_now
            if revised_now:
                progress.status = "revised"
                scene_md = self._scene_markdown_path(volume_dir, chapter, scene)
                progress.path = str(scene_md.relative_to(series_dir))
                self._save_state(series_dir, state)

        return result

    def _draft(self, *, volume_dir: Path, state: Any, outline: Any, chapter: Any, scene: Any) -> dict[str, Any]:
        if isinstance(self.llm_calls, MockLlmCalls):
            draft_data = self.llm_calls.draft or {
                "title": f"Draft of scene {scene.number}",
                "body": f"Draft content for {scene.title}.",
            }
        elif self.llm_calls is not None:
            draft_data = self.llm_calls.draft(state=state, outline=outline, scene=scene)
        else:
            draft_data = {
                "title": f"Draft of scene {scene.number}",
                "body": f"Draft content for {scene.title}.",
            }

        self._write_json(self._scene_dir(volume_dir, chapter) / f"scene_{scene.number:03d}.draft.json", draft_data)
        return draft_data

    def _review(self, *, volume_dir: Path, chapter: Any, scene: Any) -> dict[str, Any] | None:
        scene_dir = self._scene_dir(volume_dir, chapter)
        draft_path = scene_dir / f"scene_{scene.number:03d}.draft.json"
        draft_data = json.loads(draft_path.read_text(encoding="utf-8"))

        if isinstance(self.llm_calls, MockLlmCalls):
            if self.llm_calls.review_status is None:
                return None
            review_result: dict[str, Any]
            if isinstance(self.llm_calls.review_status, str):
                review_result = {"ready_for_publication": self.llm_calls.review_status == "ready_for_publication"}
            else:
                review_result = self.llm_calls.review_status
        elif self.llm_calls is not None:
            maybe_review = self.llm_calls.review(draft_data=draft_data)
            if maybe_review is None:
                return None
            review_result = maybe_review
        else:
            review_result = {
                "issues": [],
                "ready_for_publication": True,
                "suggested_changes": "",
                "overall_quality_score": 9,
            }

        self._write_json(scene_dir / f"scene_{scene.number:03d}.review.json", review_result)
        return review_result

    def _revise(self, *, volume_dir: Path, chapter: Any, scene: Any) -> bool:
        scene_dir = self._scene_dir(volume_dir, chapter)
        draft_path = scene_dir / f"scene_{scene.number:03d}.draft.json"
        review_path = scene_dir / f"scene_{scene.number:03d}.review.json"

        if isinstance(self.llm_calls, MockLlmCalls):
            if self.llm_calls.revised is None:
                return False
            revised_data = self.llm_calls.revised
        elif self.llm_calls is not None:
            revised_data = self.llm_calls.revise(
                draft_text=draft_path.read_text(encoding="utf-8"),
                review_text=review_path.read_text(encoding="utf-8"),
            )
            if revised_data is None:
                return False
        else:
            draft_data = json.loads(draft_path.read_text(encoding="utf-8"))
            revised_data = {
                "title": f"Revised: {draft_data.get('title', 'Untitled')}",
                "body": draft_data.get("body", ""),
            }

        self._write_json(scene_dir / f"scene_{scene.number:03d}.revised.json", revised_data)
        self._scene_markdown_path(volume_dir, chapter, scene).write_text(
            f"# {revised_data['title']}\n\n{revised_data['body'].strip()}\n",
            encoding="utf-8",
        )
        return True

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        if self.repository is not None:
            self.repository.save_json(path, data)
            return
        if self.write_json is not None:
            self.write_json(path, data)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _save_state(self, series_dir: Path, state: Any) -> None:
        if self.save_state is not None:
            self.save_state(series_dir, state)

    @staticmethod
    def _scene_dir(volume_dir: Path, chapter: Any) -> Path:
        return ensure_dir(volume_dir / "chapters" / f"chapter_{chapter.number:03d}")

    @staticmethod
    def _scene_markdown_path(volume_dir: Path, chapter: Any, scene: Any) -> Path:
        return volume_dir / "chapters" / f"chapter_{chapter.number:03d}" / f"scene_{scene.number:03d}.md"
