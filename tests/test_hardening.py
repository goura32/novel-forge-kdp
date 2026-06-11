import importlib.util
import json
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_forge_kdp.cli import app
from novel_forge_kdp.llm import LLMClientError, OllamaOpenAIClient, build_chat_payload
from novel_forge_kdp.workflow import NovelForge, NovelForgeError
from novel_forge_kdp.models import VolumeProgress


from tests.fakes import (
    DuplicateChapterOutlineLLM,
    DuplicateSceneOutlineLLM,
    FakeLLM,
    MismatchedOutlineLLM,
    NoChapterHeadingRevisedVolumeLLM,
    NotReadyLLM,
    NotReadyThenReadyLLM,
    ReadyWithMajorIssueLLM,
    TitleChangingLLM,
    TooManyChapterHeadingsRevisedVolumeLLM,
)

def test_slug_traversal_is_rejected(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    with pytest.raises(NovelForgeError):
        forge.status("../outside")
    with pytest.raises(NovelForgeError):
        forge.write_volume("bad/path")


def test_plan_series_refuses_existing_slug_without_overwrite(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    forge.plan_series("星 図書館")
    with pytest.raises(NovelForgeError):
        forge.plan_series("星 図書館")


def test_write_volume_rejects_outline_volume_number_mismatch(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=MismatchedOutlineLLM())
    forge.plan_series("星 図書館")
    with pytest.raises(NovelForgeError, match="volume outline number mismatch"):
        forge.write_volume("hoshikuzu-library", volume_number=2)


def test_write_volume_rejects_duplicate_chapter_numbers(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=DuplicateChapterOutlineLLM())
    forge.plan_series("星 図書館")
    with pytest.raises(NovelForgeError, match="duplicate chapter number"):
        forge.write_volume("hoshikuzu-library")


def test_write_volume_rejects_duplicate_scene_numbers(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=DuplicateSceneOutlineLLM())
    forge.plan_series("星 図書館")
    with pytest.raises(NovelForgeError, match="duplicate scene number"):
        forge.write_volume("hoshikuzu-library")


def test_write_volume_rejects_cached_outline_over_workload_bounds(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    forge.plan_series("星 図書館")
    volume_dir = tmp_path / "hoshikuzu-library" / "volume_001"
    volume_dir.mkdir()
    NovelForge._write_json(
        volume_dir / "outline.json",
        {
            "volume_number": 1,
            "title": "Too Long",
            "chapters": [
                {"number": i, "title": f"Chapter {i}", "purpose": "p", "scenes": [{"number": 1, "title": "S", "pov": "p", "goal": "g", "conflict": "c", "outcome": "o"}]}
                for i in range(1, 4)
            ],
        },
    )

    with pytest.raises(NovelForgeError, match="too many chapters"):
        forge.write_volume("hoshikuzu-library")


def test_write_volume_rejects_cached_outline_with_no_chapters(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    forge.plan_series("星 図書館")
    volume_dir = tmp_path / "hoshikuzu-library" / "volume_001"
    volume_dir.mkdir()
    NovelForge._write_json(volume_dir / "outline.json", {"volume_number": 1, "title": "Empty", "chapters": []})

    with pytest.raises(NovelForgeError, match="outline has no chapters"):
        forge.write_volume("hoshikuzu-library")


def test_write_volume_rejects_cached_outline_with_empty_chapter(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    forge.plan_series("星 図書館")
    volume_dir = tmp_path / "hoshikuzu-library" / "volume_001"
    volume_dir.mkdir()
    NovelForge._write_json(volume_dir / "outline.json", {"volume_number": 1, "title": "Empty", "chapters": [{"number": 1, "title": "Empty", "purpose": "p", "scenes": []}]})

    with pytest.raises(NovelForgeError, match="chapter has no scenes"):
        forge.write_volume("hoshikuzu-library")


def test_continue_series_refuses_unplanned_volume_past_series_cap(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    forge.plan_series("星 図書館")
    state = forge.status("hoshikuzu-library")
    state.current_volume = 4
    NovelForge._write_json(tmp_path / "hoshikuzu-library" / "state.json", state.model_dump())

    with pytest.raises(NovelForgeError, match="volume exceeds planned series"):
        forge.continue_series("hoshikuzu-library")


def test_continue_series_refuses_to_advance_beyond_last_planned_volume(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    forge.plan_series("星 図書館")
    state = forge.status("hoshikuzu-library")
    state.current_volume = len(state.series.planned_volumes)
    state.volumes = [VolumeProgress(number=state.current_volume, title="最終巻", status="revised")]
    NovelForge._write_json(tmp_path / "hoshikuzu-library" / "state.json", state.model_dump())

    with pytest.raises(NovelForgeError, match="volume exceeds planned series"):
        forge.continue_series("hoshikuzu-library")


def test_write_volume_refuses_unplanned_volume_number(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    forge.plan_series("星 図書館")

    with pytest.raises(NovelForgeError, match="volume exceeds planned series"):
        forge.write_volume("hoshikuzu-library", volume_number=99)


def test_atomic_json_write_keeps_backup(tmp_path):
    path = tmp_path / "state.json"
    NovelForge._write_json(path, {"version": 1})
    NovelForge._write_json(path, {"version": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"version": 2}
    assert json.loads(path.with_suffix(".json.bak").read_text(encoding="utf-8")) == {"version": 1}


def test_complete_volume_fails_when_revised_scene_file_missing(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    forge.plan_series("星 図書館")
    forge.write_volume("hoshikuzu-library")
    scene = tmp_path / "hoshikuzu-library" / "volume_001" / "chapters" / "chapter_001" / "scene_001.md"
    scene.unlink()
    with pytest.raises(NovelForgeError, match="missing scene manuscript"):
        forge.complete_volume("hoshikuzu-library")


def test_complete_volume_rejects_scene_path_traversal(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    state = forge.plan_series("星 図書館")
    forge.write_volume("hoshikuzu-library")
    outside = tmp_path / "secret.txt"
    outside.write_text("SECRET", encoding="utf-8")
    state = forge.status("hoshikuzu-library")
    state.volumes[0].scenes[0].path = "../secret.txt"
    NovelForge._write_json(tmp_path / "hoshikuzu-library" / "state.json", state.model_dump())
    with pytest.raises(NovelForgeError, match="escapes series directory"):
        forge.complete_volume("hoshikuzu-library")


def test_quality_gate_blocks_export_when_review_not_ready(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=NotReadyLLM())
    forge.plan_series("星 図書館")
    forge.write_volume("hoshikuzu-library")
    with pytest.raises(NovelForgeError, match="not ready for publication"):
        forge.complete_volume("hoshikuzu-library")
    assert not (tmp_path / "hoshikuzu-library" / "volume_001" / "exports" / "book.epub").exists()


def test_force_complete_volume_exports_even_when_review_not_ready(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=NotReadyLLM())
    forge.plan_series("星 図書館")
    forge.write_volume("hoshikuzu-library")
    state = forge.complete_volume("hoshikuzu-library", force=True)
    assert state.volumes[0].status == "revised"
    epub = tmp_path / "hoshikuzu-library" / "volume_001" / "exports" / "book.epub"
    with zipfile.ZipFile(epub) as zf:
        assert "OEBPS/content.opf" in zf.namelist()


def test_kdp_text_removes_all_markdown_heading_markers(tmp_path):
    NovelForge._export_kdp(tmp_path, "Title", "# Title\n\n## 第1章\n\n### Scene\n\n本文 #タグ\n")
    text = (tmp_path / "exports" / "kdp.txt").read_text(encoding="utf-8")
    assert text.splitlines() == ["Title", "", "第1章", "", "Scene", "", "本文 #タグ"]


def test_complete_volume_rejects_revised_volume_without_chapter_headings(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=NoChapterHeadingRevisedVolumeLLM())
    forge.plan_series("星 図書館")
    forge.write_volume("hoshikuzu-library")
    with pytest.raises(NovelForgeError, match="revised volume has no chapter headings"):
        forge.complete_volume("hoshikuzu-library", force=True)


def test_complete_volume_rejects_revised_volume_chapter_count_mismatch(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=TooManyChapterHeadingsRevisedVolumeLLM())
    forge.plan_series("星 図書館")
    forge.write_volume("hoshikuzu-library")
    with pytest.raises(NovelForgeError, match="revised volume chapter count mismatch"):
        forge.complete_volume("hoshikuzu-library", force=True)


def test_complete_volume_persists_revised_title_for_reexport_metadata(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=TitleChangingLLM())
    forge.plan_series("星 図書館")
    forge.write_volume("hoshikuzu-library")
    forge.complete_volume("hoshikuzu-library")

    state = forge.status("hoshikuzu-library")
    assert state.volumes[0].title == "改題後タイトル"

    forge.export_volume("hoshikuzu-library")
    metadata = json.loads((tmp_path / "hoshikuzu-library" / "volume_001" / "exports" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["title"] == "改題後タイトル"


def test_make_smoke_workspace_help_does_not_create_workspace(tmp_path, monkeypatch, capsys):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "make_smoke_workspace.py"
    spec = importlib.util.spec_from_file_location("make_smoke_workspace", script_path)
    assert spec is not None and spec.loader is not None
    make_smoke_workspace = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(make_smoke_workspace)

    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        make_smoke_workspace.main(["--help"])

    assert excinfo.value.code == 0
    assert "usage:" in capsys.readouterr().out
    assert not Path("smoke_workspace").exists()


def test_make_smoke_workspace_rejects_slug_path_traversal(tmp_path):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "make_smoke_workspace.py"
    spec = importlib.util.spec_from_file_location("make_smoke_workspace", script_path)
    assert spec is not None and spec.loader is not None
    make_smoke_workspace = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(make_smoke_workspace)

    with pytest.raises(ValueError, match="invalid series slug"):
        make_smoke_workspace.build_smoke_workspace(tmp_path, "../outside")
    assert not (tmp_path.parent / "outside").exists()


def test_complete_volume_revises_and_rechecks_before_export_when_initial_review_not_ready(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=NotReadyThenReadyLLM())
    forge.plan_series("星 図書館")
    forge.write_volume("hoshikuzu-library")
    state = forge.complete_volume("hoshikuzu-library")
    volume_dir = tmp_path / "hoshikuzu-library" / "volume_001"
    assert state.volumes[0].status == "revised"
    assert (volume_dir / "volume_review.json").exists()
    assert (volume_dir / "volume_review_final.json").exists()
    assert json.loads((volume_dir / "volume_review_final.json").read_text(encoding="utf-8"))["ready_for_publication"] is True
    assert (volume_dir / "exports" / "book.epub").exists()


def test_complete_volume_blocks_major_final_review_issue_even_if_ready_flag_true(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=ReadyWithMajorIssueLLM())
    forge.plan_series("星 図書館")
    forge.write_volume("hoshikuzu-library")
    with pytest.raises(NovelForgeError, match="major final review issues"):
        forge.complete_volume("hoshikuzu-library")
    assert not (tmp_path / "hoshikuzu-library" / "volume_001" / "exports" / "book.epub").exists()


def test_ollama_client_disables_thinking_for_json_mode(monkeypatch, tmp_path):
    seen_payloads = []

    class FakeResponse:
        text = '{"choices":[{"message":{"content":"{}"}}]}'
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    class FakeClient:
        def __init__(self, timeout):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, *args, **kwargs):
            seen_payloads.append(kwargs["json"])
            return FakeResponse()

    monkeypatch.setattr("httpx.Client", FakeClient)
    client = OllamaOpenAIClient(log_dir=tmp_path)
    assert client.complete_json(task="x", messages=[{"role": "user", "content": "x"}], schema={"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}) == {"ok": True}
    assert seen_payloads[0]["think"] is False


def test_build_chat_payload_appends_schema_hint_without_mutating_messages():
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "return json"}]
    schema = {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}

    payload = build_chat_payload(model="m", messages=messages, schema=schema, temperature=0.2, max_tokens=None)

    assert payload["model"] == "m"
    assert payload["temperature"] == 0.2
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["think"] is False
    assert "max_tokens" not in payload
    assert "JSON Schema to satisfy exactly" in payload["messages"][1]["content"]
    assert messages[1]["content"] == "return json"


def test_llm_non_json_http_200_becomes_llm_client_error(monkeypatch, tmp_path):
    class FakeResponse:
        text = "<html>bad gateway</html>"
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            raise ValueError("not json")

    class FakeClient:
        def __init__(self, timeout):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("httpx.Client", FakeClient)
    client = OllamaOpenAIClient(log_dir=tmp_path)
    with pytest.raises(LLMClientError, match="response was not JSON"):
        client.complete_json(task="x", messages=[{"role": "user", "content": "x"}], schema={"type": "object"})


def test_cli_missing_series_returns_clean_error(tmp_path):
    result = CliRunner().invoke(app, ["status", "missing", "--workspace", str(tmp_path)])
    assert result.exit_code == 1
    assert "ERROR:" in result.output
    assert "Traceback" not in result.output


def test_cli_missing_export_volume_returns_clean_error(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    forge.plan_series("星 図書館")
    result = CliRunner().invoke(app, ["export-volume", "hoshikuzu-library", "--workspace", str(tmp_path), "--volume", "99"])
    assert result.exit_code == 1
    assert "ERROR:" in result.output
    assert "volume not found: 99" in result.output
    assert "Traceback" not in result.output
