# VIS — Implementation Plan

## Architecture

```
vis/
  config.py              → Load config from .env + validation
  db.py                  → PostgreSQL connection pool + schema + queries
  youtube.py             → Playlist fetch (YouTube Data API v3) + processed video tracking via DB
  transcript.py          → Transcript extraction (dual: youtube-transcript-api + yt-dlp fallback)
  summarize.py           → Detailed summarization via OpenRouter API (JSON output)
  report.py              → Markdown report generation (including failed transcripts)
  pdf.py                 → PDF conversion with fpdf2 (Helvetica, English-only output)
  telegram.py            → Send PDF via Telegram Bot API (text error on failure)
  main.py                → Pipeline orchestrator
  scheduler.py           → Optional APScheduler-based scheduling
  Dockerfile             → Python app container
  docker-compose.yaml     → PostgreSQL + app service for Coolify deployment
  tests/                 → Unit tests
  output/                → Reports + logs
```

---

## Phase 0: Project Scaffolding

**Files to create:**

1. `.gitignore` — `.env`, `output/`, `__pycache__/`, `*.pyc`
2. `.env.example` — All config keys with placeholder values
3. `.env` — Actual config (user fills credentials, not committed)
4. `requirements.txt` — All dependencies
5. `output/` directory
6. `tests/` directory
7. `CLAUDE.md` — Project-level instructions
8. `Dockerfile` — Python app container
9. `docker-compose.yaml` — PostgreSQL service + app

**Dependencies (requirements.txt):**

- `google-api-python-client` (YouTube Data API v3)
- `youtube-transcript-api` (primary transcript source)
- `yt-dlp` (fallback transcript source — more resilient to some blocking)
- `requests` (OpenRouter + Telegram HTTP calls)
- `python-dotenv`
- `fpdf2` (PDF generation — pure Python, Helvetica built-in)
- `psycopg2-binary` (PostgreSQL driver)
- `apscheduler` (optional, for built-in scheduling)
- `pytest` (unit testing)

---

## Phase 1: Configuration Layer

**File: `config.py`**

- Load `.env` via `python-dotenv`
- Expose config values via a `Config` dataclass with `@classmethod load()`
- Validate required keys at startup (fail fast with clear error messages)
- Mask sensitive keys in logs: replace with `***` except last 4 chars
- Defaults: `OUTPUT_DIR = "./output"`, `MAX_VIDEOS = 100`, `TRANSCRIPT_RETRY_DAYS = 3`
- All modules import config from here — never read env vars directly elsewhere

**Required .env keys:**

```
YOUTUBE_API_KEY=
YOUTUBE_PLAYLIST_ID=
OPENROUTER_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
DATABASE_URL=postgresql://vis:changeme@localhost:5432/vis
OUTPUT_DIR=./output
MAX_VIDEOS=100
LLM_MODEL=google/gemini-2.0-flash-001
TRANSCRIPT_RETRY_DAYS=3
```

**Sensitive keys (masked in logs):** `YOUTUBE_API_KEY`, `OPENROUTER_API_KEY`, `TELEGRAM_BOT_TOKEN`, `DATABASE_URL`

---

## Phase 2: Database Layer

**File: `db.py`**

**Responsibilities:**

- Connection pool management (psycopg2 `SimpleConnectionPool`, min=1, max=5)
- Schema creation on first run (auto-migrate)
- Query functions for processed videos
- All DB access goes through this module — no raw SQL elsewhere

**Schema:**

```sql
CREATE TABLE IF NOT EXISTS processed_videos (
    video_id           TEXT PRIMARY KEY,
    title              TEXT NOT NULL,
    channel_title      TEXT,
    published_at       TIMESTAMPTZ,
    url                TEXT,
    status             TEXT NOT NULL,          -- 'ok', 'no_transcript', 'gave_up'
    retry_count        INTEGER DEFAULT 0,
    first_seen_at      TIMESTAMPTZ NOT NULL,
    processed_at       TIMESTAMPTZ,
    summary            TEXT,
    key_ideas          JSONB,
    category           TEXT,
    transcript_language TEXT                   -- e.g. 'en', 'tr', 'auto-en' (for debugging)
);

CREATE TABLE IF NOT EXISTS run_log (
    id                 SERIAL PRIMARY KEY,
    run_at             TIMESTAMPTZ NOT NULL,
    videos_found       INTEGER,
    videos_processed   INTEGER,
    videos_skipped     INTEGER,
    report_path        TEXT,
    success            BOOLEAN,
    telegram_sent      BOOLEAN DEFAULT FALSE,
    error_message      TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_pv_status ON processed_videos(status);
CREATE INDEX IF NOT EXISTS idx_pv_first_seen ON processed_videos(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_rl_run_at ON run_log(run_at);
```

