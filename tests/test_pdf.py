import os
import tempfile
from vis.pdf import generate_pdf


SAMPLE_VIDEOS = [
    {
        "title": "Test Video Title",
        "video_id": "abc123",
        "channel_title": "Test Channel",
        "published_at": "2026-01-01",
        "url": "https://youtube.com/watch?v=abc123",
        "category": "Tutorial",
        "headline": "Understanding Test Topics in Depth",
        "briefing": "This is a test briefing with multiple sentences.\n\nIt covers the main topics in educational depth.",
        "key_insights": [
            "First key insight",
            "Second key insight",
            "Third key insight",
        ],
        "tldr": "A quick overview of what you'll learn about test topics.",
        "analysis": {
            "why_it_matters": "This matters because testing is fundamental.",
            "critical_perspective": "However, not all testing approaches are equal.",
            "open_questions": ["What about edge cases?", "How does this scale?"],
        },
        "infographic": {
            "topic": "Test Topic",
            "key_stats": ["Stat 1", "Stat 2"],
            "key_terms": ["Term 1", "Term 2"],
            "bottom_line": "The bottom line.",
        },
    }
]

SAMPLE_FAILED = [
    {
        "title": "Failed Video",
        "video_id": "fail123",
        "channel_title": "Fail Channel",
        "url": "https://youtube.com/watch?v=fail123",
        "status": "no_transcript",
        "retry_count": 1,
    }
]


def test_pdf_generation():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "test.pdf")
        result = generate_pdf(SAMPLE_VIDEOS, SAMPLE_FAILED, pdf_path, tmpdir)
        assert os.path.exists(result)
        assert os.path.getsize(result) > 0


def test_pdf_empty_sections():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "test.pdf")
        result = generate_pdf([], [], pdf_path, tmpdir)
        assert os.path.exists(result)
        assert os.path.getsize(result) > 0
