# REA Lessons Learned

## 2026-03-24 23:07:33
**Lesson:** LLM summarization prompts that say "summarize the video" produce boring chronological recaps. Prompts must explicitly forbid video references and frame the task as "teach the topic."
**Rule:** When writing LLM prompts for content extraction, always frame as "extract and teach the knowledge" with explicit anti-patterns (no "in this video", no "the speaker says"). Include WRONG/RIGHT examples in the prompt itself.

## 2026-03-24 23:55:00
**Lesson:** `add_channel()` with `ON CONFLICT DO NOTHING` prevents re-adding soft-deleted channels. When using soft-delete pattern (active=FALSE), upsert must check active status and re-activate instead of silently returning "duplicate".
**Rule:** Any table with a soft-delete column (active/deleted) must have upsert logic that distinguishes "active duplicate" from "inactive, can re-activate". Never use ON CONFLICT DO NOTHING with soft-delete tables.

## 2026-03-24 23:55:01
**Lesson:** Telegram Markdown v1 treats `_`, `*`, `` ` ``, `[` as formatting. User-provided strings (channel names, URLs) containing these characters break sendMessage silently (HTTP 400, no delivery).
**Rule:** Always wrap dynamic/user-provided strings in backticks when embedding in Telegram Markdown messages. Use `parse_mode=None` for error messages that may contain unpredictable content.

## 2026-03-24 23:55:02
**Lesson:** CI workflow for VIS requires `playwright install --with-deps chromium` because test_pdf.py uses Playwright for PDF generation. Without it, Chromium binary is missing and tests fail.
**Rule:** When adding browser-dependent tests to CI, always include browser installation step in the workflow.
