from pathlib import Path

import pytest

from novel_forge_kdp.models import ProjectState, SeriesPlan, VolumeProgress
from novel_forge_kdp.volume_export_workflow import VolumeExportWorkflow, VolumeExportWorkflowError


def make_state() -> ProjectState:
    series = SeriesPlan.model_validate(
        {
            "title": "Series",
            "slug": "series",
            "logline": "Logline",
            "genre": "Genre",
            "target_audience": "Audience",
            "themes": ["Theme"],
            "selling_points": ["Point"],
            "world": {"summary": "World", "rules": []},
            "main_characters": [{"name": "A", "role": "B", "arc": "C"}],
            "planned_volumes": [{"number": 1, "title": "Volume One", "premise": "Premise"}],
        }
    )
    return ProjectState(series=series, volumes=[VolumeProgress(number=1, title="Volume One")])


def test_volume_export_workflow_uses_revised_manuscript_when_present(tmp_path):
    series_dir = tmp_path / "series"
    volume_dir = series_dir / "volume_001"
    volume_dir.mkdir(parents=True)
    (volume_dir / "volume_revised.md").write_text("# Revised\n", encoding="utf-8")
    calls = []

    def assemble_manuscript(series_dir, volume):
        raise AssertionError("assemble_manuscript should not run when revised manuscript exists")

    def export_kdp(volume_dir, title, manuscript):
        calls.append((volume_dir.name, title, manuscript))
        exports = volume_dir / "exports"
        exports.mkdir()
        (exports / "manuscript.md").write_text(manuscript, encoding="utf-8")

    path = VolumeExportWorkflow(
        assemble_manuscript=assemble_manuscript,
        export_kdp=export_kdp,
    ).run(series_dir=series_dir, state=make_state(), volume_number=None)

    assert path == volume_dir / "exports" / "manuscript.md"
    assert calls == [("volume_001", "Volume One", "# Revised\n")]


def test_volume_export_workflow_assembles_when_revised_manuscript_missing(tmp_path):
    series_dir = tmp_path / "series"
    calls = []

    def assemble_manuscript(series_dir, volume):
        calls.append(("assemble", series_dir.name, volume.number))
        return "# Assembled\n"

    def export_kdp(volume_dir, title, manuscript):
        calls.append(("export", volume_dir.name, title, manuscript))
        exports = volume_dir / "exports"
        exports.mkdir()
        (exports / "manuscript.md").write_text(manuscript, encoding="utf-8")

    path = VolumeExportWorkflow(
        assemble_manuscript=assemble_manuscript,
        export_kdp=export_kdp,
    ).run(series_dir=series_dir, state=make_state(), volume_number=1)

    assert path.read_text(encoding="utf-8") == "# Assembled\n"
    assert calls == [
        ("assemble", "series", 1),
        ("export", "volume_001", "Volume One", "# Assembled\n"),
    ]


def test_volume_export_workflow_rejects_missing_volume(tmp_path):
    with pytest.raises(VolumeExportWorkflowError, match="volume not found: 99"):
        VolumeExportWorkflow(
            assemble_manuscript=lambda series_dir, volume: "",
            export_kdp=lambda volume_dir, title, manuscript: None,
        ).run(series_dir=tmp_path / "series", state=make_state(), volume_number=99)
