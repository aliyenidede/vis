# VIS — Video Insight System

## What It Does

Monitors a YouTube playlist, fetches transcripts, summarizes them via LLM (OpenRouter), generates PDF reports, and delivers via Telegram. Runs as a long-lived service: Telegram bot for commands + APScheduler for daily cron.

## Architecture

```
src/vis/
  __init__.py    → Package marker
  config.py      → Load .env, validate, expose Config dataclass
  db.py          → PostgreSQL pool + schema + queries (psycopg2)
  youtube.py     → Playlist fetch via yt-dlp (no API key needed)
  transcript.py  → 3-layer extraction: youtube-transcript-api → yt-dlp → Supadata
  summarize.py   → LLM summarization via OpenRouter (JSON output)
  report.py      → Markdown report generation
  pdf.py         → PDF conversion with fpdf2 (cover page + TOC + content)
  telegram.py    → Send PDF via Telegram Bot API
  bot.py         → Telegram bot commands (/status, /check, /run, /stats, /pending)
  main.py        → Pipeline orchestrator + cleanup
  scheduler.py   → APScheduler + bot polling (long-lived process)
```

## Key Technical Rules

- **Config**: All env vars loaded in `config.py` — never read `os.environ` elsewhere
- **DB**: Always use `pool.getconn()` with try/finally `pool.putconn(conn)` — it's NOT a context manager
- **DB writes**: Explicit `conn.commit()`, `conn.rollback()` on error
- **Transcripts**: youtube-transcript-api v1.2+ uses instance methods: `YouTubeTranscriptApi().fetch()` not the old static `get_transcript()`
- **Sensitive data**: Never log API keys, tokens, DATABASE_URL passwords — use `_mask()` from config
- **Rate limiting**: 2s between transcript fetches, 1s between LLM calls
- **Supadata API**: 100 credits/month, auto-checked before use (95 credit threshold)
- **Report cleanup**: Old .md/.pdf files auto-deleted after 7 days

## Telegram Bot Commands

- `/start` — Welcome message
- `/status` — Last run info, Supadata usage
- `/check` — List new/pending videos WITHOUT consuming API credits
- `/stats` — Detailed statistics (videos by status, API usage, run count)
- `/run` — Trigger pipeline run manually
- `/pending` — List videos waiting for transcript retry

## Commands

```bash
# Run pipeline once
python -m vis.main

# Run as service (scheduler + bot)
python -m vis.scheduler

# Run tests (skip DB tests without PostgreSQL)
pytest tests/ -v -k "not test_db"

# Run all tests (requires PostgreSQL)
TEST_DATABASE_URL=postgresql://vis:pass@localhost:5432/vis_test pytest tests/ -v

# Docker
docker compose up --build
```

## Deployment

- Docker Compose: PostgreSQL + app (scheduler mode, long-lived)
- Coolify: connect GitHub repo, set env vars in UI
- Daily pipeline: 08:00 Istanbul time via APScheduler
- Telegram bot: always listening for commands
