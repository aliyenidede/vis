import logging

import yt_dlp

from .db import get_processed_ids, get_retryable_videos

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
        if title in ("Deleted video", "Private video", "[Deleted video]", "[Private video]"):
            logger.warning("Skipping %s: %s", title.lower(), video_id)
            continue

        videos.append({
            "video_id": video_id,
            "title": title,
            "channel_title": entry.get("channel", entry.get("uploader", "")),
            "published_at": entry.get("upload_date", ""),
            "url": f"https://youtube.com/watch?v={video_id}",
        })

    logger.info("Fetched %d videos from playlist", len(videos))
    return videos


def get_new_videos(
    playlist_id: str, max_results: int, db_pool, transcript_retry_days: int = 3
) -> list:
    all_videos = fetch_playlist_videos(playlist_id, max_results)
    processed_ids = get_processed_ids(db_pool)

    new_videos = [v for v in all_videos if v["video_id"] not in processed_ids]
    logger.info("Found %d new videos (out of %d total)", len(new_videos), len(all_videos))

    retryable = get_retryable_videos(db_pool, max_retry_days=transcript_retry_days)
    retryable_ids = {v["video_id"] for v in retryable}

    # Add retryable videos that aren't already in the new list
    new_ids = {nv["video_id"] for nv in new_videos}
    for v in all_videos:
        if v["video_id"] in retryable_ids and v["video_id"] not in new_ids:
            retry_info = next(r for r in retryable if r["video_id"] == v["video_id"])
            v["retry_count"] = retry_info["retry_count"]
            new_videos.append(v)

    if retryable:
        logger.info("Including %d retryable videos", len(retryable))

    return new_videos
