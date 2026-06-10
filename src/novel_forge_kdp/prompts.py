from __future__ import annotations

from pathlib import Path
from string import Template


class PromptStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).with_name("prompts")

    def render(self, name: str, **values: object) -> str:
        path = self.root / f"{name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Prompt template not found: {path}")
        text = path.read_text(encoding="utf-8")
        for key, value in values.items():
            text = text.replace("{{ " + key + " }}", str(value))
            text = text.replace("{{" + key + "}}", str(value))
        return Template(text).safe_substitute({k: str(v) for k, v in values.items()})
