from __future__ import annotations

from .models import ProjectState, SceneProgress, VolumeOutline, VolumeProgress


class VolumeProgressServiceError(RuntimeError):
    pass


class VolumeProgressService:
    """Domain service for planned volume and scene progress bookkeeping."""

    def find_volume(self, state: ProjectState, number: int) -> VolumeProgress | None:
        return next((volume for volume in state.volumes if volume.number == number), None)

    def ensure_planned_volume_number(self, state: ProjectState, number: int) -> None:
        if number > len(state.series.planned_volumes):
            raise VolumeProgressServiceError(
                f"volume exceeds planned series: volume={number} planned={len(state.series.planned_volumes)}"
            )

    def ensure_volume_progress(self, state: ProjectState, number: int) -> VolumeProgress:
        self.ensure_planned_volume_number(state, number)
        volume = self.find_volume(state, number)
        if volume is not None:
            return volume
        planned = next((planned for planned in state.series.planned_volumes if planned.number == number), None)
        if planned is None:
            raise VolumeProgressServiceError(
                f"volume exceeds planned series: volume={number} planned={len(state.series.planned_volumes)}"
            )
        volume = VolumeProgress(number=number, title=planned.title)
        state.volumes.append(volume)
        return volume

    def ensure_revised_scenes(self, *, slug: str, state: ProjectState, number: int, write_volume) -> tuple[ProjectState, VolumeProgress]:
        volume = self.find_volume(state, number)
        if volume is None or not volume.scenes or any(scene.status != "revised" for scene in volume.scenes):
            state = write_volume(slug, number)
            volume = self.find_volume(state, number)
            if volume is None:
                raise VolumeProgressServiceError(f"volume not found after write: {number}")
        return state, volume

    def sync_volume_scenes(self, volume: VolumeProgress, outline: VolumeOutline) -> None:
        existing = {(scene.chapter, scene.scene): scene for scene in volume.scenes}
        synced: list[SceneProgress] = []
        for chapter in outline.chapters:
            for scene in chapter.scenes:
                current = existing.get((chapter.number, scene.number))
                if current is None:
                    current = SceneProgress(chapter=chapter.number, scene=scene.number, title=scene.title)
                else:
                    current.title = scene.title
                synced.append(current)
        volume.scenes = synced
        volume.title = outline.title
