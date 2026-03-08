import os
import tempfile
import pytest
from vis.pdf import markdown_to_pdf


SAMPLE_MD = """# Daily Video Insight Report
**Date:** 2026-01-01 12:00:00
**Videos processed:** 2
**Videos failed:** 1

---

## 1. Test Video Title
**Channel:** Test Channel
**Published:** 2026-01-01
**Link:** https://youtube.com/watch?v=abc123
**Category:** Tutorial

### Summary
This is a test summary with multiple sentences. It covers the main topics discussed in the video.

### Key Ideas & Takeaways
- First key idea
- Second key idea
- Third key idea

---

## Videos Without Transcript

| # | Title | Channel | Link | Status |
|---|-------|---------|------|--------|
| 1 | Failed Video | Fail Channel | [Link](https://youtube.com/watch?v=fail123) | No transcript (attempt 2) |

---
"""


def test_pdf_generation():
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, "test.md")
        pdf_path = os.path.join(tmpdir, "test.pdf")

        with open(md_path, "w") as f:
            f.write(SAMPLE_MD)

        result = markdown_to_pdf(md_path, pdf_path)
        assert os.path.exists(result)
        assert os.path.getsize(result) > 0


def test_pdf_empty_sections():
    md = "# Report\n**Date:** 2026-01-01\n\n---\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, "test.md")
        pdf_path = os.path.join(tmpdir, "test.pdf")

        with open(md_path, "w") as f:
            f.write(md)

        result = markdown_to_pdf(md_path, pdf_path)
        assert os.path.exists(result)
        assert os.path.getsize(result) > 0
