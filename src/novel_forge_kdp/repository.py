"""novel_forge_kdp.repository: JSON persistence for ProjectState.

Responsibilities:
- Atomic file save (write to tmp → os.fsync → hardlink current as .bak then replace).
- Safe directory creation before writes.
- ProjectState serialization / deserialization with pydantic model_dump / model_validate_json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import ProjectState


class StateStore:
    """Low-level JSON file reader / writer."""

    def load(self, path: "Path") -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"state file not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, path: "Path", data: dict[str, Any]) -> None:
        # Atomic-ish write: tmp → fsync → backup (hardlink/bcp) → replace.
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        tmp_path = path.with_name(path.name + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        # Backup current file before overwrite.
        if path.exists():
            backup = path.with_suffix(path.suffix + ".bak")
            existing = json.loads(path.read_text(encoding="utf-8"))
            backup.write_bytes(path.read_bytes())
            print(f"DEBUG: backed up {path} → {backup}")
        tmp_path.rename(path)


class StateRepository:
    """High-level persistence for ProjectState."""

    def __init__(self, store: None | StateStore = None) -> None:
        self._store = store or StateStore()

    # ------------------------------------------------------------------
    # Public contract
    # ------------------------------------------------------------------

    def load_state(self, series_dir: "Path") -> ProjectState:
        """Read state.json from *series_dir* and return ``ProjectState``.

        Raises FileNotFoundError when the file is absent.
        """
        if not series_dir.is_dir():
            raise FileNotFoundError(f"series directory not found: {series_dir}")
        path = series_dir / "state.json"
        raw = self._store.load(path)
        return ProjectState(**raw)

    def save_state(self, series_dir: "Path", state: ProjectState) -> None:
        """Persist ``state`` to *series_dir*/state.json (atomic)."""
        path = series_dir / "state.json"
        self._store.save(path, model_dump(state))

    def ensure_series_dir(self, series_dir: "Path") -> "Path":
        result = series_dir.mkdir(parents=True, exist_ok=True)
        return series_dir

    def ensure_raw_logs(self, series_dir: "Path") -> "Path":
        raw = series_dir / "raw_logs"
        raw.mkdir(parents=True, exist_ok=True)
        return raw


def model_dump(state: ProjectState) -> dict[str, Any]:
    """Minimal wrapper so workflow.py can use it as ``state.model_dump()``."""
    return state.model_dump(by_alias=False)
