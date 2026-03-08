# VIS — Video Insight System

## Product Spec (Minimal PRD)

### 1. Overview

VIS (Video Insight System) is a small automation tool that extracts key information from YouTube videos without watching them.
The system reads videos from a specified playlist, retrieves transcripts, summarizes them using an LLM, and generates a daily PDF report.

Goal: allow the user to quickly understand the content of multiple videos in a few minutes.

---

### 2. Core Features

1. Playlist ingestion
   - Read videos from a specified YouTube playlist.

2. Transcript extraction
   - Retrieve the transcript of each video.

3. AI summarization
   - Send transcript text to an LLM via OpenRouter API.
   - Generate structured summaries.

4. Report generation
   - Compile all video summaries into a single Markdown report.

5. PDF export
   - Convert the Markdown report into a PDF document.

---

### 3. Input

- YouTube Playlist ID or URL
- OpenRouter API Key
- Output directory

Optional:

- Date filter (process only today's videos)

---

### 4. Output

A generated report:

```
Daily Video Insight Report
Date: YYYY-MM-DD

Video 1
Title
Link

Summary
Key Ideas

---

Video 2
...
```

Final output files:

- report.md
- report.pdf

---

### 5. System Flow

1. Fetch playlist videos
2. Extract video IDs
3. Retrieve transcripts
4. Summarize transcript with LLM
5. Store summaries
6. Build Markdown report
7. Convert Markdown → PDF

---

### 6. Tech Stack

Language:

- Python

Libraries:

- youtube-transcript-api
- requests
- markdown / templating
- pandoc (for PDF conversion)

LLM:

- OpenRouter API

---

### 7. Folder Structure

```
vis/
  main.py
  youtube.py
  transcript.py
  summarize.py
  report.py
  pdf.py
  config.py
  output/
```

---

### 8. CLI Usage

```
python main.py
```

Future optional CLI:

```
vis run
vis report
vis pdf
```

---

### 9. Non-Goals

The system will NOT include:

- knowledge base
- vector databases
- long-term storage
- recommendation engines
- action item generation

The tool only extracts and summarizes video information.

---

### 10. Success Criteria

The system successfully:

- processes all videos in the playlist
- generates summaries
- outputs a readable PDF report
- runs in under a few minutes for typical playlists