**Functions:**

- `init_db(database_url) -> connection_pool` — create pool, run schema migration
- `get_processed_ids(pool) -> set[str]` — return all video IDs with status 'ok' or 'gave_up'
- `get_retryable_videos(pool, max_retry_days) -> list[dict]` — videos with `no_transcript` status where `first_seen_at` is within retry window
- `upsert_video(pool, video_data) -> None` — insert or update a video record
- `log_run(pool, stats) -> None` — insert run statistics
- `get_unsent_reports(pool) -> list[dict]` — runs where `telegram_sent = false` and `report_path` exists
- `mark_telegram_sent(pool, run_id) -> None` — update `telegram_sent` to true
- `expire_old_retries(pool, max_retry_days) -> list[dict]` — mark `no_transcript` videos past retry window as `gave_up`, return them for reporting
- `close_pool(pool) -> None` — clean shutdown

**Upsert behavior for `first_seen_at`:**

```sql
INSERT INTO processed_videos (..., first_seen_at) VALUES (..., NOW())
ON CONFLICT (video_id) DO UPDATE SET
    status = EXCLUDED.status,
    retry_count = EXCLUDED.retry_count,
    processed_at = EXCLUDED.processed_at,
    summary = EXCLUDED.summary,
    key_ideas = EXCLUDED.key_ideas,
    category = EXCLUDED.category,
    transcript_language = EXCLUDED.transcript_language
    -- first_seen_at is NOT updated (preserves original discovery date)
;
```

**Connection safety:**

- `pool.getconn()` is NOT a context manager — always use try/finally:
  ```python
  conn = pool.getconn()
  try:
      # ... work ...
      conn.commit()
  finally:
      pool.putconn(conn)
  ```
- All writes use explicit `conn.commit()`
- On error: `conn.rollback()` before returning connection to pool

---

## Phase 3: YouTube Playlist Fetching

**File: `youtube.py`**

**Functions:**

- `fetch_playlist_videos(playlist_id, api_key, max_results) -> list[dict]` — fetch all videos with pagination
- `get_new_videos(playlist_id, api_key, max_results, db_pool) -> list[dict]` — return unprocessed + retryable videos

**Return format per video:**

```python
{ "video_id": str, "title": str, "channel_title": str, "published_at": str, "url": str }
```

**Edge cases:**

- Empty playlist → return empty list, log info
- API quota exceeded → catch `HttpError`, log error, re-raise
- Deleted/private videos in playlist → skip, log warning
- Retryable videos (no_transcript within retry window) → include in result for re-attempt

**Pagination:** YouTube API returns max 50 items per page. Loop until `nextPageToken` is None or `MAX_VIDEOS` reached.

**YouTube API quota note:** Each `playlistItems.list` call costs 1 unit. Daily quota is 10,000 units. With 50 items/page and MAX_VIDEOS=100, that's 2 API calls per run — quota is not a concern for daily runs.

---

## Phase 4: Transcript Extraction

**File: `transcript.py`**

**Functions:**

- `get_transcript(video_id) -> tuple[str | None, str | None]` — return `(transcript_text, language_code)` or `(None, None)`
- `_try_youtube_transcript_api(video_id) -> tuple[str | None, str | None]` — primary method
- `_try_yt_dlp(video_id) -> tuple[str | None, str | None]` — fallback method

**Dual extraction strategy:**

```
1. Try youtube-transcript-api (fast, lightweight):
   a. ytt_api = YouTubeTranscriptApi()
   b. Try ytt_api.fetch(video_id, languages=["en"])
   c. Try ytt_api.fetch(video_id, languages=["en-US", "en-GB"])
   d. Try ytt_api.fetch(video_id, languages=["tr"])
   e. List all transcripts → pick manual first, then auto-generated (any language)
   f. If nothing → fall through to yt-dlp

2. Try yt-dlp (heavier, different fingerprint):
   a. Use yt_dlp.YoutubeDL with skip_download=True, writesubtitles=True
   b. Try manual subtitles first, then auto-generated
   c. Parse VTT/SRT output to plain text
   d. If nothing → return (None, None)
```

