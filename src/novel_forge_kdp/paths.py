from __future__ import annotations

import hashlib
import re
from pathlib import Path


SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class PathSafetyError(ValueError):
    pass


def safe_slug(value: str, fallback: str = "series") -> str:
    asciiish = value.strip().lower().encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9_-]+", "-", asciiish).strip("-_")
    if slug:
        return slug[:128]
    if not value.strip():
        return fallback
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"{fallback}-{digest}"


def validate_slug(slug: str) -> str:
    if not SLUG_RE.fullmatch(slug):
        raise PathSafetyError(f"invalid series slug: {slug!r}")
    return slug


def safe_child_dir(parent: Path, slug: str) -> Path:
    validate_slug(slug)
    root = parent.resolve()
    child = (root / slug).resolve()
    if child != root / slug or root not in child.parents:
        raise PathSafetyError(f"series path escapes workspace: {slug!r}")
    return child


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
