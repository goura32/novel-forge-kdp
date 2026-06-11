from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .artifact_paths import SeriesPaths
from .models import ProjectState, VolumeProgress
from .paths import ensure_dir


class VolumeExportWorkflowError(RuntimeError):
    pass


class VolumeExportWorkflow:
    def __init__(
        self,
        *,
        assemble_manuscript: Callable[[Path, VolumeProgress], str],
        export_kdp: Callable[[Path, str, str], None],
    ) -> None:
        self.assemble_manuscript = assemble_manuscript
        self.export_kdp = export_kdp

    def run(self, *, series_dir: Path, state: ProjectState, volume_number: int | None) -> Path:
        number = volume_number or state.current_volume
        volume = next((v for v in state.volumes if v.number == number), None)
        if volume is None:
            raise VolumeExportWorkflowError(f"volume not found: {number}")
        volume_dir = ensure_dir(SeriesPaths(series_dir).volume(number).root)
        revised_path = volume_dir / "volume_revised.md"
        manuscript = revised_path.read_text(encoding="utf-8") if revised_path.exists() else self.assemble_manuscript(series_dir, volume)
        self.export_kdp(volume_dir, volume.title, manuscript)
        return volume_dir / "exports" / "manuscript.md"
