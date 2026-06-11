import pytest

from novel_forge_kdp.models import ChapterPlan, ScenePlan, VolumeOutline
from novel_forge_kdp.outline_validation import OutlineValidationError, validate_volume_outline


def valid_outline() -> VolumeOutline:
    return VolumeOutline(
        volume_number=1,
        title="夜明けの禁書",
        chapters=[
            ChapterPlan(
                number=1,
                title="第一章",
                purpose="導入",
                scenes=[ScenePlan(number=1, title="一", pov="澪", goal="g", conflict="c", outcome="o")],
            )
        ],
    )


def test_validate_volume_outline_accepts_valid_outline():
    validate_volume_outline(valid_outline(), expected_number=1)


def test_validate_volume_outline_rejects_mismatch_and_duplicates():
    outline = valid_outline()
    outline.volume_number = 2
    with pytest.raises(OutlineValidationError, match="volume outline number mismatch"):
        validate_volume_outline(outline, expected_number=1)

    outline = valid_outline()
    outline.chapters.append(outline.chapters[0].model_copy())
    with pytest.raises(OutlineValidationError, match="duplicate chapter number"):
        validate_volume_outline(outline, expected_number=1)
