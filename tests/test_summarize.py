import pytest
from vis.summarize import _parse_llm_response


def test_parse_valid_json():
    raw = '{"summary": "test", "key_ideas": ["a"], "category": "Tutorial"}'
    result = _parse_llm_response(raw)
    assert result["summary"] == "test"
    assert result["key_ideas"] == ["a"]
    assert result["category"] == "Tutorial"


def test_parse_json_in_markdown_block():
    raw = '```json\n{"summary": "test", "key_ideas": ["a"], "category": "News"}\n```'
    result = _parse_llm_response(raw)
    assert result is not None
    assert result["category"] == "News"


def test_parse_json_with_surrounding_text():
    raw = 'Here is the result: {"summary": "test", "key_ideas": ["a", "b"], "category": "Analysis"} hope that helps!'
    result = _parse_llm_response(raw)
    assert result is not None
    assert result["summary"] == "test"


def test_parse_invalid_json():
    result = _parse_llm_response("this is not json at all")
    assert result is None


def test_parse_missing_required_keys():
    raw = '{"summary": "test", "other_field": "value"}'
    result = _parse_llm_response(raw)
    assert result is None


def test_parse_empty_string():
    result = _parse_llm_response("")
    assert result is None
