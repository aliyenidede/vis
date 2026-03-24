import os
import tempfile
import pytest
from vis.report import generate_report


def _make_video(title="Test Video", channel="Test Channel", briefing="Briefing text",
                key_insights=None, category="Tutorial"):
    return {
        "video_id": "abc123",
        "title": title,
        "channel_title": channel,
        "published_at": "2026-01-01",
        "url": "https://youtube.com/watch?v=abc123",
        "headline": "Test Headline",
        "briefing": briefing,
        "key_insights": key_insights or ["insight 1", "insight 2"],
        "category": category,
        "analysis": {
            "why_it_matters": "This matters because...",
            "critical_perspective": "However, consider that...",
            "open_questions": ["What about X?"],
        },
    }


def _make_failed(title="Failed Video", status="no_transcript", retry_count=1):
    return {
        "video_id": "fail123",
        "title": title,
        "channel_title": "Fail Channel",
        "url": "https://youtube.com/watch?v=fail123",
        "status": status,
        "retry_count": retry_count,
    }


def test_normal_report():
    with tempfile.TemporaryDirectory() as tmpdir:
        videos = [_make_video(title=f"Video {i}") for i in range(3)]
        failed = [_make_failed()]
        path = generate_report(videos, failed, tmpdir)
        assert os.path.exists(path)
        content = open(path).read()
        assert "Video 0" in content
        assert "Video 2" in content
        assert "Videos Without Transcript" in content


def test_no_failed_videos():
    with tempfile.TemporaryDirectory() as tmpdir:
        videos = [_make_video()]
        path = generate_report(videos, [], tmpdir)
        content = open(path).read()
        assert "Videos Without Transcript" not in content


def test_only_failed_videos():
    with tempfile.TemporaryDirectory() as tmpdir:
        failed = [_make_failed()]
        path = generate_report([], failed, tmpdir)
        assert os.path.exists(path)
        content = open(path).read()
        assert "Videos processed:** 0" in content
        assert "Videos Without Transcript" in content


def test_special_characters_in_title():
    with tempfile.TemporaryDirectory() as tmpdir:
        videos = [_make_video(title="C++ & Python: 'Best' \"Practices\" <2026>")]
        path = generate_report(videos, [], tmpdir)
        content = open(path).read()
        assert "C++ & Python" in content


def test_empty_key_insights():
    with tempfile.TemporaryDirectory() as tmpdir:
        videos = [_make_video(key_insights=[])]
        path = generate_report(videos, [], tmpdir)
        assert os.path.exists(path)
