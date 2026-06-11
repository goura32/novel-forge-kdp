"""Tests for LLMTaskRunner."""

import pytest

from novel_forge_kdp.llm_task_runner import LLMTaskRunner, UnknownTaskError
from novel_forge_kdp.prompts import PromptStore


class RecordingClient:
    def __init__(self):
        self.calls = []

    def complete_json(self, *, task, messages, schema, temperature=0.4, max_tokens=None):
        self.calls.append(
            {
                "task": task,
                "messages": messages,
                "schema": schema,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return {"ok": True}


def test_task_runner_uses_task_spec_prompt_and_schema(tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "scene_draft.md").write_text("Scene: {{ scene }}", encoding="utf-8")

    client = RecordingClient()
    runner = LLMTaskRunner(
        client=client,
        prompts=PromptStore(prompts_dir),
        system_prompt="SYSTEM",
    )

    result = runner.complete("scene_draft", scene="opening")

    assert result == {"ok": True}
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["task"] == "scene_draft"
    assert call["messages"] == [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "Scene: opening"},
    ]
    assert call["schema"]["type"] == "object"


def test_task_runner_maps_revise_scene_to_revised_scene_schema(tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "revise_scene.md").write_text("Draft={{ draft }} Review={{ review }}", encoding="utf-8")

    client = RecordingClient()
    runner = LLMTaskRunner(client=client, prompts=PromptStore(prompts_dir), system_prompt="SYS")

    runner.complete("revise_scene", draft="D", review="R")

    call = client.calls[0]
    assert call["task"] == "revise_scene"
    assert "title" in call["schema"]["required"]
    assert "body" in call["schema"]["required"]


def test_task_runner_rejects_unknown_task(tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    runner = LLMTaskRunner(client=RecordingClient(), prompts=PromptStore(prompts_dir), system_prompt="SYS")

    with pytest.raises(UnknownTaskError, match="unknown LLM task"):
        runner.complete("missing_task")



def test_scene_llm_calls_delegates_all_steps_to_task_runner():
    from novel_forge_kdp.scene_workflow import SceneLlmCalls

    calls = []

    class Runner:
        def complete(self, task_name, **context):
            calls.append((task_name, context))
            return {"task": task_name}

    scene_calls = SceneLlmCalls(runner=Runner())

    state = type("State", (), {"series": type("Series", (), {"model_dump_json": lambda self: "SERIES"})()})()
    outline = type("Outline", (), {"model_dump_json": lambda self: "OUTLINE"})()
    scene = type("Scene", (), {"model_dump_json": lambda self: "SCENE"})()

    assert scene_calls.draft(state=state, outline=outline, scene=scene) == {"task": "scene_draft"}
    assert scene_calls.review(draft_data={"body": "draft"}) == {"task": "review"}
    assert scene_calls.revise(draft_text="DRAFT", review_text="REVIEW") == {"task": "revise_scene"}

    assert calls == [
        ("scene_draft", {"series": "SERIES", "outline": "OUTLINE", "scene": "SCENE"}),
        ("review", {"text": '{"body": "draft"}'}),
        ("revise_scene", {"draft": "DRAFT", "review": "REVIEW"}),
    ]
