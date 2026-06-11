import pytest

from novel_forge_kdp.models import ProjectState, SeriesPlan, VolumeProgress
from novel_forge_kdp.volume_completion_workflow import VolumeCompletionLlmCalls, VolumeCompletionLlmCallsError


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


class SpyRepository:
    def __init__(self):
        self.volume_reviews = []
        self.bibles = []

    def save_volume_review(self, volume_dir, data, *, final=False):
        self.volume_reviews.append((volume_dir.name, data, final))

    def save_bible(self, series_dir, data):
        self.bibles.append((series_dir.name, data))


def test_volume_completion_llm_calls_review_revise_and_update_bible(tmp_path):
    calls = []

    class Runner:
        def complete(self, task_name, **context):
            calls.append((task_name, context))
            if task_name == "volume_review":
                return {"ready_for_publication": True, "issues": []}
            if task_name == "revise_volume":
                return {"title": "Revised", "body": "## Chapter 1\n\nBody."}
            if task_name == "bible_update":
                return {"updated": True}
            raise AssertionError(task_name)

    series_dir = tmp_path / "series"
    series_dir.mkdir()
    repository = SpyRepository()
    llm_calls = VolumeCompletionLlmCalls(runner=Runner(), repository=repository)
    state = make_state()

    review = llm_calls.review_volume(series_dir, state, "manuscript")
    revised = llm_calls.revise_volume(series_dir, "manuscript", review, 1)
    llm_calls.update_bible(series_dir, "revised manuscript")

    assert review == {"ready_for_publication": True, "issues": []}
    assert revised == {"title": "Revised", "body": "## Chapter 1\n\nBody."}
    assert [name for name, _ in calls] == ["volume_review", "revise_volume", "bible_update"]
    assert "series" in calls[0][1]
    assert calls[1][1]["chapter_count"] == 1
    assert calls[2][1]["existing_bible"] == "{}"
    assert repository.bibles == [("series", {"updated": True})]


def test_volume_completion_llm_calls_final_review_only_when_initial_review_not_ready(tmp_path):
    calls = []

    class Runner:
        def complete(self, task_name, **context):
            calls.append((task_name, context))
            return {"ready_for_publication": True, "issues": []}

    repository = SpyRepository()
    llm_calls = VolumeCompletionLlmCalls(runner=Runner(), repository=repository)
    series_dir = tmp_path / "series"
    volume_dir = series_dir / "volume_001"
    volume_dir.mkdir(parents=True)

    final_review = llm_calls.final_review_if_needed(
        series_dir,
        volume_dir,
        make_state(),
        {"ready_for_publication": False, "issues": []},
        "# Revised\n",
    )

    assert final_review == {"ready_for_publication": True, "issues": []}
    assert [name for name, _ in calls] == ["volume_review"]
    assert repository.volume_reviews == [("volume_001", {"ready_for_publication": True, "issues": []}, True)]


def test_volume_completion_llm_calls_rejects_bad_revised_structure(tmp_path):
    class Runner:
        def complete(self, task_name, **context):
            return {"title": "Bad", "body": "No chapter heading."}

    llm_calls = VolumeCompletionLlmCalls(runner=Runner(), repository=SpyRepository())

    with pytest.raises(VolumeCompletionLlmCallsError, match="no chapter headings"):
        llm_calls.revise_volume(tmp_path / "series", "manuscript", {"ready_for_publication": True}, 1)
