from __future__ import annotations

from pathlib import Path

from .models import VolumeProgress
from .paths import PathSafetyError


class ManuscriptAssemblyError(RuntimeError):
    pass


class ManuscriptAssembler:
    def assemble_volume(self, *, series_dir: Path, volume: VolumeProgress) -> str:
        parts = [f"# {volume.title}"]
        for scene in sorted(volume.scenes, key=lambda s: (s.chapter, s.scene)):
            if scene.status != "revised":
                raise ManuscriptAssemblyError(f"scene is not revised: chapter={scene.chapter} scene={scene.scene}")
            if scene.path is None:
                raise ManuscriptAssemblyError(f"missing scene manuscript path: chapter={scene.chapter} scene={scene.scene}")
            scene_path = self.safe_series_file(series_dir, scene.path)
            if not scene_path.exists():
                raise ManuscriptAssemblyError(f"missing scene manuscript: {scene.path}")
            text = scene_path.read_text(encoding="utf-8").strip()
            if not text:
                raise ManuscriptAssemblyError(f"empty scene manuscript: {scene.path}")
            parts.append(text)
        if len(parts) == 1:
            raise ManuscriptAssemblyError(f"volume has no revised scenes: volume={volume.number}")
        return "\n\n".join(parts).strip() + "\n"

    @staticmethod
    def safe_series_file(series_dir: Path, relative_path: str) -> Path:
        candidate_raw = Path(relative_path)
        if candidate_raw.is_absolute():
            raise PathSafetyError(f"scene manuscript path escapes series directory: {relative_path}")
        root = series_dir.resolve()
        candidate = (root / candidate_raw).resolve()
        if root != candidate and root not in candidate.parents:
            raise PathSafetyError(f"scene manuscript path escapes series directory: {relative_path}")
        return candidate
