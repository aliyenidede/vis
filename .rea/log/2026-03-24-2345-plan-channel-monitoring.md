# Plan: channel-monitoring

Date: 2026-03-24 23:45:00
Plan: .rea/plans/0001-channel-monitoring/
Status: completed

## Summary
Add YouTube channel monitoring to VIS. Users can add channels via Telegram bot commands (/addchannel, /rmchannel, /channels). New videos from monitored channels are automatically processed through the existing pipeline alongside playlist videos. Reports combine both sources, grouped by origin.

## Decisions made
- Check frequency: same daily schedule (08:00 Istanbul), no separate interval
- Only process videos published after channel was added (no backfill)
- Combined reports: playlist + channel videos in single PDF, grouped by source
- Soft delete for channel removal (active=FALSE)

## Human decisions
- User chose daily (24h) check on same schedule instead of more frequent polling
- User chose no backfill — only new videos after channel is added
- User chose combined reports over separate per-channel reports
