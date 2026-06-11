from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_paths import SeriesPaths
from .exporter import KdpExporter
from .chapter_manuscript_assembler import ChapterManuscriptAssembler
from .llm import OllamaOpenAIClient
from .llm_task_runner import LLMTaskRunner
from .manuscript_assembler import ManuscriptAssembler, ManuscriptAssemblyError
from .models import ChapterPlan, ProjectState, ScenePlan, SceneProgress, SeriesPlan, VolumeOutline, VolumeProgress
from .outline_validation import OutlineValidationError, validate_volume_outline
from .paths import PathSafetyError, ensure_dir, safe_child_dir
from .prompts import PromptStore
from .quality import QualityGate, QualityGateError
from .repository import ProjectRepository
from .scene_workflow import SceneLlmCalls, SceneResult, SceneWorkflow
from .series_continuation_workflow import SeriesContinuationWorkflow
from .series_planner import SeriesPlanner
from .outline_scene_processor import OutlineSceneProcessor
from .volume_completion_workflow import VolumeCompletionLlmCalls, VolumeCompletionLlmCallsError, VolumeCompletionWorkflow
from .volume_export_workflow import VolumeExportWorkflow, VolumeExportWorkflowError
from .volume_outline_workflow import VolumeOutlineWorkflow
from .volume_progress_service import VolumeProgressService, VolumeProgressServiceError
from .volume_writing_workflow import VolumeWritingWorkflow


class NovelForgeError(RuntimeError):
    pass


def assemble_volume_manuscript_for_forge(series_dir: Path, volume: VolumeProgress) -> str:
    try:
        return ManuscriptAssembler().assemble_volume(series_dir=series_dir, volume=volume)
    except (ManuscriptAssemblyError, PathSafetyError) as exc:
        raise NovelForgeError(str(exc)) from exc


