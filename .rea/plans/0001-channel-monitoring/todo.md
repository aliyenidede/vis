## Todo

- [x] Add `monitored_channels` table and `source` column to `processed_videos` in db.py
      1. Add CREATE TABLE monitored_channels to SCHEMA_SQL (id, channel_input, channel_name, added_at, active, UNIQUE)
      2. Add ALTER TABLE processed_videos ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'playlist' to SCHEMA_SQL
      3. Add query functions: add_channel(), remove_channel(), get_active_channels(), update_channel_name()
      4. Update upsert_video() to accept and save source parameter
      Test: DB init creates new table, upsert_video saves source field

- [x] Add fetch_channel_videos() to youtube.py
      1. New function: construct URL from channel_input (@handle, URL, or channel ID)
      2. Use same yt-dlp options as fetch_playlist_videos() with extract_flat=True
      3. Return video list + resolved channel name from yt-dlp metadata
      Test: function returns videos in same format as fetch_playlist_videos

- [x] Modify get_new_videos() in youtube.py to include channel videos
      1. After playlist fetch, call get_active_channels() and fetch_channel_videos() for each
      2. Filter channel videos by added_at cutoff (only after channel was added)
      3. Merge and deduplicate by video_id (playlist priority)
      4. Tag each video with source field ('playlist' or 'channel:<channel_input>')
      5. 2s pause between channel fetches for rate limiting
      Test: merged list contains both playlist and channel videos, no duplicates

- [x] Update pipeline to pass source through (main.py + report.py)
      1. Pass source field from video dict through to upsert_video() in main.py
      2. Pass source info to generate_report() in report.py
      3. Group videos in report by source: playlist section, then per-channel sections
      Test: report markdown shows grouped sections

- [x] Add bot commands: /addchannel, /rmchannel, /channels (bot.py)
      1. Add 3 entries to BOT_COMMANDS list
      2. Add 3 handlers to handlers dict in _handle_update()
      3. Implement _cmd_addchannel(): parse arg, add to DB, test fetch, update name, reply
      4. Implement _cmd_rmchannel(): parse arg, match by id or name, soft delete, reply
      5. Implement _cmd_channels(): list active channels with id, name, added_at
      6. Handle edge cases: missing arg, invalid channel, duplicate, not found
      Test: commands respond correctly via Telegram
