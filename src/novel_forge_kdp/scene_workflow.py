"""Scene processing pipeline for draft -> review -> revise lifecycle."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .paths import ensure_dir

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
class SceneResult:
    draft_created: bool = False
    review_done: bool = False
    revised_now: bool = False


class SceneWorkflowError(RuntimeError):
    pass


@dataclass
class SceneWorkflow:
    """Executes one scene through the draft -> review -> revise lifecycle."""

    repository: JsonRepositoryProtocol
    llm_calls: SceneLlmCallsProtocol
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
        draft_data = self.llm_calls.draft(state=state, outline=outline, scene=scene)
        self.repository.save_json(self._scene_dir(volume_dir, chapter) / f"scene_{scene.number:03d}.draft.json", draft_data)
        return draft_data

    def _review(self, *, volume_dir: Path, chapter: Any, scene: Any) -> dict[str, Any] | None:
        scene_dir = self._scene_dir(volume_dir, chapter)
        draft_path = scene_dir / f"scene_{scene.number:03d}.draft.json"
        draft_data = json.loads(draft_path.read_text(encoding="utf-8"))

        review_result = self.llm_calls.review(draft_data=draft_data)
        if review_result is None:
            return None

        self.repository.save_json(scene_dir / f"scene_{scene.number:03d}.review.json", review_result)
        return review_result

    def _revise(self, *, volume_dir: Path, chapter: Any, scene: Any) -> bool:
        scene_dir = self._scene_dir(volume_dir, chapter)
        draft_path = scene_dir / f"scene_{scene.number:03d}.draft.json"
        review_path = scene_dir / f"scene_{scene.number:03d}.review.json"

        revised_data = self.llm_calls.revise(
            draft_text=draft_path.read_text(encoding="utf-8"),
            review_text=review_path.read_text(encoding="utf-8"),
        )
        if revised_data is None:
            return False

        self.repository.save_json(scene_dir / f"scene_{scene.number:03d}.revised.json", revised_data)
        self._scene_markdown_path(volume_dir, chapter, scene).write_text(
            f"# {revised_data['title']}\n\n{revised_data['body'].strip()}\n",
            encoding="utf-8",
        )
        return True

    def _save_state(self, series_dir: Path, state: Any) -> None:
        if self.save_state is not None:
            self.save_state(series_dir, state)

    @staticmethod
    def _scene_dir(volume_dir: Path, chapter: Any) -> Path:
        return ensure_dir(volume_dir / "chapters" / f"chapter_{chapter.number:03d}")

    @staticmethod
    def _scene_markdown_path(volume_dir: Path, chapter: Any, scene: Any) -> Path:
        return volume_dir / "chapters" / f"chapter_{chapter.number:03d}" / f"scene_{scene.number:03d}.md"
