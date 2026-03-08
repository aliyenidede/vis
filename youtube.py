import logging

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from db import get_processed_ids, get_retryable_videos

logger = logging.getLogger(__name__)


def fetch_playlist_videos(playlist_id: str, api_key: str, max_results: int = 100) -> list:
    logger.info("Fetching playlist videos (max %d)", max_results)
    youtube = build("youtube", "v3", developerKey=api_key)

    videos = []
    next_page_token = None

    while len(videos) < max_results:
        request = youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=min(50, max_results - len(videos)),
            pageToken=next_page_token,
        )

        try:
            response = request.execute()
        except HttpError as e:
            if e.resp.status == 403:
                logger.error("YouTube API quota exceeded: %s", e)
            raise

        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            video_id = snippet.get("resourceId", {}).get("videoId")

            if not video_id:
                logger.warning("Skipping playlist item with no videoId: %s", item.get("id"))
                continue

            title = snippet.get("title", "")
            if title in ("Deleted video", "Private video"):
                logger.warning("Skipping %s: %s", title.lower(), video_id)
                continue

            videos.append({
                "video_id": video_id,
                "title": title,
                "channel_title": snippet.get("videoOwnerChannelTitle", ""),
                "published_at": snippet.get("publishedAt", ""),
                "url": f"https://youtube.com/watch?v={video_id}",
            })

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    logger.info("Fetched %d videos from playlist", len(videos))
    return videos


def get_new_videos(
    playlist_id: str, api_key: str, max_results: int, db_pool
) -> list:
    all_videos = fetch_playlist_videos(playlist_id, api_key, max_results)
    processed_ids = get_processed_ids(db_pool)

    new_videos = [v for v in all_videos if v["video_id"] not in processed_ids]
    logger.info("Found %d new videos (out of %d total)", len(new_videos), len(all_videos))

    retryable = get_retryable_videos(db_pool, max_retry_days=3)
    retryable_ids = {v["video_id"] for v in retryable}

    # Add retryable videos that aren't already in the new list
    for v in all_videos:
        if v["video_id"] in retryable_ids and v["video_id"] not in {nv["video_id"] for nv in new_videos}:
            retry_info = next(r for r in retryable if r["video_id"] == v["video_id"])
            v["retry_count"] = retry_info["retry_count"]
            new_videos.append(v)

    if retryable:
        logger.info("Including %d retryable videos", len(retryable))

    return new_videos
