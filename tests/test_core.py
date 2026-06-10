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
                "planned_volumes": [
                    {"number": 1, "title": "夜明けの禁書", "premise": "禁書を巡る第一巻。"},
                    {"number": 2, "title": "黄昏の目録", "premise": "失われた目録を巡る第二巻。"},
                ],
            }
        if task == "volume_outline":
            volume_number = 1
            for m in messages:
                if "対象巻: 2" in m.get("content", ""):
                    volume_number = 2
            return {
                "volume_number": volume_number,
                "title": "夜明けの禁書" if volume_number == 1 else "黄昏の目録",
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
        if task == "volume_review":
            return {"score": 88, "strengths": ["統一感"], "issues": [{"severity": "minor", "point": "終盤の余韻を補強"}], "revision_brief": "巻末の余韻を増やす。", "ready_for_publication": True}
        if task == "revise_volume":
            return {"title": "夜明けの禁書", "body": "## 星の降る閲覧室\n\n# 禁書の囁き\n\n澪は夜の図書館で、星の匂いがする本を開いた。余韻が残った。", "changes": ["巻末の余韻を補強"]}
        if task == "bible_update":
            return {
                "characters": [{"name": "澪", "description": "星の司書", "status": "旅立ちを決意"}],
                "terms": [{"term": "禁書", "description": "星の匂いがする本"}],
                "foreshadowing": [{"item": "青白い光", "status": "open"}],
                "continuity_notes": ["澪は禁書を開いた"],
            }
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
    chapter_md = (volume_dir / "chapters" / "chapter_001" / "chapter.md").read_text(encoding="utf-8")
    assert chapter_md.startswith("## 星の降る閲覧室")
    assert "# 禁書の囁き" in chapter_md
    assert state.volumes[0].status == "drafted"

    loaded = forge.status("hoshikuzu-library")
    assert loaded.volumes[0].scenes[0].status == "revised"


def test_complete_volume_reviews_revises_exports_and_updates_bible(tmp_path):
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
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
    forge = NovelForge(workspace=tmp_path, llm=FakeLLM())
    forge.plan_series("星 図書館")
    first = forge.continue_series("hoshikuzu-library")
    assert first.volumes[0].status == "revised"

    second = forge.continue_series("hoshikuzu-library")
    assert second.current_volume == 2
    assert any(v.number == 2 for v in second.volumes)
    assert (tmp_path / "hoshikuzu-library" / "volume_002" / "outline.json").exists()
