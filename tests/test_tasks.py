"""Tests for novel_forge_kdp.tasks."""


def test_task_specs_have_valid_names():
    from novel_forge_kdp.tasks import TASK_SPECS

    for spec in TASK_SPECS:
        assert isinstance(spec.task_name, str)
        assert len(spec.task_name) > 0
        assert isinstance(spec.prompt_template_name, str)
        assert len(spec.prompt_template_name) > 0
        assert isinstance(spec.schema_name, str)
        assert len(spec.schema_name) > 0
        for key in spec.context_keys:
            assert isinstance(key, str)
            assert len(key) > 0


def test_task_specs_are_unique_by_name():
    from novel_forge_kdp.tasks import TASK_SPECS

    names = [spec.task_name for spec in TASK_SPECS]
    assert len(names) == len(set(names)), f"Duplicate task_names: {[name for name in names if names.count(name) > 1]}"


def test_task_get_by_name_returns_correct_spec():
    from novel_forge_kdp.tasks import TASK_SPECS, lookup_task

    series_plan = list(filter(lambda s: s.task_name == "series_plan", TASK_SPECS))
    assert len(series_plan) == 1
    spec = series_plan[0]
    assert spec.prompt_template_name == "series_plan"
    assert spec.schema_name == "series_plan"

    scene_draft = lookup_task("scene_draft")
    assert scene_draft is not None
    assert scene_draft.task_name == "scene_draft"


def test_lookup_nonexistent_task_returns_none():
    from novel_forge_kdp.tasks import lookup_task

    result = lookup_task("nonexistent_task_xyz")
    assert result is None


def test_task_specs_cover_all_expected_tasks():
    from novel_forge_kdp.tasks import TASK_SPECS

    expected = {
        "series_plan",
        "volume_outline",
        "scene_draft",
        "review",
        "revise_scene",
        "volume_review",
        "revise_volume",
        "bible_update",
    }
    actual = {spec.task_name for spec in TASK_SPECS}
    assert expected == actual
