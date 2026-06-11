from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .artifact_paths import SeriesPaths
from .exporter import KdpExporter, chapter_heading_count, write_epub, write_export_chapters
from .llm import OllamaOpenAIClient
from .models import ChapterPlan, ProjectState, ScenePlan, SceneProgress, SeriesPlan, VolumeOutline, VolumeProgress
from .outline_validation import OutlineValidationError, validate_volume_outline
from .paths import PathSafetyError, ensure_dir, safe_child_dir, safe_slug
from .prompts import PromptStore
from .quality import QualityGate, QualityGateError, review_has_blocking_issues
from .repository import StateRepository
from .schemas import load_schema
from .scene_workflow import SceneLlmCalls, SceneResult, SceneWorkflow


class NovelForgeError(RuntimeError):
    pass


class NovelForge:
    def __init__(self, workspace: Path, llm: Any | None = None, prompts: PromptStore | None = None) -> None:
        self.workspace = Path(workspace)
        ensure_dir(self.workspace)
        self.prompts = prompts or PromptStore()
        self.llm = llm
        self.repository = StateRepository()

    def _client_for(self, series_dir: Path | None = None) -> Any:
        if self.llm is not None:
            if hasattr(self.llm, "log_dir"):
                self.llm.log_dir = (series_dir / "raw_logs") if series_dir is not None else (self.workspace / "_raw_logs")
            return self.llm
        return OllamaOpenAIClient(log_dir=(series_dir / "raw_logs") if series_dir is not None else (self.workspace / "_raw_logs"))

    def _series_dir(self, slug: str) -> Path:
        try:
            return safe_child_dir(self.workspace, slug)
        except PathSafetyError as exc:
            raise NovelForgeError(str(exc)) from exc

    def plan_series(self, keyword: str) -> ProjectState:
        schema = load_schema("series_plan")
        prompt = self.prompts.render("series_plan", keyword=keyword)
        data = self._client_for().complete_json(
            task="series_plan",
            messages=[{"role": "system", "content": _json_system()}, {"role": "user", "content": prompt}],
            schema=schema,
        )
        data["slug"] = safe_slug(data.get("slug") or data.get("title") or keyword)
        series = SeriesPlan.model_validate(data)
        state = ProjectState(
            series=series,
            volumes=[VolumeProgress(number=v.number, title=v.title) for v in series.planned_volumes[:1]],
        )
        series_dir = self._series_dir(series.slug)
        if series_dir.exists():
            raise NovelForgeError(f"series already exists: {series.slug}")
        ensure_dir(series_dir)
        paths = SeriesPaths(series_dir)
        ensure_dir(paths.raw_logs)
        self._write_json(paths.series_plan, series.model_dump())
        self._save_state(series_dir, state)
        return state

    def status(self, slug: str) -> ProjectState:
        series_dir = self._series_dir(slug)
        try:
            return self.repository.load_state(series_dir)
        except FileNotFoundError as exc:
            raise NovelForgeError(f"series not found: {slug}") from exc

    def write_volume(self, slug: str, volume_number: int | None = None, max_scenes: int | None = None) -> ProjectState:
        series_dir = self._series_dir(slug)
        state = self.status(slug)
        number = volume_number or state.current_volume
        volume = self._ensure_volume_progress(state, number)
        volume_dir = ensure_dir(SeriesPaths(series_dir).volume(number).root)
        outline = self._load_or_create_outline(series_dir, volume_dir, state, volume, number)

        if self._process_outline_scenes(series_dir, volume_dir, state, volume, outline, max_scenes):
            return state
        for chapter in outline.chapters:
            self._write_chapter_markdown(volume_dir, chapter)
        volume.status = "drafted"
        self._save_state(series_dir, state)
        return state

    def _ensure_volume_progress(self, state: ProjectState, number: int) -> VolumeProgress:
        if number > len(state.series.planned_volumes):
            raise NovelForgeError(f"volume exceeds planned series: volume={number} planned={len(state.series.planned_volumes)}")
        volume = next((v for v in state.volumes if v.number == number), None)
        if volume is not None:
            return volume
        planned = next((v for v in state.series.planned_volumes if v.number == number), None)
        if planned is None:
            raise NovelForgeError(f"volume exceeds planned series: volume={number} planned={len(state.series.planned_volumes)}")
        volume = VolumeProgress(number=number, title=planned.title)
        state.volumes.append(volume)
        return volume

    def _load_or_create_outline(self, series_dir: Path, volume_dir: Path, state: ProjectState, volume: VolumeProgress, number: int) -> VolumeOutline:
        outline_path = SeriesPaths(series_dir).volume(number).outline
        if outline_path.exists():
            outline = VolumeOutline.model_validate_json(outline_path.read_text(encoding="utf-8"))
            self._validate_volume_outline(outline, number)
            self._sync_volume_scenes(volume, outline)
            return outline
        outline_data = self._client_for(series_dir).complete_json(
            task="volume_outline",
            messages=[
                {"role": "system", "content": _json_system()},
                {"role": "user", "content": self.prompts.render("volume_outline", series=json.dumps(state.series.model_dump(), ensure_ascii=False), volume_number=number)},
            ],
            schema=load_schema("volume_outline"),
        )
        outline = VolumeOutline.model_validate(outline_data)
        self._validate_volume_outline(outline, number)
        self._write_json(outline_path, outline.model_dump())
        volume.status = "outlined"
        self._sync_volume_scenes(volume, outline)
        self._save_state(series_dir, state)
        return outline

    def _process_outline_scenes(
        self,
        series_dir: Path,
        volume_dir: Path,
        state: ProjectState,
        volume: VolumeProgress,
        outline: VolumeOutline,
        max_scenes: int | None,
    ) -> bool:
        processed = 0
        for chapter in outline.chapters:
            for scene in chapter.scenes:
                if max_scenes is not None and processed >= max_scenes:
                    self._save_state(series_dir, state)
                    return True
                progress = next(p for p in volume.scenes if p.chapter == chapter.number and p.scene == scene.number)
                if self._process_scene(series_dir, volume_dir, state, outline, chapter, scene, progress):
                    processed += 1
        return False

    def _process_scene(self, series_dir: Path, volume_dir: Path, state: ProjectState, outline: VolumeOutline, chapter: ChapterPlan, scene: ScenePlan, progress: SceneProgress) -> bool:
        result = SceneWorkflow(
            llm_calls=SceneLlmCalls(client=self._client_for(series_dir), prompts=self.prompts, system_prompt=_json_system()),
            write_json=self._write_json,
            save_state=self._save_state,
        ).run(
            series_dir=series_dir,
            volume_dir=volume_dir,
            state=state,
            outline=outline,
            chapter=chapter,
            scene=scene,
            progress=progress,
        )
        if result.revised_now:
            self._write_chapter_markdown(volume_dir, chapter)
        return result.revised_now

    def _write_chapter_markdown(self, volume_dir: Path, chapter: ChapterPlan) -> None:
        chapter_dir = ensure_dir(volume_dir / "chapters" / f"chapter_{chapter.number:03d}")
        parts = [f"## {chapter.title}"]
        for scene in chapter.scenes:
            scene_md = chapter_dir / f"scene_{scene.number:03d}.md"
            if scene_md.exists():
                text = scene_md.read_text(encoding="utf-8").strip()
                if text:
                    parts.append(text)
        (chapter_dir / "chapter.md").write_text("\n\n".join(parts).strip() + "\n", encoding="utf-8")

    @staticmethod
    def _safe_series_file(series_dir: Path, relative_path: str) -> Path:
        candidate_raw = Path(relative_path)
        if candidate_raw.is_absolute():
            raise NovelForgeError(f"scene manuscript path escapes series directory: {relative_path}")
        root = series_dir.resolve()
        candidate = (root / candidate_raw).resolve()
        if root != candidate and root not in candidate.parents:
            raise NovelForgeError(f"scene manuscript path escapes series directory: {relative_path}")
        return candidate

    @staticmethod
    def _validate_volume_outline(outline: VolumeOutline, expected_number: int) -> None:
        try:
            validate_volume_outline(outline, expected_number)
        except OutlineValidationError as exc:
            raise NovelForgeError(str(exc)) from exc

    @staticmethod
    def _sync_volume_scenes(volume: VolumeProgress, outline: VolumeOutline) -> None:
        existing = {(scene.chapter, scene.scene): scene for scene in volume.scenes}
        synced: list[SceneProgress] = []
        for chapter in outline.chapters:
            for scene in chapter.scenes:
                current = existing.get((chapter.number, scene.number))
                if current is None:
                    current = SceneProgress(chapter=chapter.number, scene=scene.number, title=scene.title)
                else:
                    current.title = scene.title
                synced.append(current)
        volume.scenes = synced
        volume.title = outline.title

    def complete_volume(self, slug: str, volume_number: int | None = None, force: bool = False) -> ProjectState:
        series_dir = self._series_dir(slug)
        state = self.status(slug)
        number = volume_number or state.current_volume
        state, volume = self._ensure_revised_scenes(slug, state, number)
        volume_dir = ensure_dir(SeriesPaths(series_dir).volume(number).root)
        manuscript = self._assemble_volume_manuscript(series_dir, volume)
        outline = self._load_validated_outline(volume_dir, number)

        review = self._review_volume(series_dir, state, manuscript)
        self._write_json(volume_dir / "volume_review.json", review)
        revised = self._revise_volume(series_dir, manuscript, review, expected_chapter_count=len(outline.chapters))
        self._write_json(volume_dir / "volume_revised.json", revised)

        volume.title = revised["title"]
        revised_md = f"# {revised['title']}\n\n{revised['body'].strip()}\n"
        (volume_dir / "volume_revised.md").write_text(revised_md, encoding="utf-8")
        final_review = self._final_review_if_needed(series_dir, volume_dir, state, review, revised_md)
        self._ensure_publication_allowed(series_dir, state, volume, final_review, force)

        self._update_bible(series_dir, revised_md)
        self._export_kdp(volume_dir, revised["title"], revised_md)
        volume.status = "revised"
        self._save_state(series_dir, state)
        return state

    def _ensure_revised_scenes(self, slug: str, state: ProjectState, number: int) -> tuple[ProjectState, VolumeProgress]:
        volume = next((v for v in state.volumes if v.number == number), None)
        if volume is None or not volume.scenes or any(scene.status != "revised" for scene in volume.scenes):
            state = self.write_volume(slug, number)
            volume = next(v for v in state.volumes if v.number == number)
        return state, volume

    def _load_validated_outline(self, volume_dir: Path, number: int) -> VolumeOutline:
        outline = VolumeOutline.model_validate_json((volume_dir / "outline.json").read_text(encoding="utf-8"))
        self._validate_volume_outline(outline, number)
        return outline

    def _review_volume(self, series_dir: Path, state: ProjectState, manuscript: str) -> dict[str, Any]:
        return self._client_for(series_dir).complete_json(
            task="volume_review",
            messages=[
                {"role": "system", "content": _json_system()},
                {"role": "user", "content": self.prompts.render("volume_review", series=state.series.model_dump_json(), manuscript=manuscript)},
            ],
            schema=load_schema("volume_review"),
        )

    def _revise_volume(self, series_dir: Path, manuscript: str, review: dict[str, Any], expected_chapter_count: int) -> dict[str, Any]:
        revised = self._client_for(series_dir).complete_json(
            task="revise_volume",
            messages=[
                {"role": "system", "content": _json_system()},
                {"role": "user", "content": self.prompts.render("revise_volume", manuscript=manuscript, review=json.dumps(review, ensure_ascii=False), chapter_count=expected_chapter_count)},
            ],
            schema=load_schema("revised_volume"),
        )
        try:
            QualityGate().ensure_revised_volume_structure(revised["body"], expected_chapter_count)
        except QualityGateError as exc:
            raise NovelForgeError(str(exc)) from exc
        return revised

    def _final_review_if_needed(self, series_dir: Path, volume_dir: Path, state: ProjectState, review: dict[str, Any], revised_md: str) -> dict[str, Any]:
        if review.get("ready_for_publication", False):
            return review
        final_review = self._review_volume(series_dir, state, revised_md)
        self._write_json(volume_dir / "volume_review_final.json", final_review)
        return final_review

    def _ensure_publication_allowed(self, series_dir: Path, state: ProjectState, volume: VolumeProgress, final_review: dict[str, Any], force: bool) -> None:
        try:
            QualityGate().ensure_export_allowed(final_review, force=force)
        except QualityGateError as exc:
            volume.status = "reviewed"
            self._save_state(series_dir, state)
            raise NovelForgeError(str(exc)) from exc

    def continue_series(self, slug: str) -> ProjectState:
        state = self.status(slug)
        self._ensure_planned_volume_number(state, state.current_volume)
        current = self._find_volume(state, state.current_volume)
        if current is None or current.status != "revised":
            return self.complete_volume(slug, state.current_volume)
        next_number = state.current_volume + 1
        self._ensure_planned_volume_number(state, next_number)
        state.current_volume = next_number
        self._ensure_volume_progress(state, next_number)
        self._save_state(self._series_dir(slug), state)
        return self.write_volume(slug, next_number)

    @staticmethod
    def _find_volume(state: ProjectState, number: int) -> VolumeProgress | None:
        return next((v for v in state.volumes if v.number == number), None)

    @staticmethod
    def _ensure_planned_volume_number(state: ProjectState, number: int) -> None:
        if number > len(state.series.planned_volumes):
            raise NovelForgeError(f"volume exceeds planned series: volume={number} planned={len(state.series.planned_volumes)}")

    def export_volume(self, slug: str, volume_number: int | None = None) -> Path:
        series_dir = self._series_dir(slug)
        state = self.status(slug)
        number = volume_number or state.current_volume
        volume = next((v for v in state.volumes if v.number == number), None)
        if volume is None:
            raise NovelForgeError(f"volume not found: {number}")
        volume_dir = ensure_dir(SeriesPaths(series_dir).volume(number).root)
        manuscript = (volume_dir / "volume_revised.md").read_text(encoding="utf-8") if (volume_dir / "volume_revised.md").exists() else self._assemble_volume_manuscript(series_dir, volume)
        self._export_kdp(volume_dir, volume.title, manuscript)
        return volume_dir / "exports" / "manuscript.md"

    def _assemble_volume_manuscript(self, series_dir: Path, volume: VolumeProgress) -> str:
        parts = [f"# {volume.title}"]
        for scene in sorted(volume.scenes, key=lambda s: (s.chapter, s.scene)):
            if scene.status != "revised":
                raise NovelForgeError(f"scene is not revised: chapter={scene.chapter} scene={scene.scene}")
            if scene.path is None:
                raise NovelForgeError(f"missing scene manuscript path: chapter={scene.chapter} scene={scene.scene}")
            scene_path = self._safe_series_file(series_dir, scene.path)
            if not scene_path.exists():
                raise NovelForgeError(f"missing scene manuscript: {scene.path}")
            text = scene_path.read_text(encoding="utf-8").strip()
            if not text:
                raise NovelForgeError(f"empty scene manuscript: {scene.path}")
            parts.append(text)
        if len(parts) == 1:
            raise NovelForgeError(f"volume has no revised scenes: volume={volume.number}")
        return "\n\n".join(parts).strip() + "\n"

    def _update_bible(self, series_dir: Path, manuscript: str) -> None:
        bible_path = SeriesPaths(series_dir).bible
        existing = bible_path.read_text(encoding="utf-8") if bible_path.exists() else "{}"
        bible = self._client_for(series_dir).complete_json(
            task="bible_update",
            messages=[
                {"role": "system", "content": _json_system()},
                {"role": "user", "content": self.prompts.render("bible_update", existing_bible=existing, manuscript=manuscript)},
            ],
            schema=load_schema("bible_update"),
        )
        self._write_json(bible_path, bible)

    @staticmethod
    def _export_kdp(volume_dir: Path, title: str, manuscript: str) -> None:
        KdpExporter().export(volume_dir, title, manuscript)

    @staticmethod
    def _write_export_chapters(exports: Path, manuscript: str) -> None:
        write_export_chapters(exports, manuscript)

    @staticmethod
    def _write_epub(path: Path, title: str, manuscript: str) -> None:
        write_epub(path, title, manuscript)

    def _save_state(self, series_dir: Path, state: ProjectState) -> None:
        self.repository.save_state(series_dir, state)

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        tmp = path.with_name(path.name + ".tmp")
        backup = path.with_suffix(path.suffix + ".bak")
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            backup.write_bytes(path.read_bytes())
        tmp.replace(path)


def _chapter_heading_count(markdown: str) -> int:
    return chapter_heading_count(markdown)


def _review_has_blocking_issues(review: dict[str, Any]) -> bool:
    return review_has_blocking_issues(review)


def _json_system() -> str:
    return "You are a professional Japanese commercial fiction editor. Return only valid JSON matching the requested schema. Do not use markdown fences."