**Rate limiting between videos:** 2-second delay between transcript requests (both methods) to avoid triggering IP blocks.

**Edge cases:**

- `TranscriptsDisabled` → try yt-dlp fallback
- `NoTranscriptFound` → try yt-dlp fallback
- `VideoUnavailable` → return (None, None), log warning
- `RequestBlocked` / IP block → try yt-dlp fallback, log warning
- Very long transcripts → truncate to ~50,000 characters
- Non-English transcript → return it (LLM system prompt handles translation)
- yt-dlp writes temp files → use `tempfile.TemporaryDirectory()`, clean up after

**Important:** youtube-transcript-api v1.2+ uses instance methods: `YouTubeTranscriptApi().fetch()` not `YouTubeTranscriptApi.get_transcript()`. The old static methods are deprecated.

---

## Phase 5: LLM Summarization

**File: `summarize.py`**

**Functions:**

- `summarize_transcript(transcript, video_title, api_key, model) -> dict | None` — return structured summary
- `_call_openrouter(messages, api_key, model, retries=3) -> str` — low-level API call with retry
- `_parse_llm_response(raw_response) -> dict | None` — parse JSON from LLM response

**OpenRouter API call:**

- Endpoint: `https://openrouter.ai/api/v1/chat/completions`
- Headers: `Authorization: Bearer {key}`, `Content-Type: application/json`
- Model: configurable via `LLM_MODEL` env var (default: `google/gemini-2.0-flash-001`)
- Max tokens: 2000
- Response format: JSON requested explicitly
- Never log API key — only use from config, pass as parameter

**System prompt:**

```
You are a video content analyst. Given a video transcript, produce a detailed structured summary.

The transcript may be in any language. Always produce your output in English.

You MUST respond with valid JSON only, no markdown, no extra text. Use this exact structure:

{
  "summary": "3-5 paragraphs covering the full content of the video in detail",
  "key_ideas": ["idea 1", "idea 2", "..."],
  "category": "One of: Tutorial, News, Analysis, Discussion, Review, Entertainment, Other"
}
```

**User prompt:**

```
Video title: {video_title}

Transcript:
{transcript}
```

**JSON parsing strategy:**

1. Try `json.loads(response)` directly
2. If fails, try to extract JSON from markdown code block (```json ... ```)
3. If fails, try to find first `{` to last `}` and parse that
4. Validate parsed dict has required keys: `summary`, `key_ideas`, `category`
5. If all fail → log warning with first 200 chars of response, return None (video stays unprocessed)

**Rate limiting:**

- 1-second delay between API calls
- 429 response → read `retry-after` header if present, else exponential backoff starting at 5s, max 3 retries
- 5xx → retry 3 times with 2s backoff
- 4xx (non-429) → fail immediately, log error with response body

**Return structure:**

```python
{
    "summary": str,
    "key_ideas": list[str],
    "category": str
}
```

---

## Phase 6: Markdown Report Generation

**File: `report.py`**

**Functions:**

- `generate_report(videos_with_summaries, failed_videos, output_dir) -> str` — return path to generated .md file

**Report template:**

```markdown
# Daily Video Insight Report
**Date:** YYYY-MM-DD HH:MM:SS
**Videos processed:** N
**Videos failed:** M

---

## 1. {Video Title}
**Channel:** {channel}
**Published:** {date}
**Link:** https://youtube.com/watch?v={id}
**Category:** {category}

### Summary
{detailed summary}

### Key Ideas & Takeaways
- {idea 1}
- {idea 2}

---

## Videos Without Transcript

| # | Title | Channel | Link | Status |
|---|-------|---------|------|--------|
| 1 | {title} | {channel} | [Link]({url}) | No transcript (attempt 2/3) |
| 2 | {title} | {channel} | [Link]({url}) | Gave up after 3 days — watch manually |

---
```

**Edge cases:**

