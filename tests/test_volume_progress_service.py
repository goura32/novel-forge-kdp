import pytest

from novel_forge_kdp.models import ChapterPlan, PlannedVolume, ProjectState, ScenePlan, SceneProgress, SeriesPlan, VolumeOutline, VolumeProgress, World, Character
from novel_forge_kdp.volume_progress_service import VolumeProgressService, VolumeProgressServiceError


def series_state(planned_count: int = 1) -> ProjectState:
    planned = [PlannedVolume(number=i, title=f"Volume {i}", premise="premise") for i in range(1, planned_count + 1)]
    return ProjectState(
        series=SeriesPlan(
            title="Series",
            slug="series",
            logline="logline",
            genre="genre",
            target_audience="audience",
            themes=["theme"],
            selling_points=["point"],
            world=World(summary="world"),
            main_characters=[Character(name="澪", role="hero", arc="arc")],
            planned_volumes=planned,
        )
    )


def test_volume_progress_service_creates_and_finds_planned_volume():
    state = series_state(planned_count=2)
    service = VolumeProgressService()

    volume = service.ensure_volume_progress(state, 2)

    assert volume.number == 2
    assert volume.title == "Volume 2"
    assert service.find_volume(state, 2) is volume


def test_volume_progress_service_rejects_unplanned_volume():
    state = series_state(planned_count=1)

    with pytest.raises(VolumeProgressServiceError, match="volume exceeds planned series"):
        VolumeProgressService().ensure_planned_volume_number(state, 2)


def test_volume_progress_service_syncs_outline_scenes_preserving_existing_status():
    state = series_state(planned_count=1)
    volume = VolumeProgress(number=1, title="Old", scenes=[SceneProgress(chapter=1, scene=1, title="Old Scene", status="reviewed")])
    outline = VolumeOutline(
        volume_number=1,
        title="New Title",
        chapters=[
            ChapterPlan(
                number=1,
                title="Chapter",
                purpose="purpose",
                scenes=[
                    ScenePlan(number=1, title="New Scene", pov="p", goal="g", conflict="c", outcome="o"),
                    ScenePlan(number=2, title="Added Scene", pov="p", goal="g", conflict="c", outcome="o"),
                ],
            )
        ],
    )

    VolumeProgressService().sync_volume_scenes(volume, outline)

    assert volume.title == "New Title"
    assert [(s.chapter, s.scene, s.title, s.status) for s in volume.scenes] == [
        (1, 1, "New Scene", "reviewed"),
        (1, 2, "Added Scene", "planned"),
    ]
