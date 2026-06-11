from __future__ import annotations

import html
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any

from .llm import OllamaOpenAIClient
from .models import ChapterPlan, ProjectState, SceneProgress, SeriesPlan, VolumeOutline, VolumeProgress
from .paths import PathSafetyError, ensure_dir, safe_child_dir, safe_slug
from .prompts import PromptStore
from .schemas import load_schema


class NovelForgeError(RuntimeError):
    pass


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
        ensure_dir(series_dir / "raw_logs")
        self._write_json(series_dir / "series_plan.json", series.model_dump())
        self._save_state(series_dir, state)
        return state

    def status(self, slug: str) -> ProjectState:
        state_path = self._series_dir(slug) / "state.json"
        if not state_path.exists():
            raise NovelForgeError(f"series not found: {slug}")
        return ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))

    def write_volume(self, slug: str, volume_number: int | None = None, max_scenes: int | None = None) -> ProjectState:
        series_dir = self._series_dir(slug)
        state = self.status(slug)
        number = volume_number or state.current_volume
        if number > len(state.series.planned_volumes):
            raise NovelForgeError(f"volume exceeds planned series: volume={number} planned={len(state.series.planned_volumes)}")
        volume = next((v for v in state.volumes if v.number == number), None)
        if volume is None:
            planned = next((v for v in state.series.planned_volumes if v.number == number), None)
            if planned is None:
                raise NovelForgeError(f"volume exceeds planned series: volume={number} planned={len(state.series.planned_volumes)}")
            volume = VolumeProgress(number=number, title=planned.title)
            state.volumes.append(volume)
        volume_dir = ensure_dir(series_dir / f"volume_{number:03d}")
        outline_path = volume_dir / "outline.json"
        if outline_path.exists():
            outline = VolumeOutline.model_validate_json(outline_path.read_text(encoding="utf-8"))
            self._validate_volume_outline(outline, number)
            self._sync_volume_scenes(volume, outline)
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
            self._validate_volume_outline(outline, number)
            self._write_json(outline_path, outline.model_dump())
            volume.status = "outlined"
            self._sync_volume_scenes(volume, outline)
            self._save_state(series_dir, state)

        processed = 0
        for chapter in outline.chapters:
            for scene in chapter.scenes:
                if max_scenes is not None and processed >= max_scenes:
                    self._save_state(series_dir, state)
                    return state
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
                    self._write_chapter_markdown(volume_dir, chapter)
                    processed += 1
                    self._save_state(series_dir, state)
        for chapter in outline.chapters:
            self._write_chapter_markdown(volume_dir, chapter)
        volume.status = "drafted"
        self._save_state(series_dir, state)
        return state

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
        if outline.volume_number != expected_number:
            raise NovelForgeError(f"volume outline number mismatch: expected={expected_number} actual={outline.volume_number}")
        if len(outline.chapters) < 1:
            raise NovelForgeError("outline has no chapters")
        if len(outline.chapters) > 2:
            raise NovelForgeError(f"too many chapters in outline: max=2 actual={len(outline.chapters)}")
        chapter_numbers: set[int] = set()
        for chapter in outline.chapters:
            if chapter.number in chapter_numbers:
                raise NovelForgeError(f"duplicate chapter number in outline: {chapter.number}")
            chapter_numbers.add(chapter.number)
            if len(chapter.scenes) < 1:
                raise NovelForgeError(f"chapter has no scenes: chapter={chapter.number}")
            if len(chapter.scenes) > 2:
                raise NovelForgeError(f"too many scenes in outline chapter: chapter={chapter.number} max=2 actual={len(chapter.scenes)}")
            scene_numbers: set[int] = set()
            for scene in chapter.scenes:
                if scene.number in scene_numbers:
                    raise NovelForgeError(f"duplicate scene number in outline: chapter={chapter.number} scene={scene.number}")
                scene_numbers.add(scene.number)

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
        volume = next((v for v in state.volumes if v.number == number), None)
        if volume is None or not volume.scenes or any(scene.status != "revised" for scene in volume.scenes):
            state = self.write_volume(slug, number)
            volume = next(v for v in state.volumes if v.number == number)
        volume_dir = ensure_dir(series_dir / f"volume_{number:03d}")
        manuscript = self._assemble_volume_manuscript(series_dir, volume)
        outline = VolumeOutline.model_validate_json((volume_dir / "outline.json").read_text(encoding="utf-8"))
        self._validate_volume_outline(outline, number)
        expected_chapter_count = len(outline.chapters)
        review = self._client_for(series_dir).complete_json(
            task="volume_review",
            messages=[
                {"role": "system", "content": _json_system()},
                {"role": "user", "content": self.prompts.render("volume_review", series=state.series.model_dump_json(), manuscript=manuscript)},
            ],
            schema=load_schema("volume_review"),
        )
        self._write_json(volume_dir / "volume_review.json", review)
        revised = self._client_for(series_dir).complete_json(
            task="revise_volume",
            messages=[
                {"role": "system", "content": _json_system()},
                {"role": "user", "content": self.prompts.render("revise_volume", manuscript=manuscript, review=json.dumps(review, ensure_ascii=False), chapter_count=expected_chapter_count)},
            ],
            schema=load_schema("revised_volume"),
        )
        chapter_heading_count = _chapter_heading_count(revised["body"])
        if chapter_heading_count < 1:
            raise NovelForgeError("revised volume has no chapter headings: expected at least one '## ' chapter heading")
        if chapter_heading_count != expected_chapter_count:
            raise NovelForgeError(f"revised volume chapter count mismatch: expected={expected_chapter_count} actual={chapter_heading_count}")
        self._write_json(volume_dir / "volume_revised.json", revised)
        volume.title = revised["title"]
        revised_md = f"# {revised['title']}\n\n{revised['body'].strip()}\n"
        (volume_dir / "volume_revised.md").write_text(revised_md, encoding="utf-8")
        final_review = review
        if not review.get("ready_for_publication", False):
            final_review = self._client_for(series_dir).complete_json(
                task="volume_review",
                messages=[
                    {"role": "system", "content": _json_system()},
                    {"role": "user", "content": self.prompts.render("volume_review", series=state.series.model_dump_json(), manuscript=revised_md)},
                ],
                schema=load_schema("volume_review"),
            )
            self._write_json(volume_dir / "volume_review_final.json", final_review)
        if not force and not final_review.get("ready_for_publication", False):
            volume.status = "reviewed"
            self._save_state(series_dir, state)
            raise NovelForgeError("volume review says not ready for publication after revision; revised draft saved, rerun with force=True to export anyway")
        if not force and _review_has_blocking_issues(final_review):
            volume.status = "reviewed"
            self._save_state(series_dir, state)
            raise NovelForgeError("volume review has major final review issues; revised draft saved, rerun with force=True to export anyway")
        self._update_bible(series_dir, revised_md)
        self._export_kdp(volume_dir, revised["title"], revised_md)
        volume.status = "revised"
        self._save_state(series_dir, state)
        return state

    def continue_series(self, slug: str) -> ProjectState:
        state = self.status(slug)
        if state.current_volume > len(state.series.planned_volumes):
            raise NovelForgeError(f"volume exceeds planned series: volume={state.current_volume} planned={len(state.series.planned_volumes)}")
        current = next((v for v in state.volumes if v.number == state.current_volume), None)
        if current is None or current.status != "revised":
            return self.complete_volume(slug, state.current_volume)
        next_number = state.current_volume + 1
        if next_number > len(state.series.planned_volumes):
            raise NovelForgeError(f"volume exceeds planned series: volume={next_number} planned={len(state.series.planned_volumes)}")
        state.current_volume = next_number
        if not any(v.number == next_number for v in state.volumes):
            planned = next((v for v in state.series.planned_volumes if v.number == next_number), None)
            if planned is None:
                raise NovelForgeError(f"volume exceeds planned series: volume={next_number} planned={len(state.series.planned_volumes)}")
            state.volumes.append(VolumeProgress(number=next_number, title=planned.title))
            self._save_state(self._series_dir(slug), state)
        return self.write_volume(slug, next_number)

    def export_volume(self, slug: str, volume_number: int | None = None) -> Path:
        series_dir = self._series_dir(slug)
        state = self.status(slug)
        number = volume_number or state.current_volume
        volume = next((v for v in state.volumes if v.number == number), None)
        if volume is None:
            raise NovelForgeError(f"volume not found: {number}")
        volume_dir = ensure_dir(series_dir / f"volume_{number:03d}")
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
        bible_path = series_dir / "bible.json"
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
        exports = ensure_dir(volume_dir / "exports")
        clean = manuscript.strip() + "\n"
        (exports / "manuscript.md").write_text(clean, encoding="utf-8")
        text = re.sub(r"^#{1,6}\s+", "", clean, flags=re.MULTILINE)
        (exports / "kdp.txt").write_text(text.strip() + "\n", encoding="utf-8")
        (exports / "metadata.json").write_text(json.dumps({"title": title, "format": "KDP text/markdown/EPUB draft"}, ensure_ascii=False, indent=2), encoding="utf-8")
        NovelForge._write_epub(exports / "book.epub", title, clean)
        NovelForge._write_export_chapters(exports, clean)

    @staticmethod
    def _write_export_chapters(exports: Path, manuscript: str) -> None:
        chapter_root = ensure_dir(exports / "chapters")
        matches = list(re.finditer(r"^##\s+.+$", manuscript, re.MULTILINE))
        for old in chapter_root.glob("chapter_*.md"):
            old.unlink()
        for index, match in enumerate(matches, start=1):
            end = matches[index].start() if index < len(matches) else len(manuscript)
            chapter_text = manuscript[match.start():end].strip() + "\n"
            (chapter_root / f"chapter_{index:03d}.md").write_text(chapter_text, encoding="utf-8")

    @staticmethod
    def _write_epub(path: Path, title: str, manuscript: str) -> None:
        paragraphs = [p.strip() for p in manuscript.split("\n\n") if p.strip()]
        body = "\n".join(f"<p>{html.escape(p).replace(chr(10), '<br/>')}</p>" for p in paragraphs)
        chapter = f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ja">