- No failed videos → omit "Videos Without Transcript" section entirely
- No successful videos but has failed → still generate report (shows only failed section)
- No videos at all → don't generate report (handled in main.py)

Output file: `output/report_YYYY-MM-DD_HHMMSS.md`

---

## Phase 7: PDF Generation

**File: `pdf.py`**

**Functions:**

- `markdown_to_pdf(md_path, pdf_path) -> str` — convert MD to PDF, return PDF path

**Implementation:**

- Use `fpdf2` with built-in Helvetica font (English-only output, no Unicode fonts needed)
- Parse our own structured Markdown format:
  - `# ` → Helvetica-Bold 18pt, dark blue
  - `## ` → Helvetica-Bold 14pt
  - `### ` → Helvetica-Bold 12pt
  - `**text**` → Helvetica-Bold inline
  - `- ` → bullet point with 10mm indent
  - `---` → horizontal line (full width, light gray)
  - `| col | col |` → simple table with cell borders
  - `[text](url)` → blue underlined link
  - Regular text → Helvetica 11pt, normal paragraph
- A4 size, 15mm margins
- Auto page break with 15mm bottom margin
- Page numbers in footer: "Page X of Y"

**Edge cases:**

- Very long summary text → fpdf2 handles multi_cell wrapping automatically
- Special characters in titles → Helvetica covers basic Latin + common symbols
- Empty sections → skip, don't render blank space

---

## Phase 8: Telegram Delivery

**File: `telegram.py`**

**Functions:**

- `send_pdf(bot_token, chat_id, pdf_path, caption) -> bool` — send PDF, return success
- `send_error_message(bot_token, chat_id, message) -> bool` — send plain text error message

**Caption format:**

```
Daily Video Insight Report — YYYY-MM-DD HH:MM:SS — N videos
```

**PDF send implementation:**

```python
url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
with open(pdf_path, 'rb') as f:
    files = {'document': (filename, f, 'application/pdf')}
    data = {'chat_id': chat_id, 'caption': caption}
    response = requests.post(url, files=files, data=data, timeout=30)
```

**Error message implementation:**

```python
url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
data = {'chat_id': chat_id, 'text': message}
response = requests.post(url, json=data, timeout=10)
```

**Telegram API limits:**

- Max file size: 50MB (PDF reports will be <1MB, no concern)
- Caption max: 1024 characters (our format is ~60 chars, no concern)
- Rate limit: 1 message/second per chat (we send max 2 messages, no concern)
- 429 response: read `retry_after` from response JSON, wait that many seconds

**Error handling:**

- Network error / timeout → retry 3 times with 2s backoff
- 429 (rate limit) → wait `retry_after` seconds, retry
- Bot blocked by user → log error, return False
- Invalid chat_id → log error, return False
- Any other error → log error with response body, return False
- **On PDF send failure:** call `send_error_message()` with: "VIS: PDF delivery failed. Report saved locally at {path}. Error: {details}"
- Never log bot token — only use from config, pass as parameter

---

## Phase 9: Main Orchestrator

**File: `main.py`**

**Pipeline flow:**

```
1. Load config (fail fast if invalid)
2. Setup logging (console + rotating file)
3. Initialize DB connection pool
4. Check for unsent reports from previous failed runs → try to send them
5. Expire old retries: mark no_transcript videos past TRANSCRIPT_RETRY_DAYS as "gave_up" → add to failed_videos for report
6. Fetch playlist videos
7. Filter to new/unprocessed videos + retryable videos (no_transcript within TRANSCRIPT_RETRY_DAYS)
8. If no new videos AND no expired retries → log info, exit 0
9. For each video (with 2s delay between transcript fetches):
   a. Fetch transcript → returns (text, language) or (None, None)
   b. If no transcript:
      - Upsert as "no_transcript", increment retry_count (gave_up handled in step 5)
      - Add to failed_videos list for report
      - Continue
   c. Summarize transcript → if None, skip (do NOT update status, retry next run)
   d. Upsert video to DB: status="ok", summary, key_ideas, category, transcript_language
10. If no videos were processed AND no failed videos AND no expired retries → log info, exit 0
11. Generate Markdown report (processed videos + failed videos section)
12. Convert to PDF
13. Send PDF via Telegram
14. Log run to DB (with telegram_sent status)
15. If Telegram failed → send error text message
16. Close DB pool
17. Log completion with stats, exit 0
```

