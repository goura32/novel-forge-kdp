from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class TaskSpec:
    task_name: str
    prompt_template_name: str
    schema_name: str
    context_keys: Sequence[str] = ()


TASK_SPECS: list[TaskSpec] = [
    TaskSpec(
        task_name="series_plan",
        prompt_template_name="series_plan",
        schema_name="series_plan",
    ),
    TaskSpec(
        task_name="volume_outline",
        prompt_template_name="volume_outline",
        schema_name="volume_outline",
    ),
    TaskSpec(
        task_name="scene_draft",
        prompt_template_name="scene_draft",
        schema_name="scene_draft",
    ),
    TaskSpec(
        task_name="review",
        prompt_template_name="review",
        schema_name="review",
    ),
    TaskSpec(
        task_name="revise_scene",
        prompt_template_name="revise_scene",
        schema_name="revised_scene",
    ),
    TaskSpec(
        task_name="volume_review",
        prompt_template_name="volume_review",
        schema_name="volume_review",
    ),
    TaskSpec(
        task_name="revise_volume",
        prompt_template_name="revise_volume",
        schema_name="revised_volume",
    ),
    TaskSpec(
        task_name="bible_update",
        prompt_template_name="bible_update",
        schema_name="bible_update",
    ),
]


def lookup_task(name: str) -> "TaskSpec | None":
    for spec in TASK_SPECS:
        if spec.task_name == name:
            return spec
    return None
