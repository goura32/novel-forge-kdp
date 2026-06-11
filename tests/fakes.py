from __future__ import annotations


class FakeLLM:
    def __init__(self, planned_volume_count: int = 1) -> None:
        self.calls = []
        self.planned_volume_count = planned_volume_count

    def complete_json(self, *, task, messages, schema, temperature=0.4, max_tokens=None):
        self.calls.append({"task": task, "messages": messages, "schema": schema})
        if task == "series_plan":
            planned = [{"number": 1, "title": "夜明けの禁書", "premise": "禁書を巡る第一巻。"}]
            if self.planned_volume_count >= 2:
                planned.append({"number": 2, "title": "黄昏の目録", "premise": "失われた目録を巡る第二巻。"})
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
                "planned_volumes": planned,
            }
        if task == "volume_outline":
            volume_number = 1
            for message in messages:
                if "対象巻: 2" in message.get("content", ""):
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


class FakeSceneLlmCalls:
    def __init__(self, draft=None, review_status=None, revised=None) -> None:
        self.draft_response = draft or {
            "title": "Draft of scene",
            "body": "Draft content.",
        }
        self.review_status = review_status
        self.revised_response = revised or {
            "title": "Revised scene",
            "body": self.draft_response.get("body", ""),
        }

    def draft(self, *, state, outline, scene):
        return self.draft_response

    def review(self, *, draft_data):
        if self.review_status is None:
            return None
        if isinstance(self.review_status, str):
            return {"ready_for_publication": self.review_status == "ready_for_publication"}
        return self.review_status

    def revise(self, *, draft_text, review_text):
        return self.revised_response


class NotReadyLLM(FakeLLM):
    def complete_json(self, *, task, messages, schema, temperature=0.4, max_tokens=None):
        if task == "volume_review":
            self.calls.append({"task": task, "messages": messages, "schema": schema})
            return {"score": 62, "strengths": ["雰囲気"], "issues": [{"severity": "major", "point": "構成の弱さ"}], "revision_brief": "構成を再調整する。", "ready_for_publication": False}
        return super().complete_json(task=task, messages=messages, schema=schema, temperature=temperature, max_tokens=max_tokens)


class MismatchedOutlineLLM(FakeLLM):
    def complete_json(self, *, task, messages, schema, temperature=0.4, max_tokens=None):
        if task == "series_plan":
            data = super().complete_json(task=task, messages=messages, schema=schema, temperature=temperature, max_tokens=max_tokens)
            data["planned_volumes"].append({"number": 2, "title": "黄昏の目録", "premise": "第二巻。"})
            return data
        if task == "volume_outline":
            data = super().complete_json(task=task, messages=messages, schema=schema, temperature=temperature, max_tokens=max_tokens)
            data["volume_number"] = 1
            return data
        return super().complete_json(task=task, messages=messages, schema=schema, temperature=temperature, max_tokens=max_tokens)


class DuplicateChapterOutlineLLM(FakeLLM):
    def complete_json(self, *, task, messages, schema, temperature=0.4, max_tokens=None):
        if task == "volume_outline":
            return {
                "volume_number": 1,
                "title": "夜明けの禁書",
                "chapters": [
                    {"number": 1, "title": "一", "purpose": "導入", "scenes": [{"number": 1, "title": "A", "pov": "澪", "goal": "g", "conflict": "c", "outcome": "o"}]},
                    {"number": 1, "title": "二", "purpose": "重複", "scenes": [{"number": 1, "title": "B", "pov": "澪", "goal": "g", "conflict": "c", "outcome": "o"}]},
                ],
            }
        return super().complete_json(task=task, messages=messages, schema=schema, temperature=temperature, max_tokens=max_tokens)


class DuplicateSceneOutlineLLM(FakeLLM):
    def complete_json(self, *, task, messages, schema, temperature=0.4, max_tokens=None):
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
                            {"number": 1, "title": "A", "pov": "澪", "goal": "g", "conflict": "c", "outcome": "o"},
                            {"number": 1, "title": "B", "pov": "澪", "goal": "g", "conflict": "c", "outcome": "o"},
                        ],
                    }
                ],
            }
        return super().complete_json(task=task, messages=messages, schema=schema, temperature=temperature, max_tokens=max_tokens)


class NoChapterHeadingRevisedVolumeLLM(FakeLLM):
    def complete_json(self, *, task, messages, schema, temperature=0.4, max_tokens=None):
        if task == "revise_volume":
            return {"title": "夜明けの禁書", "body": "# 禁書の囁き\n\n章見出しなしの本文。", "changes": ["章見出しを欠落させた"]}
        return super().complete_json(task=task, messages=messages, schema=schema, temperature=temperature, max_tokens=max_tokens)


class TooManyChapterHeadingsRevisedVolumeLLM(FakeLLM):
    def complete_json(self, *, task, messages, schema, temperature=0.4, max_tokens=None):
        if task == "revise_volume":
            return {"title": "夜明けの禁書", "body": "## 第一章\n\n本文。\n\n## 第二章\n\n本文。", "changes": ["章を増やした"]}
        return super().complete_json(task=task, messages=messages, schema=schema, temperature=temperature, max_tokens=max_tokens)


class TitleChangingLLM(FakeLLM):
    def complete_json(self, *, task, messages, schema, temperature=0.4, max_tokens=None):
        if task == "revise_volume":
            return {"title": "改題後タイトル", "body": "## 星の降る閲覧室\n\n本文。", "changes": ["タイトル変更"]}
        return super().complete_json(task=task, messages=messages, schema=schema, temperature=temperature, max_tokens=max_tokens)


class NotReadyThenReadyLLM(FakeLLM):
    def __init__(self) -> None:
        super().__init__()
        self.volume_review_calls = 0

    def complete_json(self, *, task, messages, schema, temperature=0.4, max_tokens=None):
        if task == "volume_review":
            self.calls.append({"task": task, "messages": messages, "schema": schema})
            self.volume_review_calls += 1
            if self.volume_review_calls == 1:
                return {"score": 62, "strengths": ["雰囲気"], "issues": [{"severity": "major", "point": "構成の弱さ"}], "revision_brief": "構成を再調整する。", "ready_for_publication": False}
            return {"score": 86, "strengths": ["改稿で構成が改善"], "issues": [{"severity": "minor", "point": "軽微な表記ゆれ"}], "revision_brief": "軽微な表記だけ確認。", "ready_for_publication": True}
        return super().complete_json(task=task, messages=messages, schema=schema, temperature=temperature, max_tokens=max_tokens)


class ReadyWithMajorIssueLLM(FakeLLM):
    def __init__(self) -> None:
        super().__init__()
        self.volume_review_calls = 0

    def complete_json(self, *, task, messages, schema, temperature=0.4, max_tokens=None):
        if task == "volume_review":
            self.calls.append({"task": task, "messages": messages, "schema": schema})
            self.volume_review_calls += 1
            if self.volume_review_calls == 1:
                return {"score": 70, "strengths": ["雰囲気"], "issues": [{"severity": "minor", "point": "軽微"}], "revision_brief": "改稿。", "ready_for_publication": False}
            return {"score": 85, "strengths": ["改善"], "issues": [{"severity": "major", "point": "重大な重複が残っている"}], "revision_brief": "重大問題を直す。", "ready_for_publication": True}
        return super().complete_json(task=task, messages=messages, schema=schema, temperature=temperature, max_tokens=max_tokens)
