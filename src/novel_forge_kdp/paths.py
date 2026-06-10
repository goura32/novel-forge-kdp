from __future__ import annotations

import re
from pathlib import Path


def safe_slug(value: str, fallback: str = "series") -> str:
    asciiish = value.strip().lower().encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", asciiish).strip("-")
    return slug or fallback


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