<head><title>{html.escape(title)}</title></head>
<body>{body}</body>
</html>
'''
        nav = f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ja">
<head><title>{html.escape(title)}</title></head>
<body><nav epub:type="toc"><ol><li><a href="chapter.xhtml">{html.escape(title)}</a></li></ol></nav></body>
</html>
'''
        opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="ja">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="bookid">novel-forge-kdp</dc:identifier><dc:title>{html.escape(title)}</dc:title><dc:language>ja</dc:language></metadata>
  <manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="chapter"/></spine>
</package>
'''
        container = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>
'''
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            zf.writestr("META-INF/container.xml", container)
            zf.writestr("OEBPS/content.opf", opf)
            zf.writestr("OEBPS/nav.xhtml", nav)
            zf.writestr("OEBPS/chapter.xhtml", chapter)

    def _save_state(self, series_dir: Path, state: ProjectState) -> None:
        self._write_json(series_dir / "state.json", state.model_dump())

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
    return len(re.findall(r"^##\s+.+$", markdown, re.MULTILINE))


def _review_has_blocking_issues(review: dict[str, Any]) -> bool:
    return any(str(issue.get("severity", "")).lower() in {"major", "critical", "blocker"} for issue in review.get("issues", []) if isinstance(issue, dict))


def _json_system() -> str:
    return "You are a professional Japanese commercial fiction editor. Return only valid JSON matching the requested schema. Do not use markdown fences."