**Unsent report recovery (step 4):**

- Query `run_log` for `telegram_sent = false` AND `report_path IS NOT NULL`
- For each unsent report: check if PDF file exists, try to send, update `telegram_sent`
- This handles the crash-between-PDF-and-Telegram scenario

**Logging:**

- Python `logging` module
- Console handler: INFO level, StreamHandler
- File handler: DEBUG level, `RotatingFileHandler` (maxBytes=5MB, backupCount=3)
- Format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- Log file: `output/vis.log`
- **Sensitive data:** Never log API keys, tokens, or DATABASE_URL passwords. Config module masks these at load time.

---

## Phase 10: Docker & Deployment

**File: `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

RUN mkdir -p /app/output

CMD ["python", "main.py"]
```

**File: `docker-compose.yaml`**

```yaml
services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: vis
      POSTGRES_USER: vis
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U vis"]
      interval: 10s
      timeout: 5s
      retries: 5

  app:
    build: .
    restart: "no"
    depends_on:
      db:
        condition: service_healthy
    env_file: .env
    environment:
      DATABASE_URL: postgresql://vis:${POSTGRES_PASSWORD}@db:5432/vis
    volumes:
      - ./output:/app/output

volumes:
  pgdata:
```

**Coolify deployment:**

- Push repo to GitHub, connect to Coolify via GitHub integration
- Coolify auto-detects `docker-compose.yaml` and builds
- Environment variables: Set via Coolify UI (Settings → Environment Variables) — same keys as `.env`
- `POSTGRES_PASSWORD`: Generate strong password, set in Coolify env vars
- `pgdata` volume: Coolify persists Docker volumes across deploys automatically
- Scheduling: Use Coolify's built-in "Scheduled Tasks" feature (cron syntax: `0 5 * * *` for 05:00 UTC = 08:00 Istanbul)
- Alternatively: Add cron entry on VPS host: `0 5 * * * cd /path/to/vis && docker compose run --rm app`

---

## Phase 11: Scheduling

**Primary: Coolify Scheduled Tasks**

- Coolify dashboard → Service → Scheduled Tasks
- Command: `docker compose run --rm app`
- Cron: `0 5 * * *` (05:00 UTC = 08:00 AM Istanbul)

**Fallback: Host crontab**

```cron
0 5 * * * cd /opt/vis && docker compose run --rm app >> /opt/vis/output/cron.log 2>&1
```

**Optional: `scheduler.py` with APScheduler**

- `CronTrigger(hour=8, minute=0, timezone="Europe/Istanbul")`
- Run as a long-lived process
- Not recommended for Docker (use cron instead)

---

## Phase 12: Testing

**Directory: `tests/`**

**Test files:**

- `tests/test_summarize.py` — JSON parse strategy tests
- `tests/test_report.py` — Markdown report generation tests
- `tests/test_db.py` — DB operations (requires test PostgreSQL)
- `tests/test_transcript.py` — Transcript parsing/truncation tests
- `tests/test_pdf.py` — PDF generation from sample markdown
- `tests/test_config.py` — Config validation and defaults

**`tests/test_summarize.py`:**

```python
# Test _parse_llm_response with:
- Valid JSON string
- JSON wrapped in ```json ... ``` markdown code block
- JSON with leading/trailing text ("Here is the result: {...}")
- Invalid JSON → returns None
- Valid JSON but missing required keys → returns None
- Empty string → returns None
```

**`tests/test_report.py`:**

```python
# Test generate_report with:
- Normal case: 3 videos with summaries, 1 failed
- No failed videos → no "Videos Without Transcript" section
- No successful videos, only failed → still generates report
- Special characters in video titles
- Empty key_ideas list
```

**`tests/test_db.py`:**

```python
# Test against real PostgreSQL (docker-compose test service or local):
- init_db creates tables and indexes
- upsert_video insert + update
- get_processed_ids returns correct set
- get_retryable_videos respects retry window
- log_run + get_unsent_reports + mark_telegram_sent
```

**`tests/test_transcript.py`:**

```python
# Test transcript processing:
- Truncation at 50,000 characters
- VTT/SRT parsing to plain text (for yt-dlp output)
- Language code extraction
```

**`tests/test_pdf.py`:**

