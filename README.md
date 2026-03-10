# VIS -- Video Insight System

Monitor a YouTube playlist, extract transcripts, summarize each video with an LLM, and get a daily PDF report on Telegram. Runs as a long-lived service with a built-in Telegram bot for on-demand control.

## Features

- **Automatic monitoring** -- checks your playlist daily, processes only new videos
- **3-layer transcript extraction** -- youtube-transcript-api, yt-dlp subtitles, Supadata API as fallback
- **LLM summarization** -- sends transcripts to OpenRouter (any model, default Gemini 2.0 Flash)
- **PDF reports** -- cover page, table of contents, formatted summaries
- **Telegram bot** -- 7 commands for status checks, manual runs, and system info
- **Retry logic** -- videos without transcripts are retried for 3 days before giving up
- **API budget tracking** -- monitors Supadata usage (100 credits/month) with automatic cutoff

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL
- [OpenRouter](https://openrouter.ai/) API key
- [Telegram Bot](https://core.telegram.org/bots#botfather) token
- [Supadata](https://supadata.ai/) API key (optional -- only needed if youtube-transcript-api and yt-dlp both fail, common on cloud servers)

### Local Setup

```bash
git clone https://github.com/aliyenidede/vis.git
cd vis

pip install -e .

cp .env.example .env
# Fill in your credentials (see Configuration below)

# Run pipeline once
python -m vis.main

# Run as service (daily scheduler + Telegram bot)
python -m vis.scheduler
```

### Docker (recommended)

```bash
git clone https://github.com/aliyenidede/vis.git
cd vis

cp .env.example .env
# Fill in your credentials (see Configuration below)

docker compose up --build
```

Docker Compose starts PostgreSQL and the app together. The app runs in scheduler mode: daily pipeline at 08:00 Istanbul time + Telegram bot always listening.

## Configuration

Copy `.env.example` to `.env` and fill in the values:

| Variable | Required | Description |
|----------|----------|-------------|
| `YOUTUBE_PLAYLIST_ID` | Yes | YouTube playlist ID to monitor (must be Public or Unlisted) |
| `OPENROUTER_API_KEY` | Yes | [OpenRouter](https://openrouter.ai/) API key for LLM summarization |
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Yes | Your Telegram chat ID (use [@userinfobot](https://t.me/userinfobot) to find it) |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `SUPADATA_API_KEY` | No | [Supadata](https://supadata.ai/) API key for transcript fallback |
| `OUTPUT_DIR` | No | Report output directory (default: `./output`) |
| `MAX_VIDEOS` | No | Max videos to fetch from playlist (default: `100`) |
| `LLM_MODEL` | No | OpenRouter model ID (default: `deepseek/deepseek-v3.2`) |
| `TRANSCRIPT_RETRY_DAYS` | No | Days to retry failed transcripts (default: `3`) |

When using Docker Compose, also set `POSTGRES_PASSWORD` in your `.env` -- the compose file uses it for both the database and the app's `DATABASE_URL`.

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and available commands |
| `/status` | Pipeline status, last run info, Supadata usage |
| `/check` | Check for new videos without consuming API credits |
| `/stats` | Detailed statistics -- videos by status, API usage, run count |
| `/run` | Trigger a pipeline run manually |
| `/pending` | List videos waiting for transcript retry |
| `/info` | System configuration and version |

## How It Works

### Pipeline Flow

```mermaid
flowchart TD
    A[Scheduled Trigger / /run command] --> B[Load Config & Init DB]
    B --> C{Unsent reports from\nprevious runs?}
    C -->|Yes| D[Retry sending via Telegram]
    C -->|No| E[Cleanup old reports + Expire retries]
    D --> E
    E --> F[Fetch YouTube Playlist via yt-dlp]
    F --> G[Filter new & retryable videos]
    G --> H{Any videos\nto process?}
    H -->|No| Z[Exit -- nothing to do]
    H -->|Yes| I[For each video]

    I --> J[Fetch Transcript]
    J --> K{Transcript\navailable?}
    K -->|No| L[Mark as no_transcript\nretry next run]
    K -->|Yes| M[Summarize via LLM]
    M --> N{Summary\nsuccessful?}
    N -->|No| O[Skip -- retry next run]
    N -->|Yes| P[Save to DB]

    L --> I
    O --> I
    P --> I

    I -->|All done| Q[Generate Markdown Report]
    Q --> R[Convert to PDF with cover + TOC]
    R --> S[Send PDF via Telegram]
    S --> T{Telegram\nsucceeded?}
    T -->|Yes| U[Done]
    T -->|No| V[Queue for retry]
    V --> U

    style A fill:#4a90d9,color:#fff
    style Z fill:#95a5a6,color:#fff
    style U fill:#27ae60,color:#fff
    style L fill:#e67e22,color:#fff
    style V fill:#e74c3c,color:#fff
```

### Transcript Extraction

Three layers, tried in order:

```mermaid
flowchart LR
    A[Video ID] --> B[youtube-transcript-api]
    B --> C{Found?}
    C -->|Yes| D[Return transcript]
    C -->|No| E[yt-dlp subtitle extraction]
    E --> F{Found?}
    F -->|Yes| D
    F -->|No| G{Supadata API\ncredits available?}
    G -->|Yes| H[Supadata API]
    H --> I{Found?}
    I -->|Yes| D
    I -->|No| J[Return None -- retry later]
    G -->|No| J

    style D fill:#27ae60,color:#fff
    style J fill:#e74c3c,color:#fff
```

Language priority: `en` > `en-US`/`en-GB` > `tr` > any manual > any auto-generated

### Retry Logic

Videos without transcripts are retried across runs:

| Day | Action |
|-----|--------|
| 1-3 | Retry transcript extraction each run |
| 4+  | Give up, report as "watch manually" |

## Project Structure

```
src/vis/
  config.py      # Environment config & validation
  db.py          # PostgreSQL pool, schema, queries
  youtube.py     # Playlist fetching via yt-dlp
  transcript.py  # 3-layer transcript extraction
  summarize.py   # LLM summarization via OpenRouter
  report.py      # Markdown report generation
  pdf.py         # PDF with cover page + TOC (fpdf2)
  telegram.py    # Telegram PDF delivery
  bot.py         # Telegram bot commands
  main.py        # Pipeline orchestrator + cleanup
  scheduler.py   # APScheduler cron + bot polling
```

## Self-Hosting

VIS is designed to run on any Docker host. If you use [Coolify](https://coolify.io/):

1. Connect your GitHub repo in Coolify UI
2. Set the environment variables (same keys as `.env.example`)
3. Deploy -- the app starts in scheduler mode automatically

For other platforms (VPS, Railway, Fly.io), deploy with Docker Compose or run `python -m vis.scheduler` directly.

## Running Tests

```bash
# Unit tests (no database needed)
pytest tests/ -v -k "not test_db"

# Full test suite (requires PostgreSQL)
TEST_DATABASE_URL=postgresql://vis:pass@localhost:5432/vis_test pytest tests/ -v
```

## Tech Stack

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) -- playlist fetching, no API key needed
- [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) -- primary transcript source
- [Supadata](https://supadata.ai/) -- server-side transcript fallback
- [OpenRouter](https://openrouter.ai/) -- LLM gateway (any model)
- [fpdf2](https://github.com/py-pdf/fpdf2) -- PDF generation
- [PostgreSQL](https://www.postgresql.org/) -- video tracking + API usage
- [APScheduler](https://github.com/agronholm/apscheduler) -- cron scheduling
- [Telegram Bot API](https://core.telegram.org/bots/api) -- report delivery + commands

## License

AGPL-3.0 -- see [LICENSE](LICENSE)