class NovelForge:
    def __init__(self, workspace: Path, llm: Any | None = None, prompts: PromptStore | None = None) -> None:
        self.workspace = Path(workspace)
        ensure_dir(self.workspace)
        self.prompts = prompts or PromptStore()
        self.llm = llm
        self.repository = ProjectRepository()
        self.volume_progress = VolumeProgressService()
        self.chapter_manuscript_assembler = ChapterManuscriptAssembler()

    def _client_for(self, series_dir: Path | None = None) -> Any:
        if self.llm is not None:
            if hasattr(self.llm, "log_dir"):
                self.llm.log_dir = (series_dir / "raw_logs") if series_dir is not None else (self.workspace / "_raw_logs")
            return self.llm
        return OllamaOpenAIClient(log_dir=(series_dir / "raw_logs") if series_dir is not None else (self.workspace / "_raw_logs"))

    def _task_runner_for(self, series_dir: Path | None = None) -> LLMTaskRunner:
        return LLMTaskRunner(client=self._client_for(series_dir), prompts=self.prompts, system_prompt=_json_system())

    def _series_dir(self, slug: str) -> Path:
        try:
            return safe_child_dir(self.workspace, slug)
        except PathSafetyError as exc:
            raise NovelForgeError(str(exc)) from exc

    def _new_series_dir(self, slug: str) -> Path:
        series_dir = self._series_dir(slug)
        if series_dir.exists():
            raise NovelForgeError(f"series already exists: {slug}")
        return series_dir

    def plan_series(self, keyword: str) -> ProjectState:
        return SeriesPlanner(
            task_runner=self._task_runner_for(),
            repository=self.repository,
            series_dir_for=self._new_series_dir,
        ).plan(keyword=keyword)

    def status(self, slug: str) -> ProjectState:
        series_dir = self._series_dir(slug)
        try:
            return self.repository.load_state(series_dir)
        except FileNotFoundError as exc:
            raise NovelForgeError(f"series not found: {slug}") from exc

    def write_volume(self, slug: str, volume_number: int | None = None, max_scenes: int | None = None) -> ProjectState:
        series_dir = self._series_dir(slug)
        state = self.status(slug)
        try:
            return VolumeWritingWorkflow(
                ensure_volume_progress=self.volume_progress.ensure_volume_progress,
                load_or_create_outline=self._load_or_create_outline,
                outline_scene_processor=OutlineSceneProcessor(
                    process_scene=self._process_scene,
                    save_state=self._save_state,
                    chapter_manuscript_assembler=self.chapter_manuscript_assembler,
                ),
                chapter_manuscript_assembler=self.chapter_manuscript_assembler,
                save_state=self._save_state,
            ).run(
                series_dir=series_dir,
                state=state,
                volume_number=volume_number,
                max_scenes=max_scenes,
            )
        except VolumeProgressServiceError as exc:
            raise NovelForgeError(str(exc)) from exc

    def _load_or_create_outline(self, series_dir: Path, volume_dir: Path, state: ProjectState, volume: VolumeProgress, number: int) -> VolumeOutline:
        return VolumeOutlineWorkflow(
            task_runner=self._task_runner_for(series_dir),
            repository=self.repository,
            validate_volume_outline=self._validate_volume_outline,
            sync_volume_scenes=self.volume_progress.sync_volume_scenes,
            save_state=self._save_state,
        ).load_or_create(
            series_dir=series_dir,
            volume_dir=volume_dir,
            state=state,
            volume=volume,
            number=number,
        )

    def _process_scene(self, series_dir: Path, volume_dir: Path, state: ProjectState, outline: VolumeOutline, chapter: ChapterPlan, scene: ScenePlan, progress: SceneProgress) -> bool:
        result = SceneWorkflow(
            llm_calls=SceneLlmCalls(runner=self._task_runner_for(series_dir)),
            repository=self.repository,
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
        return result.revised_now

    @staticmethod
    def _validate_volume_outline(outline: VolumeOutline, expected_number: int) -> None:
        try:
            validate_volume_outline(outline, expected_number)
        except OutlineValidationError as exc:
            raise NovelForgeError(str(exc)) from exc

    def complete_volume(self, slug: str, volume_number: int | None = None, force: bool = False) -> ProjectState:
        series_dir = self._series_dir(slug)
        state = self.status(slug)
        number = volume_number or state.current_volume
        try:
            state, volume = self.volume_progress.ensure_revised_scenes(
                slug=slug,
                state=state,
                number=number,
                write_volume=self.write_volume,
            )
        except VolumeProgressServiceError as exc:
            raise NovelForgeError(str(exc)) from exc
        volume_dir = ensure_dir(SeriesPaths(series_dir).volume(number).root)
        manuscript = assemble_volume_manuscript_for_forge(series_dir, volume)
        outline = self._load_validated_outline(volume_dir, number)
        llm_calls = VolumeCompletionLlmCalls(
            runner=self._task_runner_for(series_dir),
            repository=self.repository,
        )
        try:
            return VolumeCompletionWorkflow(
                review_volume=llm_calls.review_volume,
                revise_volume=llm_calls.revise_volume,
                final_review_if_needed=llm_calls.final_review_if_needed,
                ensure_publication_allowed=self._ensure_publication_allowed,
                update_bible=llm_calls.update_bible,
                export_kdp=self._export_kdp,
                save_state=self._save_state,
                save_volume_review=self.repository.save_volume_review,
                save_volume_revised=self.repository.save_volume_revised,
            ).run(
                series_dir=series_dir,
                volume_dir=volume_dir,
                state=state,
                volume=volume,
                outline=outline,
                manuscript=manuscript,
                force=force,
            )
        except VolumeCompletionLlmCallsError as exc:
            raise NovelForgeError(str(exc)) from exc


    def _load_validated_outline(self, volume_dir: Path, number: int) -> VolumeOutline:
        outline = VolumeOutline.model_validate_json((volume_dir / "outline.json").read_text(encoding="utf-8"))
        self._validate_volume_outline(outline, number)
        return outline

    def _ensure_publication_allowed(self, series_dir: Path, state: ProjectState, volume: VolumeProgress, final_review: dict[str, Any], force: bool) -> None:
        try:
            QualityGate().ensure_export_allowed(final_review, force=force)
        except QualityGateError as exc:
            volume.status = "reviewed"
            self._save_state(series_dir, state)
            raise NovelForgeError(str(exc)) from exc

    def continue_series(self, slug: str) -> ProjectState:
        try:
            return SeriesContinuationWorkflow(
                status=self.status,
                complete_volume=self.complete_volume,
                write_volume=self.write_volume,
                series_dir_for=self._series_dir,
                save_state=self._save_state,
                find_volume=self.volume_progress.find_volume,
                ensure_planned_volume_number=self.volume_progress.ensure_planned_volume_number,
                ensure_volume_progress=self.volume_progress.ensure_volume_progress,
            ).continue_series(slug=slug)
        except VolumeProgressServiceError as exc:
            raise NovelForgeError(str(exc)) from exc

    def export_volume(self, slug: str, volume_number: int | None = None) -> Path:
        series_dir = self._series_dir(slug)
        state = self.status(slug)
        try:
            return VolumeExportWorkflow(
                assemble_manuscript=assemble_volume_manuscript_for_forge,
                export_kdp=self._export_kdp,
            ).run(series_dir=series_dir, state=state, volume_number=volume_number)
        except VolumeExportWorkflowError as exc:
            raise NovelForgeError(str(exc)) from exc

    @staticmethod
    def _export_kdp(volume_dir: Path, title: str, manuscript: str) -> None:
        KdpExporter().export(volume_dir, title, manuscript)

    def _save_state(self, series_dir: Path, state: ProjectState) -> None:
        self.repository.save_state(series_dir, state)


def _json_system() -> str:
    return "You are a professional Japanese commercial fiction editor. Return only valid JSON matching the requested schema. Do not use markdown fences."
