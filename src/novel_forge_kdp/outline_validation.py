from __future__ import annotations

from .models import VolumeOutline

MAX_CHAPTERS_PER_VOLUME = 2
MAX_SCENES_PER_CHAPTER = 2


class OutlineValidationError(RuntimeError):
    pass


def validate_volume_outline(outline: VolumeOutline, expected_number: int) -> None:
    if outline.volume_number != expected_number:
        raise OutlineValidationError(f"volume outline number mismatch: expected={expected_number} actual={outline.volume_number}")
    if len(outline.chapters) < 1:
        raise OutlineValidationError("outline has no chapters")
    if len(outline.chapters) > MAX_CHAPTERS_PER_VOLUME:
        raise OutlineValidationError(f"too many chapters in outline: max={MAX_CHAPTERS_PER_VOLUME} actual={len(outline.chapters)}")
    chapter_numbers: set[int] = set()
    for chapter in outline.chapters:
        if chapter.number in chapter_numbers:
            raise OutlineValidationError(f"duplicate chapter number in outline: {chapter.number}")
        chapter_numbers.add(chapter.number)
        if len(chapter.scenes) < 1:
            raise OutlineValidationError(f"chapter has no scenes: chapter={chapter.number}")
        if len(chapter.scenes) > MAX_SCENES_PER_CHAPTER:
            raise OutlineValidationError(f"too many scenes in outline chapter: chapter={chapter.number} max={MAX_SCENES_PER_CHAPTER} actual={len(chapter.scenes)}")
        scene_numbers: set[int] = set()
        for scene in chapter.scenes:
            if scene.number in scene_numbers:
                raise OutlineValidationError(f"duplicate scene number in outline: chapter={chapter.number} scene={scene.number}")
            scene_numbers.add(scene.number)
