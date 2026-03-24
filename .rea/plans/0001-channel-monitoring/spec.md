# Spec: YouTube Channel Monitoring

## Description

Add the ability to monitor specific YouTube channels alongside the existing playlist monitoring. When a monitored channel publishes a new video, it gets automatically processed through the existing pipeline (transcript → summarize → PDF → Telegram).

## Scope

### In scope
- Store monitored channels in PostgreSQL
- Fetch recent videos from monitored channels via yt-dlp
- Process channel videos through existing pipeline (same as playlist videos)
- Telegram bot commands to add/remove/list channels
- Channel check runs on same daily schedule as playlist (08:00 Istanbul)
- Only process videos published AFTER channel was added (no backfill)
- Combined report: playlist + channel videos in same PDF, grouped by source

### Out of scope
- Real-time webhook/push notifications (yt-dlp is polling-based)
- Per-channel custom schedules
- Separate reports per channel
- Channel analytics or statistics
- Video filtering by keywords/topics

## Constraints
- Must not break existing playlist monitoring
- Same rate limiting rules apply (2s transcript, 1s LLM)
- Channel videos share the same `processed_videos` table
- yt-dlp handles channel URL resolution (accepts @handle, /channel/ID, full URL)
