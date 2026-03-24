# Plan: YouTube Channel Monitoring

## Overview

Extend VIS to monitor YouTube channels in addition to the existing playlist. Channels are managed via Telegram bot commands and stored in PostgreSQL. Channel videos are fetched via yt-dlp (same as playlist), merged with playlist videos, and processed through the existing pipeline. Reports combine both sources, grouped by origin.

## Phase 1: Data Layer (db.py)

### New table: `monitored_channels`

Add to `SCHEMA_SQL` in `src/vis/db.py`:

```
monitored_channels:
  - id: SERIAL PRIMARY KEY
  - channel_input: TEXT NOT NULL (what user provided — @handle, URL, etc.)
  - channel_name: TEXT (resolved display name, populated on first successful fetch)
  - added_at: TIMESTAMPTZ DEFAULT NOW() (cutoff: only videos after this are processed)
  - active: BOOLEAN DEFAULT TRUE
  - UNIQUE(channel_input)
```

### New column on `processed_videos`

Add `source` column (TEXT, DEFAULT 'playlist') to track where a video came from. Values: 'playlist', 'channel:<channel_input>'.

### New query functions

All follow existing pattern: `conn = pool.getconn()` / try-finally `pool.putconn(conn)`.

- `add_channel(pool, channel_input)` → INSERT into monitored_channels, return id. ON CONFLICT raise/ignore.
- `remove_channel(pool, channel_id)` → UPDATE SET active=FALSE WHERE id=channel_id (soft delete)
- `get_active_channels(pool)` → SELECT * FROM monitored_channels WHERE active=TRUE
- `update_channel_name(pool, channel_id, name)` → UPDATE channel_name WHERE id=channel_id

## Phase 2: YouTube Channel Fetching (youtube.py)

### New function: `fetch_channel_videos(channel_input, max_results=50)`

- Construct URL: if channel_input starts with `@`, use `https://www.youtube.com/{channel_input}/videos`; if starts with `http`, use as-is; else treat as channel ID: `https://www.youtube.com/channel/{channel_input}/videos`
- Use same yt-dlp options as `fetch_playlist_videos()`: `extract_flat=True`, `quiet=True`, `playlistend=max_results`
- Return same format: list of dicts with `video_id`, `title`, `channel_title`, `published_at`, `url`
- On success, also return the resolved channel name from yt-dlp metadata (for `channel_name` DB update)

### Modify: `get_new_videos(config, pool)`

Current behavior: fetches playlist videos, filters out processed ones, adds retryable ones.

New behavior:
1. Fetch playlist videos (existing logic, unchanged)
2. Fetch videos from ALL active monitored channels (call `get_active_channels()`, then `fetch_channel_videos()` for each)
3. For channel videos: filter by `added_at` cutoff (only videos published after channel was added)
4. Merge all videos, deduplicate by `video_id` (playlist takes priority if same video appears in both)
5. Filter out already-processed IDs (existing logic)
6. Tag each video with `source`: 'playlist' or 'channel:<channel_input>'
7. Return merged list

Rate limiting: 2s pause between channel fetches (same as transcript rate limit pattern).

## Phase 3: Pipeline Integration (main.py)

### Modify: `run_pipeline(config, pool)`

- `get_new_videos()` already returns merged list — no change to video processing loop
- Pass `source` field through to `upsert_video()` so it gets saved in DB
- Report generation: pass source info so report can group videos by origin

### Modify: `upsert_video()` call

Add `source` parameter to `upsert_video()` in `db.py`. Save to new `source` column.

## Phase 4: Report Grouping (report.py)

### Modify: `generate_report()`

- Accept source info for each video
- Group videos: first playlist videos, then channel videos (grouped by channel name)
- Add section headers: "Playlist" and "Channel: <name>" in the markdown report
- If all videos are from same source, no grouping header needed

## Phase 5: Bot Commands (bot.py)

### `/addchannel <url or @handle>`

1. Parse argument from message text
2. Validate: must have an argument
3. Call `add_channel(pool, channel_input)`
4. Attempt a test fetch via `fetch_channel_videos(channel_input, max_results=1)` to validate the channel exists
5. If fetch succeeds: update channel_name in DB, reply with success message showing resolved name
6. If fetch fails: remove the channel, reply with error
7. If duplicate: reply "already monitoring"

### `/rmchannel <id or name>`

1. Parse argument
2. Get active channels, match by id (number) or partial name match
3. Call `remove_channel(pool, matched_id)`
4. Reply with confirmation

### `/channels`

1. Call `get_active_channels(pool)`
2. Format list: `#id — channel_name (added_at)`
3. If empty: "No channels monitored"

### Registration

- Add all 3 commands to `BOT_COMMANDS` list
- Add handlers to `handlers` dict in `_handle_update()`
- Bot needs `pool` reference (already available via `self.pool` set in scheduler)

## Phase 6: Integration Verification

- Ensure existing playlist monitoring works unchanged
- Test channel add/remove/list via bot
- Verify pipeline processes channel + playlist videos together
- Verify report groups videos by source