```python
# Test PDF generation:
- Valid markdown → produces valid PDF file
- All markdown elements render without error (headers, bold, bullets, tables, links, hr)
- Empty sections handled gracefully
- Output file exists and is >0 bytes
```

**`tests/test_config.py`:**

```python
# Test config loading:
- Missing required key → raises ValueError with key name
- Default values applied correctly
- Sensitive keys are masked in string representation
```

**Running tests:**

```bash
# Local (requires PostgreSQL running):
pytest tests/ -v

# Skip DB tests if no PostgreSQL:
pytest tests/ -v -k "not test_db"
```

---

## Error Handling Summary

| Scenario | Behavior |
|----------|----------|
| Missing .env key | Fail fast at startup with clear message naming the key |
| DB connection fails | Fail fast at startup with clear message (check DATABASE_URL) |
| YouTube API quota exceeded | Log error, abort run, exit 1 |
| Playlist empty | Log info, exit 0 |
| No new videos | Log info, exit 0 |
| Deleted/private video in playlist | Skip, log warning, continue |
| Transcript unavailable (< 3 days) | Mark `no_transcript`, retry next run, show in report |
| Transcript unavailable (>= 3 days) | Mark `gave_up`, stop retrying, show in report as "watch manually" |
| youtube-transcript-api blocked | Fall through to yt-dlp, log warning |
| Both transcript methods fail | Treat as no transcript (retry logic applies) |
| LLM API 429 (rate limit) | Read `retry-after` header, exponential backoff, 3 retries |
| LLM API 5xx | Retry 3 times with 2s backoff, then skip video (leave unprocessed) |
| LLM API 4xx (non-429) | Log error with response body, skip video, leave unprocessed |
| LLM output not valid JSON | Try 3 parse strategies, if all fail skip (leave unprocessed) |
| PDF generation fails | Log error, send error text via Telegram |
| Telegram PDF send fails | Send error text message, log run as telegram_sent=false |
| Telegram text send also fails | Log error, exit 1 (report exists locally in output/) |
| Previous run's Telegram failed | Next run detects unsent report, retries sending |
| Crash mid-pipeline | DB saves are incremental, completed videos won't reprocess |

---

## Implementation Order

| Step | File(s) | Depends On |
|------|---------|-----------:|
| 1 | `.gitignore`, `.env.example`, `.env`, `requirements.txt` | Nothing |
| 2 | `config.py` + `tests/test_config.py` | Step 1 |
| 3 | `db.py` + `tests/test_db.py` | `config.py` |
| 4 | `youtube.py` | `config.py`, `db.py` |
| 5 | `transcript.py` + `tests/test_transcript.py` | Nothing |
| 6 | `summarize.py` + `tests/test_summarize.py` | `config.py` |
| 7 | `report.py` + `tests/test_report.py` | Nothing |
| 8 | `pdf.py` + `tests/test_pdf.py` | Nothing |
| 9 | `telegram.py` | `config.py` |
| 10 | `main.py` | All above |
| 11 | `Dockerfile`, `docker-compose.yaml` | All above |
| 12 | `scheduler.py` | `main.py` |

---

## Security Checklist

- [ ] `.env` in `.gitignore` — never committed
- [ ] API keys never logged — config masks sensitive values
- [ ] No tokens in error messages sent to Telegram
- [ ] `DATABASE_URL` password never logged
- [ ] Docker: no secrets in Dockerfile or docker-compose.yaml (all via env vars)
- [ ] OpenRouter: set monthly budget limit in dashboard
- [ ] Telegram bot token: if leaked, regenerate via @BotFather

---

## Final File List

```
vis/
  .gitignore
  .env                      # user fills, not committed
  .env.example
  requirements.txt
  CLAUDE.md
  spec.md
  plan.md
  config.py
  db.py
  youtube.py
  transcript.py
  summarize.py
  report.py
  pdf.py
  telegram.py
  main.py
  scheduler.py              # optional
  Dockerfile
  docker-compose.yaml
  tests/
    test_config.py
    test_db.py
    test_transcript.py
    test_summarize.py
    test_report.py
    test_pdf.py
  output/
    report_YYYY-MM-DD_HHMMSS.md
    report_YYYY-MM-DD_HHMMSS.pdf
    vis.log
```
