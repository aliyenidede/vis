# VIS — Video Insight System

## What It Does

Monitors a YouTube playlist and specific YouTube channels, fetches transcripts, summarizes them via LLM (OpenRouter), generates PDF reports, and delivers via Telegram. Runs as a long-lived service: Telegram bot for commands + APScheduler for daily cron.

## Architecture

```
src/vis/
  __init__.py    → Package marker
  config.py      → Load .env, validate, expose Config dataclass
  db.py          → PostgreSQL pool + schema + queries (psycopg2)
  youtube.py     → Playlist + channel fetch via yt-dlp (no API key needed)
  transcript.py  → 3-layer extraction: youtube-transcript-api → yt-dlp → Supadata
  summarize.py   → LLM summarization via OpenRouter (JSON output)
  report.py      → Markdown report generation (uses headline, briefing, analysis fields)
  pdf.py         → HTML/PDF conversion via Playwright (dark-theme, cover + TOC + content)
  telegram.py    → Send PDF via Telegram Bot API
  bot.py         → Telegram bot commands (/status, /check, /run, /stats, /pending, /addchannel, /rmchannel, /channels)
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
- **Channel monitoring**: Channels stored in `monitored_channels` table (soft-delete via `active` flag). Videos from channels tagged with `source='channel:<input>'` in `processed_videos`. Only videos published after `added_at` are processed.
- **Telegram Markdown**: Always wrap dynamic strings in backticks, use `parse_mode=None` for error messages

## Telegram Bot Commands

- `/start` — Welcome message
- `/status` — Last run info, Supadata usage
- `/check` — List new/pending videos WITHOUT consuming API credits
- `/stats` — Detailed statistics (videos by status, API usage, run count)
- `/run` — Trigger pipeline run manually
- `/pending` — List videos waiting for transcript retry
- `/info` — System configuration and version info
- `/addchannel <@handle or URL>` — Add a YouTube channel to monitor
- `/rmchannel <id or name>` — Remove a monitored channel
- `/channels` — List monitored channels

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

## Workflow Behavior

**Self-Improvement Loop** — After any correction from the user, append the lesson to `.rea/lessons.md`:
```
## YYYY-MM-DD
**Mistake:** what went wrong
**Rule:** what to do instead
```
If the lesson is architectural (e.g. a rule about what can import what, where logic must live), promote it to the relevant section of `CLAUDE.md` instead of lessons.md.

**Verification Standard** — Before marking any task complete, ask: "Would a staff engineer approve this?" Run tests, check logs, prove it works.

**Verification Iron Rule** — NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE. Before saying "done": run the command that proves it, read the full output, check exit code. "Should work" is not evidence.
