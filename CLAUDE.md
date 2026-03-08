# VIS — Video Insight Summarizer

## What It Does

Monitors a YouTube playlist, fetches transcripts, summarizes them via LLM (OpenRouter), generates PDF reports, and delivers via Telegram. Runs daily via Docker/Coolify cron.

## Architecture

```
config.py   → Load .env, validate, expose Config dataclass
db.py       → PostgreSQL pool + schema + queries (psycopg2)
youtube.py  → Playlist fetch (YouTube Data API v3)
transcript.py → Dual extraction: youtube-transcript-api + yt-dlp fallback
summarize.py  → LLM summarization via OpenRouter (JSON output)
report.py   → Markdown report generation
pdf.py      → PDF conversion with fpdf2
telegram.py → Send PDF via Telegram Bot API
main.py     → Pipeline orchestrator
scheduler.py → Optional APScheduler scheduling
```

## Key Technical Rules

- **Config**: All env vars loaded in `config.py` — never read `os.environ` elsewhere
- **DB**: Always use `pool.getconn()` with try/finally `pool.putconn(conn)` — it's NOT a context manager
- **DB writes**: Explicit `conn.commit()`, `conn.rollback()` on error
- **Transcripts**: youtube-transcript-api v1.2+ uses instance methods: `YouTubeTranscriptApi().fetch()` not the old static `get_transcript()`
- **Sensitive data**: Never log API keys, tokens, DATABASE_URL passwords — use `_mask()` from config
- **Rate limiting**: 2s between transcript fetches, 1s between LLM calls

## Commands

```bash
# Run pipeline
python main.py

# Run tests (skip DB tests without PostgreSQL)
pytest tests/ -v -k "not test_db"

# Run all tests (requires PostgreSQL)
TEST_DATABASE_URL=postgresql://vis:pass@localhost:5432/vis_test pytest tests/ -v

# Docker
docker compose up --build
```

## Deployment

- Docker Compose: PostgreSQL + app
- Coolify: connect GitHub repo, set env vars in UI
- Cron: `0 5 * * *` (05:00 UTC = 08:00 Istanbul)
