import os
import tempfile
import pytest
from vis.transcript import _truncate, _parse_vtt


def test_truncate_short():
    text = "short text"
    assert _truncate(text) == text


def test_truncate_long():
    text = "a" * 600000
    result = _truncate(text)
    assert len(result) == 500000


def test_parse_vtt():
    vtt_content = """WEBVTT

00:00:00.000 --> 00:00:05.000
Hello world

00:00:05.000 --> 00:00:10.000
This is a test

00:00:10.000 --> 00:00:15.000
This is a test
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".vtt", delete=False, encoding="utf-8") as f:
        f.write(vtt_content)
        f.flush()
        path = f.name

    try:
        result = _parse_vtt(path)
        assert "Hello world" in result
        assert "This is a test" in result
        # Deduplicated consecutive identical lines
        assert result.count("This is a test") == 1
    finally:
        os.unlink(path)


def test_parse_vtt_with_tags():
    vtt_content = """WEBVTT

00:00:00.000 --> 00:00:05.000
<c.colorE5E5E5>Hello</c> <c.colorCCCCCC>world</c>
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".vtt", delete=False, encoding="utf-8") as f:
        f.write(vtt_content)
        f.flush()
        path = f.name

    try:
        result = _parse_vtt(path)
        assert "Hello" in result
        assert "<c." not in result
    finally:
        os.unlink(path)
