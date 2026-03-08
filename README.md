# VIS — Video Insight Summarizer

Automated YouTube playlist monitor that fetches transcripts, summarizes them with an LLM, and delivers daily PDF reports via Telegram.

## How It Works

```mermaid
flowchart TD
    A[Scheduled Trigger] --> B[Load Config & Init DB]
    B --> C{Unsent reports from\nprevious runs?}
    C -->|Yes| D[Retry sending via Telegram]
    C -->|No| E[Expire old transcript retries]
    D --> E
    E --> F[Fetch YouTube Playlist]
    F --> G[Filter new & retryable videos]
    G --> H{Any videos\nto process?}
    H -->|No| Z[Exit — nothing to do]
    H -->|Yes| I[For each video]

    I --> J[Fetch Transcript]
    J --> K{Transcript\navailable?}
    K -->|No| L[Mark as no_transcript\nretry next run]
    K -->|Yes| M[Summarize via LLM\nOpenRouter API]
    M --> N{Summary\nsuccessful?}
    N -->|No| O[Skip — retry next run]
    N -->|Yes| P[Save to DB as ok]

    L --> I
    O --> I
    P --> I

    I -->|All done| Q[Generate Markdown Report]
    Q --> R[Convert to PDF]
    R --> S[Send PDF via Telegram]
    S --> T{Telegram\nsucceeded?}
    T -->|Yes| U[Log run — done]
    T -->|No| V[Send error text message]
    V --> U

    style A fill:#4a90d9,color:#fff
    style Z fill:#95a5a6,color:#fff
    style U fill:#27ae60,color:#fff
    style L fill:#e67e22,color:#fff
    style V fill:#e74c3c,color:#fff
```

## Transcript Extraction

Dual-method approach for maximum reliability:

```mermaid
flowchart LR
    A[Video ID] --> B[youtube-transcript-api]
    B --> C{Found?}
    C -->|Yes| D[Return transcript]
    C -->|No| E[yt-dlp fallback]
    E --> F{Found?}
    F -->|Yes| D
    F -->|No| G[Return None — retry later]

    style D fill:#27ae60,color:#fff
    style G fill:#e74c3c,color:#fff
```

**Language priority:** `en` → `en-US`/`en-GB` → `tr` → any manual → any auto-generated

## Retry Logic

Videos without transcripts are retried across multiple runs:

| Day | Status | Action |
|-----|--------|--------|
| 1 | `no_transcript` | Retry next run |
| 2 | `no_transcript` | Retry next run |
| 3 | `no_transcript` | Retry next run |
| 4+ | `gave_up` | Stop retrying, report as "watch manually" |

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL
- YouTube Data API key
- OpenRouter API key
- Telegram Bot token

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

# Run
python -m vis.main
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
│   ├── db.py          # PostgreSQL operations
│   ├── youtube.py     # Playlist fetching
│   ├── transcript.py  # Transcript extraction (dual method)
│   ├── summarize.py   # LLM summarization via OpenRouter
│   ├── report.py      # Markdown report generation
│   ├── pdf.py         # PDF conversion (fpdf2)
│   ├── telegram.py    # Telegram delivery
│   ├── main.py        # Pipeline orchestrator
│   └── scheduler.py   # Optional APScheduler
├── tests/             # Unit tests
├── docs/              # Spec & implementation plan
├── output/            # Generated reports & logs
├── Dockerfile
└── docker-compose.yaml
```

## Deployment

Designed for [Coolify](https://coolify.io/) with Docker Compose:

1. Connect GitHub repo in Coolify
2. Set environment variables in Coolify UI (same keys as `.env.example`)
3. Add scheduled task: `0 5 * * *` (05:00 UTC = 08:00 Istanbul)

## Tech Stack

- **YouTube Data API v3** — playlist fetching
- **youtube-transcript-api** + **yt-dlp** — transcript extraction
- **OpenRouter** — LLM summarization (default: Gemini 2.0 Flash)
- **fpdf2** — PDF generation
- **PostgreSQL** — processed video tracking
- **Telegram Bot API** — report delivery
