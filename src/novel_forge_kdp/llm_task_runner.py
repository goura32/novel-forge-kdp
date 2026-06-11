from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .prompts import PromptStore
from .schemas import load_schema
from .tasks import lookup_task


class UnknownTaskError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMTaskRunner:
    """Runs a named LLM task through TaskSpec -> prompt -> schema mapping."""

    client: Any
    prompts: PromptStore
    system_prompt: str

    def complete(
        self,
        task_name: str,
        *,
        temperature: float = 0.4,
        max_tokens: int | None = None,
        **context: Any,
    ) -> Any:
        spec = lookup_task(task_name)
        if spec is None:
            raise UnknownTaskError(f"unknown LLM task: {task_name}")
        prompt = self.prompts.render(spec.prompt_template_name, **context)
        return self.client.complete_json(
            task=spec.task_name,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            schema=load_schema(spec.schema_name),
            temperature=temperature,
            max_tokens=max_tokens,
        )
