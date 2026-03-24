import logging

import yt_dlp

import time
from datetime import datetime

from .db import (
    get_active_channels,
    get_processed_ids,
    get_retryable_videos,
    update_channel_name,
)

logger = logging.getLogger(__name__)


def fetch_playlist_videos(playlist_id: str, max_results: int = 100) -> list:
    logger.info("Fetching playlist videos via yt-dlp (max %d)", max_results)

    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
    }

    url = f"https://www.youtube.com/playlist?list={playlist_id}"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error("Failed to fetch playlist %s: %s", playlist_id, e)
        raise

    videos = []
    for entry in list(info.get("entries", []))[:max_results]:
        if not entry:
            continue

        video_id = entry.get("id")
        if not video_id:
            continue

        title = entry.get("title", "")
        if title in (
            "Deleted video",
            "Private video",
            "[Deleted video]",
            "[Private video]",
        ):
            logger.warning("Skipping %s: %s", title.lower(), video_id)
            continue

        videos.append(
            {
                "video_id": video_id,
                "title": title,
                "channel_title": entry.get("channel", entry.get("uploader", "")),
                "published_at": entry.get("upload_date", ""),
                "url": f"https://youtube.com/watch?v={video_id}",
            }
        )

    logger.info("Fetched %d videos from playlist", len(videos))
    return videos


def fetch_channel_videos(channel_input: str, max_results: int = 50) -> tuple:
    """Fetch videos from a YouTube channel.

    Args:
        channel_input: @handle, full URL, or bare channel ID
        max_results: Maximum number of videos to return

    Returns:
        Tuple of (videos_list, channel_name). On error returns ([], None).
    """
    if channel_input.startswith("@"):
        url = f"https://www.youtube.com/{channel_input}/videos"
    elif channel_input.startswith("http"):
        url = (
            channel_input
            if "/videos" in channel_input
            else channel_input.rstrip("/") + "/videos"
        )
    else:
        url = f"https://www.youtube.com/channel/{channel_input}/videos"

    logger.info("Fetching channel videos from %s (max %d)", url, max_results)

    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "playlistend": max_results,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        logger.warning("Failed to fetch channel %s: %s", channel_input, e)
        return [], None

    if info is None:
        logger.warning("yt-dlp returned no info for %s", channel_input)
        return [], None

    channel_name = info.get("channel", info.get("uploader", channel_input))

    videos = []
    for entry in list(info.get("entries", []))[:max_results]:
        if not entry:
            continue

        video_id = entry.get("id")
        if not video_id:
            continue

        title = entry.get("title", "")
        if title in (
            "Deleted video",
            "Private video",
            "[Deleted video]",
            "[Private video]",
        ):
            logger.warning("Skipping %s: %s", title.lower(), video_id)
            continue

        videos.append(
            {
                "video_id": video_id,
                "title": title,
                "channel_title": entry.get("channel", entry.get("uploader", "")),
                "published_at": entry.get("upload_date") or None,
                "url": f"https://youtube.com/watch?v={video_id}",
            }
        )

    logger.info("Fetched %d videos from channel %s", len(videos), channel_name)
    return videos, channel_name


def get_new_videos(
    playlist_id: str, max_results: int, db_pool, transcript_retry_days: int = 3
) -> list:
    # 1. Fetch playlist videos (existing logic)
    all_videos = fetch_playlist_videos(playlist_id, max_results)
    for v in all_videos:
        v["source"] = "playlist"

    processed_ids = get_processed_ids(db_pool)

    new_videos = [v for v in all_videos if v["video_id"] not in processed_ids]
    logger.info(
        "Found %d new playlist videos (out of %d total)",
        len(new_videos),
        len(all_videos),
    )

    # 2. Fetch videos from monitored channels
    channels = get_active_channels(db_pool)
    seen_ids = {v["video_id"] for v in all_videos}

    for channel in channels:
        channel_input = channel["channel_input"]
        added_at = channel["added_at"]

        videos, channel_name = fetch_channel_videos(channel_input)

        # Update resolved channel name in DB if we got one
        if channel_name and channel_name != channel.get("channel_name"):
            update_channel_name(db_pool, channel["id"], channel_name)

        # Filter: only videos published after channel was added
        for v in videos:
            if v["video_id"] in seen_ids:
                continue  # Deduplicate (playlist takes priority)
            seen_ids.add(v["video_id"])

            # Check published_at cutoff
            pub = v.get("published_at")
            if pub and added_at:
                try:
                    pub_date = datetime.strptime(pub, "%Y%m%d")
                    if pub_date.date() < added_at.date():
                        continue  # Published before channel was added
                except (ValueError, TypeError):
                    pass  # Can't parse date, include the video

            v["source"] = f"channel:{channel_input}"
            if v["video_id"] not in processed_ids:
                new_videos.append(v)

        if videos:
            logger.info(
                "Channel %s: %d videos fetched",
                channel_name or channel_input,
                len(videos),
            )

        time.sleep(2)  # Rate limiting between channel fetches

    # 3. Add retryable videos (from both playlist and channels)
    retryable = get_retryable_videos(db_pool, max_retry_days=transcript_retry_days)

    new_ids = {nv["video_id"] for nv in new_videos}
    for r in retryable:
        if r["video_id"] not in new_ids:
            new_videos.append(r)
            new_ids.add(r["video_id"])

    if retryable:
        logger.info("Including %d retryable videos", len(retryable))

    return new_videos
