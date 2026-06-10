import json
from pathlib import Path

import pytest

from novel_forge_kdp.llm import LLMClientError, parse_json_content
from novel_forge_kdp.paths import safe_slug
from novel_forge_kdp.prompts import PromptStore
from novel_forge_kdp.workflow import NovelForge


class FakeLLM:
    def __init__(self):
        self.calls = []

    def complete_json(self, *, task, messages, schema, temperature=0.4, max_tokens=None):
        self.calls.append({"task": task, "messages": messages, "schema": schema})
        if task == "series_plan":
            return {
                "title": "星屑の図書館",
                "slug": "hoshikuzu-library",
                "logline": "失われた物語を取り戻す司書の冒険。",
                "genre": "ライト文芸ファンタジー",
                "target_audience": "KDP読者",
                "themes": ["記憶", "再生"],
                "selling_points": ["謎解き", "成長"],
                "world": {"summary": "本が星になる都市。", "rules": ["禁書は夜に目覚める"]},
                "main_characters": [{"name": "澪", "role": "司書", "arc": "孤独から連帯へ"}],
                "planned_volumes": [{"number": 1, "title": "夜明けの禁書", "premise": "禁書を巡る第一巻。"}],
            }
        if task == "volume_outline":
            return {
                "volume_number": 1,
                "title": "夜明けの禁書",
                "chapters": [
                    {
                        "number": 1,
                        "title": "星の降る閲覧室",
                        "purpose": "導入",
                        "scenes": [
                            {"number": 1, "title": "禁書の囁き", "pov": "澪", "goal": "禁書を見つける", "conflict": "封印が解ける", "outcome": "旅立ちを決意"}
                        ],
                    }
                ],
            }
        if task == "scene_draft":
            return {"title": "禁書の囁き", "body": "澪は夜の図書館で、星の匂いがする本を開いた。", "continuity_notes": ["禁書が登場"]}
        if task == "review":
            return {"score": 82, "strengths": ["雰囲気"], "issues": [{"severity": "minor", "point": "描写を増やす"}], "revision_brief": "情景描写を一段増やす。"}
        if task == "revise_scene":
            return {"title": "禁書の囁き", "body": "澪は夜の図書館で、星の匂いがする本を開いた。窓辺には青白い光が降り積もっていた。", "changes": ["情景描写を追加"]}
        raise AssertionError(task)


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


def test_new_series_creates_resumeable_scene_workflow(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    state = forge.plan_series("星 図書館")
    assert state.series.title == "星屑の図書館"
    assert (tmp_path / "hoshikuzu-library" / "state.json").exists()

    state = forge.write_volume("hoshikuzu-library")
    volume_dir = tmp_path / "hoshikuzu-library" / "volume_001"
    assert (volume_dir / "outline.json").exists()
    assert (volume_dir / "chapters" / "chapter_001" / "scene_001.md").read_text(encoding="utf-8").startswith("# 禁書の囁き")
    assert state.volumes[0].status == "drafted"

    loaded = forge.status("hoshikuzu-library")
    assert loaded.volumes[0].scenes[0].status == "revised"
