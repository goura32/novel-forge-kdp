import json

from novel_forge_kdp.models import ProjectState, SeriesPlan, VolumeOutline, VolumeProgress
from novel_forge_kdp.repository import ProjectRepository
from novel_forge_kdp.volume_outline_workflow import VolumeOutlineWorkflow

from tests.fakes import FakeLLM


def make_state() -> ProjectState:
    series = SeriesPlan.model_validate(FakeLLM().complete_json(task="series_plan", messages=[], schema={}))
    return ProjectState(series=series, volumes=[VolumeProgress(number=1, title=series.planned_volumes[0].title)])


class Runner:
    def __init__(self):
        self.calls = []

    def complete(self, task_name, **context):
        self.calls.append((task_name, context))
        return FakeLLM().complete_json(task="volume_outline", messages=[], schema={})


def test_volume_outline_workflow_creates_validates_saves_and_syncs_outline(tmp_path):
    state = make_state()
    volume = state.volumes[0]
    series_dir = tmp_path / state.series.slug
    volume_dir = series_dir / "volume_001"
    volume_dir.mkdir(parents=True)
    runner = Runner()
    calls = []

    workflow = VolumeOutlineWorkflow(
        task_runner=runner,
        repository=ProjectRepository(),
        validate_volume_outline=lambda outline, number: calls.append(("validate", outline.volume_number, number)),
        sync_volume_scenes=lambda volume, outline: calls.append(("sync", volume.number, len(outline.chapters))),
        save_state=lambda series_dir, state: calls.append(("save_state", series_dir.name, state.series.slug)),
    )

    outline = workflow.load_or_create(series_dir=series_dir, volume_dir=volume_dir, state=state, volume=volume, number=1)

    assert outline.volume_number == 1
    assert runner.calls[0][0] == "volume_outline"
    assert json.loads((volume_dir / "outline.json").read_text(encoding="utf-8"))["title"] == outline.title
    assert volume.status == "outlined"
    assert calls == [("validate", 1, 1), ("sync", 1, 1), ("save_state", state.series.slug, state.series.slug)]


def test_volume_outline_workflow_loads_existing_outline_without_llm_or_state_save(tmp_path):
    state = make_state()
    volume = state.volumes[0]
    series_dir = tmp_path / state.series.slug
    volume_dir = series_dir / "volume_001"
    volume_dir.mkdir(parents=True)
    existing = VolumeOutline.model_validate(FakeLLM().complete_json(task="volume_outline", messages=[], schema={}))
    (volume_dir / "outline.json").write_text(existing.model_dump_json(), encoding="utf-8")
    runner = Runner()
    calls = []

    workflow = VolumeOutlineWorkflow(
        task_runner=runner,
        repository=ProjectRepository(),
        validate_volume_outline=lambda outline, number: calls.append(("validate", outline.volume_number, number)),
        sync_volume_scenes=lambda volume, outline: calls.append(("sync", volume.number, len(outline.chapters))),
        save_state=lambda series_dir, state: calls.append(("save_state", series_dir.name, state.series.slug)),
    )

    outline = workflow.load_or_create(series_dir=series_dir, volume_dir=volume_dir, state=state, volume=volume, number=1)

    assert outline.title == existing.title
    assert runner.calls == []
    assert volume.status == "planned"
    assert calls == [("validate", 1, 1), ("sync", 1, 1)]
