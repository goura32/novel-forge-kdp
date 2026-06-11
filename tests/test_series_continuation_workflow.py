from pathlib import Path
from typing import Literal

from novel_forge_kdp.models import ProjectState, SeriesPlan, VolumeProgress
from novel_forge_kdp.series_continuation_workflow import SeriesContinuationWorkflow

from tests.fakes import FakeLLM


VolumeStatus = Literal["planned", "outlined", "drafted", "reviewed", "revised"]


def make_state(*, current_volume=1, volume_status: VolumeStatus = "planned", volume_count=2):
    series = SeriesPlan.model_validate(
        FakeLLM(planned_volume_count=volume_count).complete_json(task="series_plan", messages=[], schema={})
    )
    return ProjectState(
        series=series,
        current_volume=current_volume,
        volumes=[VolumeProgress(number=1, title=series.planned_volumes[0].title, status=volume_status)],
    )


def test_series_continuation_completes_current_volume_when_not_revised():
    state = make_state(volume_status="drafted")
    calls = []

    def complete_volume(slug, volume_number):
        calls.append(("complete_volume", slug, volume_number))
        state.volumes[0].status = "revised"
        return state

    workflow = SeriesContinuationWorkflow(
        status=lambda slug: state,
        complete_volume=complete_volume,
        write_volume=lambda slug, volume_number: (_ for _ in ()).throw(AssertionError("write_volume should not run")),
        series_dir_for=lambda slug: Path(slug),
        save_state=lambda series_dir, state: calls.append(("save_state", series_dir.name)),
        find_volume=lambda state, number: next(
            (volume for volume in state.volumes if volume.number == number),
            None,
        ),
        ensure_planned_volume_number=lambda state, number: calls.append(("ensure_planned", number)),
        ensure_volume_progress=lambda state, number: (_ for _ in ()).throw(
            AssertionError("ensure_volume_progress should not run")
        ),
    )

    result = workflow.continue_series(slug="hoshikuzu-library")

    assert result.volumes[0].status == "revised"
    assert calls == [("ensure_planned", 1), ("complete_volume", "hoshikuzu-library", 1)]


def test_series_continuation_advances_to_next_volume_after_current_is_revised():
    state = make_state(volume_status="revised")
    calls = []

    def ensure_volume_progress(state, number):
        calls.append(("ensure_volume_progress", number))
        volume = VolumeProgress(number=number, title=state.series.planned_volumes[number - 1].title)
        state.volumes.append(volume)
        return volume

    def write_volume(slug, volume_number):
        calls.append(("write_volume", slug, volume_number))
        return state

    workflow = SeriesContinuationWorkflow(
        status=lambda slug: state,
        complete_volume=lambda slug, volume_number: (_ for _ in ()).throw(
            AssertionError("complete_volume should not run")
        ),
        write_volume=write_volume,
        series_dir_for=lambda slug: Path("/workspace") / slug,
        save_state=lambda series_dir, state: calls.append(("save_state", series_dir.name, state.current_volume)),
        find_volume=lambda state, number: next(
            (volume for volume in state.volumes if volume.number == number),
            None,
        ),
        ensure_planned_volume_number=lambda state, number: calls.append(("ensure_planned", number)),
        ensure_volume_progress=ensure_volume_progress,
    )

    result = workflow.continue_series(slug="hoshikuzu-library")

    assert result.current_volume == 2
    assert [volume.number for volume in result.volumes] == [1, 2]
    assert calls == [
        ("ensure_planned", 1),
        ("ensure_planned", 2),
        ("ensure_volume_progress", 2),
        ("save_state", "hoshikuzu-library", 2),
        ("write_volume", "hoshikuzu-library", 2),
    ]
