# VIS -- Video Insight System

Automated YouTube playlist monitor that fetches transcripts, summarizes them with an LLM, and delivers daily PDF reports via Telegram. Includes a Telegram bot for on-demand commands.

## How It Works

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

    I --> J[Fetch Transcript 3-layer]
    J --> K{Transcript\navailable?}
    K -->|No| L[Mark as no_transcript\nretry next run]
    K -->|Yes| M[Summarize via LLM\nOpenRouter API]
    M --> N{Summary\nsuccessful?}
    N -->|No| O[Skip -- retry next run]
    N -->|Yes| P[Save to DB as ok]

    L --> I
    O --> I
    P --> I

    I -->|All done| Q[Generate Markdown Report]
    Q --> R[Convert to PDF with cover + TOC]
    R --> S[Send PDF via Telegram]
    S --> T{Telegram\nsucceeded?}
    T -->|Yes| U[Log run -- done]
    T -->|No| V[Send error text message]
    V --> U

    style A fill:#4a90d9,color:#fff
    style Z fill:#95a5a6,color:#fff
    style U fill:#27ae60,color:#fff
    style L fill:#e67e22,color:#fff
    style V fill:#e74c3c,color:#fff
```

## Transcript Extraction

3-layer fallback for maximum reliability:

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

**Language priority:** `en` -> `en-US`/`en-GB` -> `tr` -> any manual -> any auto-generated

## Telegram Bot Commands

| Command    | Description                                       |
| ---------- | ------------------------------------------------- |
| `/start`   | Welcome message and available commands             |
| `/status`  | Pipeline status, last run info, Supadata usage     |
| `/check`   | Check for new videos (no API credits consumed)     |
| `/stats`   | Detailed statistics (videos, API usage, run count) |
| `/run`     | Trigger a pipeline run manually                    |
| `/pending` | List videos waiting for transcript retry           |

## Retry Logic

Videos without transcripts are retried across multiple runs:

| Day | Status          | Action                                    |
| --- | --------------- | ----------------------------------------- |
| 1   | `no_transcript` | Retry next run                            |
| 2   | `no_transcript` | Retry next run                            |
| 3   | `no_transcript` | Retry next run                            |
| 4+  | `gave_up`       | Stop retrying, report as "watch manually" |

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL
- OpenRouter API key
- Telegram Bot token
- Supadata API key (optional, for server-side transcript fallback)

### Setup

```bash
# Clone
git clone https://github.com/aliyenidede/vis.git
cd vis

# Install
pip install -e .

# Configure
cp .env.example .env
# Edit .env with your credentials

# Run once
python -m vis.main

# Run as service (scheduler + bot)
python -m vis.scheduler
```

### Docker

```bash
# Set POSTGRES_PASSWORD in .env
docker compose up --build
```

### Tests

```bash
pytest tests/ -v -k "not test_db"
```

## Project Structure

```
vis/
├── src/vis/           # Source package
│   ├── config.py      # Environment config & validation
│   ├── db.py          # PostgreSQL operations + API usage tracking
│   ├── youtube.py     # Playlist fetching via yt-dlp
│   ├── transcript.py  # 3-layer transcript extraction
│   ├── summarize.py   # LLM summarization via OpenRouter
│   ├── report.py      # Markdown report generation
│   ├── pdf.py         # PDF with cover page, TOC, content (fpdf2)
│   ├── telegram.py    # Telegram PDF delivery
│   ├── bot.py         # Telegram bot commands
│   ├── main.py        # Pipeline orchestrator + cleanup
│   └── scheduler.py   # APScheduler cron + bot polling
├── tests/             # Unit tests
├── docs/              # Spec & implementation plan
├── output/            # Generated reports & logs (auto-cleaned weekly)
├── Dockerfile
└── docker-compose.yaml
```

## Deployment

Designed for [Coolify](https://coolify.io/) with Docker Compose:

1. Connect GitHub repo in Coolify
2. Set environment variables in Coolify UI (same keys as `.env.example`)
3. App runs as long-lived service: daily cron at 08:00 Istanbul + Telegram bot always listening

## Tech Stack

- **yt-dlp** -- playlist fetching (no API key needed)
- **youtube-transcript-api** + **yt-dlp** + **Supadata API** -- 3-layer transcript extraction
- **OpenRouter** -- LLM summarization (default: Gemini 2.0 Flash)
- **fpdf2** -- PDF generation with cover page and TOC
- **PostgreSQL** -- video tracking + API usage monitoring
- **Telegram Bot API** -- report delivery + interactive commands
- **APScheduler** -- daily cron scheduling
