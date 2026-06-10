from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_ROOT = Path(__file__).with_name("schemas")


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_ROOT / f"{name}.json").read_text(encoding="utf-8"))
