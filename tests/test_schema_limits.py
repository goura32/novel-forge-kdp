"""Tests for novel_forge_kdp.schema_limits. Ensures schema maxItems match runtime MAX_* constants."""


def test_volume_outline_schema_max_chapters_matches_runtime():
    """Schema 'chapters'.maxItems must match MAX_CHAPTERS_PER_VOLUME."""
    from novel_forge_kdp.schemas import load_schema
    
    schema = load_schema("volume_outline")
    chapters_def = schema["properties"]["chapters"]
    schema_max = chapters_def.get("maxItems")
    
    try:
        from novel_forge_kdp.outline_validation import MAX_CHAPTERS_PER_VOLUME as runtime_max
    except ImportError:
        raise AssertionError("Cannot import MAX_CHAPTERS_PER_VOLUME from outline_validation")
    
    assert schema_max == runtime_max, (
        f"Schema chapters.maxItems={schema_max} != runtime MAX_CHAPTERS_PER_VOLUME={runtime_max}"
    )


def test_volume_outline_schema_max_scenes_matches_runtime():
    """Schema 'chapters'.items.properties['scenes'].maxItems must match MAX_SCENES_PER_CHAPTER."""
    from novel_forge_kdp.schemas import load_schema
    
    schema = load_schema("volume_outline")
    chapters_items = schema["properties"]["chapters"]["items"]
    scenes_def = chapters_items["properties"]["scenes"]
    schema_max = scenes_def.get("maxItems")
    
    try:
        from novel_forge_kdp.outline_validation import MAX_SCENES_PER_CHAPTER as runtime_max
    except ImportError:
        raise AssertionError("Cannot import MAX_SCENES_PER_CHAPTER from outline_validation")
    
    assert schema_max == runtime_max, (
        f"Schema scenes.maxItems={schema_max} != runtime MAX_SCENES_PER_CHAPTER={runtime_max}"
    )


def test_schema_max_values_are_reasonable():
    """Both max items must be positive integers."""
    try:
        from novel_forge_kdp.outline_validation import MAX_CHAPTERS_PER_VOLUME, MAX_SCENES_PER_CHAPTER
        
        assert isinstance(MAX_CHAPTERS_PER_VOLUME, int), "MAX_CHAPTERS_PER_VOLUME must be int"
        assert MAX_CHAPTERS_PER_VOLUME >= 1, "MAX_CHAPTERS_PER_VOLUME must be >= 1"
        
        assert isinstance(MAX_SCENES_PER_CHAPTER, int), "MAX_SCENES_PER_CHAPTER must be int"
        assert MAX_SCENES_PER_CHAPTER >= 1, "MAX_SCENES_PER_CHAPTER must be >= 1"
    except ImportError:
        raise AssertionError("Cannot import constants from outline_validation")
