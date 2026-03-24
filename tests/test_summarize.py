import pytest
from vis.summarize import _parse_llm_response


def test_parse_valid_json():
    raw = '{"briefing": "test", "key_insights": ["a"], "category": "Tutorial"}'
    result = _parse_llm_response(raw)
    assert result["briefing"] == "test"
    assert result["key_insights"] == ["a"]
    assert result["category"] == "Tutorial"


def test_parse_old_field_names_remapped():
    """Old-style responses (summary/key_ideas) should be remapped to new fields."""
    raw = '{"summary": "test", "key_ideas": ["a"], "category": "Tutorial"}'
    result = _parse_llm_response(raw)
    assert result["briefing"] == "test"
    assert result["key_insights"] == ["a"]


def test_parse_json_in_markdown_block():
    raw = (
        '```json\n{"briefing": "test", "key_insights": ["a"], "category": "News"}\n```'
    )
    result = _parse_llm_response(raw)
    assert result is not None
    assert result["category"] == "News"


def test_parse_json_with_surrounding_text():
    raw = 'Here is the result: {"briefing": "test", "key_insights": ["a", "b"], "category": "Analysis"} hope that helps!'
    result = _parse_llm_response(raw)
    assert result is not None
    assert result["briefing"] == "test"


def test_parse_invalid_json():
    result = _parse_llm_response("this is not json at all")
    assert result is None


def test_parse_missing_required_keys():
    raw = '{"briefing": "test", "other_field": "value"}'
    result = _parse_llm_response(raw)
    assert result is None


def test_parse_empty_string():
    result = _parse_llm_response("")
    assert result is None
