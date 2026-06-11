import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from novel_forge_kdp.llm import LLMClientError, parse_json_content
from novel_forge_kdp.schemas import load_schema
from novel_forge_kdp.paths import safe_slug
from novel_forge_kdp.prompts import PromptStore
from novel_forge_kdp.workflow import NovelForge


from tests.fakes import FakeLLM


class FourSceneLLM(FakeLLM):
    def complete_json(self, *, task, messages, schema, temperature=0.4, max_tokens=None):
        if task == "volume_outline":
            self.calls.append({"task": task, "messages": messages, "schema": schema})
            return {
                "volume_number": 1,
                "title": "夜明けの禁書",
                "chapters": [
                    {
                        "number": 1,
                        "title": "第一章",
                        "purpose": "導入",
                        "scenes": [
                            {"number": 1, "title": "一", "pov": "澪", "goal": "g", "conflict": "c", "outcome": "o"},
                            {"number": 2, "title": "二", "pov": "澪", "goal": "g", "conflict": "c", "outcome": "o"},
                        ],
                    },
                    {
                        "number": 2,
                        "title": "第二章",
                        "purpose": "転換",
                        "scenes": [
                            {"number": 1, "title": "三", "pov": "澪", "goal": "g", "conflict": "c", "outcome": "o"},
                            {"number": 2, "title": "四", "pov": "澪", "goal": "g", "conflict": "c", "outcome": "o"},
                        ],
                    },
                ],
            }
        return super().complete_json(task=task, messages=messages, schema=schema, temperature=temperature, max_tokens=max_tokens)


def revised_scene_keys(state):
    return [(scene.chapter, scene.scene) for scene in state.volumes[0].scenes if scene.status == "revised"]


def test_write_volume_max_scenes_counts_only_newly_processed_scenes_on_resume(tmp_path):
    llm = FourSceneLLM()
    forge = NovelForge(workspace=tmp_path, llm=llm)
    forge.plan_series("星 図書館")

    first = forge.write_volume("hoshikuzu-library", max_scenes=2)
    assert revised_scene_keys(first) == [(1, 1), (1, 2)]
    assert first.volumes[0].status == "outlined"

    second = forge.write_volume("hoshikuzu-library", max_scenes=1)
    assert revised_scene_keys(second) == [(1, 1), (1, 2), (2, 1)]
    assert second.volumes[0].status == "outlined"

    final = forge.write_volume("hoshikuzu-library")
    assert revised_scene_keys(final) == [(1, 1), (1, 2), (2, 1), (2, 2)]
    assert final.volumes[0].status == "drafted"


def test_safe_slug_normalizes_names():
    assert safe_slug(" 星屑の図書館!! KDP ") == "kdp"
    assert safe_slug("Novel Forge 01") == "novel-forge-01"
    assert safe_slug("   ") == "series"


def test_parse_json_content_accepts_plain_json_and_code_fences():
    assert parse_json_content('{"ok": true}') == {"ok": True}
    assert parse_json_content('```json\n{"ok": true}\n```') == {"ok": True}
    with pytest.raises(LLMClientError):
        parse_json_content('not json')


def test_prompt_store_renders_markdown_templates(tmp_path):
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "demo.md").write_text("# Demo\nKeyword: {{ keyword }}", encoding="utf-8")
    store = PromptStore(prompts)
    assert "Keyword: 魔法" in store.render("demo", keyword="魔法")


def test_generation_schemas_bound_production_workload():
    series_schema = load_schema("series_plan")
    volume_schema = load_schema("volume_outline")
    assert series_schema["properties"]["planned_volumes"]["maxItems"] == 3
    assert volume_schema["properties"]["chapters"]["maxItems"] == 2
    assert volume_schema["properties"]["chapters"]["items"]["properties"]["scenes"]["maxItems"] == 2

    too_many_chapters = {
        "volume_number": 1,
        "title": "Too Long",
        "chapters": [
            {"number": i, "title": f"Chapter {i}", "purpose": "p", "scenes": [{"number": 1, "title": "S", "pov": "p", "goal": "g", "conflict": "c", "outcome": "o"}]}
            for i in range(1, 6)
        ],
    }
    assert list(Draft202012Validator(volume_schema).iter_errors(too_many_chapters))


def test_new_series_creates_resumeable_scene_workflow(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM(planned_volume_count=2))
    state = forge.plan_series("星 図書館")
    assert state.series.title == "星屑の図書館"
    assert (tmp_path / "hoshikuzu-library" / "state.json").exists()

    state = forge.write_volume("hoshikuzu-library")
    volume_dir = tmp_path / "hoshikuzu-library" / "volume_001"
    assert (volume_dir / "outline.json").exists()
    assert (volume_dir / "chapters" / "chapter_001" / "scene_001.md").read_text(encoding="utf-8").startswith("# 禁書の囁き")
    chapter_md = (volume_dir / "chapters" / "chapter_001" / "chapter.md").read_text(encoding="utf-8")
    assert chapter_md.startswith("## 星の降る閲覧室")
    assert "# 禁書の囁き" in chapter_md
    assert state.volumes[0].status == "drafted"

    loaded = forge.status("hoshikuzu-library")
    assert loaded.volumes[0].scenes[0].status == "revised"


def test_complete_volume_reviews_revises_exports_and_updates_bible(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM(planned_volume_count=2))
    forge.plan_series("星 図書館")
    forge.write_volume("hoshikuzu-library")

    state = forge.complete_volume("hoshikuzu-library")
    series_dir = tmp_path / "hoshikuzu-library"
    volume_dir = series_dir / "volume_001"

    assert state.volumes[0].status == "revised"
    assert (volume_dir / "volume_review.json").exists()
    assert (volume_dir / "volume_revised.md").read_text(encoding="utf-8").startswith("# 夜明けの禁書")
    assert (volume_dir / "exports" / "manuscript.md").exists()
    assert (volume_dir / "exports" / "kdp.txt").read_text(encoding="utf-8").startswith("夜明けの禁書")
    assert (volume_dir / "exports" / "book.epub").read_bytes().startswith(b"PK")
    exported_chapter = (volume_dir / "exports" / "chapters" / "chapter_001.md").read_text(encoding="utf-8")
    assert exported_chapter.startswith("## 星の降る閲覧室")
    assert "# 禁書の囁き" in exported_chapter
    bible = json.loads((series_dir / "bible.json").read_text(encoding="utf-8"))
    assert bible["characters"][0]["name"] == "澪"


def test_continue_series_revises_unfinished_or_starts_next_volume(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM(planned_volume_count=2))
    forge.plan_series("星 図書館")
    first = forge.continue_series("hoshikuzu-library")
    assert first.volumes[0].status == "revised"

    second = forge.continue_series("hoshikuzu-library")
    assert second.current_volume == 2
    assert any(v.number == 2 for v in second.volumes)
    assert (tmp_path / "hoshikuzu-library" / "volume_002" / "outline.json").exists()
