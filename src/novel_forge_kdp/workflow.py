from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .llm import OllamaOpenAIClient
from .models import ProjectState, SceneProgress, SeriesPlan, VolumeOutline, VolumeProgress
from .paths import ensure_dir, safe_slug
from .prompts import PromptStore
from .schemas import load_schema


class NovelForge:
    def __init__(self, workspace: Path, llm: Any | None = None, prompts: PromptStore | None = None) -> None:
        self.workspace = Path(workspace)
        ensure_dir(self.workspace)
        self.prompts = prompts or PromptStore()
        self.llm = llm

    def _client_for(self, series_dir: Path | None = None) -> Any:
        if self.llm is not None:
            if hasattr(self.llm, "log_dir"):
                self.llm.log_dir = (series_dir / "raw_logs") if series_dir is not None else (self.workspace / "_raw_logs")
            return self.llm
        return OllamaOpenAIClient(log_dir=(series_dir / "raw_logs") if series_dir is not None else (self.workspace / "_raw_logs"))

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
        series_dir = ensure_dir(self.workspace / series.slug)
        ensure_dir(series_dir / "raw_logs")
        self._write_json(series_dir / "series_plan.json", series.model_dump())
        self._save_state(series_dir, state)
        return state

    def status(self, slug: str) -> ProjectState:
        return ProjectState.model_validate_json((self.workspace / slug / "state.json").read_text(encoding="utf-8"))

    def write_volume(self, slug: str, volume_number: int | None = None) -> ProjectState:
        series_dir = self.workspace / slug
        state = self.status(slug)
        number = volume_number or state.current_volume
        volume = next((v for v in state.volumes if v.number == number), None)
        if volume is None:
            planned = next((v for v in state.series.planned_volumes if v.number == number), None)
            if planned is None:
                planned = state.series.planned_volumes[-1]
            volume = VolumeProgress(number=number, title=planned.title)
            state.volumes.append(volume)
        volume_dir = ensure_dir(series_dir / f"volume_{number:03d}")
        outline_path = volume_dir / "outline.json"
        if outline_path.exists():
            outline = VolumeOutline.model_validate_json(outline_path.read_text(encoding="utf-8"))
        else:
            outline_data = self._client_for(series_dir).complete_json(
                task="volume_outline",
                messages=[
                    {"role": "system", "content": _json_system()},
                    {"role": "user", "content": self.prompts.render("volume_outline", series=json.dumps(state.series.model_dump(), ensure_ascii=False), volume_number=number)},
                ],
                schema=load_schema("volume_outline"),
            )
            outline = VolumeOutline.model_validate(outline_data)
            self._write_json(outline_path, outline.model_dump())
            volume.status = "outlined"
            volume.scenes = [SceneProgress(chapter=c.number, scene=s.number, title=s.title) for c in outline.chapters for s in c.scenes]
            self._save_state(series_dir, state)

        for chapter in outline.chapters:
            for scene in chapter.scenes:
                progress = next(p for p in volume.scenes if p.chapter == chapter.number and p.scene == scene.number)
                scene_dir = ensure_dir(volume_dir / "chapters" / f"chapter_{chapter.number:03d}")
                scene_md = scene_dir / f"scene_{scene.number:03d}.md"
                if progress.status == "planned":
                    draft = self._client_for(series_dir).complete_json(
                        task="scene_draft",
                        messages=[{"role": "system", "content": _json_system()}, {"role": "user", "content": self.prompts.render("scene_draft", series=state.series.model_dump_json(), outline=outline.model_dump_json(), scene=scene.model_dump_json())}],
                        schema=load_schema("scene_draft"),
                    )
                    self._write_json(scene_dir / f"scene_{scene.number:03d}.draft.json", draft)
                    progress.status = "drafted"
                    self._save_state(series_dir, state)
                if progress.status == "drafted":
                    draft_path = scene_dir / f"scene_{scene.number:03d}.draft.json"
                    draft_data = json.loads(draft_path.read_text(encoding="utf-8"))
                    review = self._client_for(series_dir).complete_json(
                        task="review",
                        messages=[{"role": "system", "content": _json_system()}, {"role": "user", "content": self.prompts.render("review", text=json.dumps(draft_data, ensure_ascii=False))}],
                        schema=load_schema("review"),
                    )
                    self._write_json(scene_dir / f"scene_{scene.number:03d}.review.json", review)
                    progress.status = "reviewed"
                    self._save_state(series_dir, state)
                if progress.status == "reviewed":
                    draft_path = scene_dir / f"scene_{scene.number:03d}.draft.json"
                    review_path = scene_dir / f"scene_{scene.number:03d}.review.json"
                    revised = self._client_for(series_dir).complete_json(
                        task="revise_scene",
                        messages=[{"role": "system", "content": _json_system()}, {"role": "user", "content": self.prompts.render("revise_scene", draft=draft_path.read_text(encoding="utf-8"), review=review_path.read_text(encoding="utf-8"))}],
                        schema=load_schema("revised_scene"),
                    )
                    self._write_json(scene_dir / f"scene_{scene.number:03d}.revised.json", revised)
                    scene_md.write_text(f"# {revised['title']}\n\n{revised['body'].strip()}\n", encoding="utf-8")
                    progress.status = "revised"
                    progress.path = str(scene_md.relative_to(series_dir))
                    self._save_state(series_dir, state)
        volume.status = "drafted"
        self._save_state(series_dir, state)
        return state

    def _save_state(self, series_dir: Path, state: ProjectState) -> None:
        self._write_json(series_dir / "state.json", state.model_dump())

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _json_system() -> str:
    return "You are a professional Japanese commercial fiction editor. Return only valid JSON matching the requested schema. Do not use markdown fences."
