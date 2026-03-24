# REA Lessons Learned

## 2026-03-24 23:07:33
**Lesson:** LLM summarization prompts that say "summarize the video" produce boring chronological recaps. Prompts must explicitly forbid video references and frame the task as "teach the topic."
**Rule:** When writing LLM prompts for content extraction, always frame as "extract and teach the knowledge" with explicit anti-patterns (no "in this video", no "the speaker says"). Include WRONG/RIGHT examples in the prompt itself.
