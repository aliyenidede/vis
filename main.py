import logging
import os
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from config import Config
from db import (
    init_db, close_pool, log_run, get_unsent_reports,
    mark_telegram_sent, expire_old_retries, upsert_video,
)
from youtube import get_new_videos
from transcript import get_transcript
from summarize import summarize_transcript
from report import generate_report
from pdf import markdown_to_pdf
from telegram import send_pdf, send_error_message

logger = logging.getLogger("vis")


def setup_logging(output_dir: str):
    os.makedirs(output_dir, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    root.addHandler(console)

    log_path = os.path.join(output_dir, "vis.log")
    file_handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


def run():
    # 1. Load config
    config = Config.load()

    # 2. Setup logging
    setup_logging(config.output_dir)
    logger.info("VIS pipeline starting")

    # 3. Initialize DB
    pool = init_db(config.database_url)

    try:
        # 4. Check for unsent reports from previous runs
        unsent = get_unsent_reports(pool)
        for report in unsent:
            pdf_path = report["report_path"]
            if pdf_path and os.path.exists(pdf_path):
                logger.info("Retrying unsent report: %s", pdf_path)
                caption = f"Daily Video Insight Report (retry) — {os.path.basename(pdf_path)}"
                if send_pdf(config.telegram_bot_token, config.telegram_chat_id, pdf_path, caption):
                    mark_telegram_sent(pool, report["id"])

        # 5. Expire old retries
        expired = expire_old_retries(pool, config.transcript_retry_days)
        failed_videos = [
            {**v, "status": "gave_up"} for v in expired
        ]

        # 6-7. Fetch and filter videos
        new_videos = get_new_videos(
            config.youtube_playlist_id,
            config.youtube_api_key,
            config.max_videos,
            pool,
        )

        # 8. Check if there's work to do
        if not new_videos and not expired:
            logger.info("No new videos and no expired retries. Nothing to do.")
            return

        # 9. Process each video
        videos_with_summaries = []

        for video in new_videos:
            video_id = video["video_id"]
            logger.info("Processing: %s (%s)", video["title"], video_id)

            # 9a. Fetch transcript
            transcript_text, lang = get_transcript(video_id)
            time.sleep(2)  # Rate limiting between transcript fetches

            # 9b. No transcript
            if not transcript_text:
                retry_count = video.get("retry_count", 0) + 1
                upsert_video(pool, {
                    "video_id": video_id,
                    "title": video["title"],
                    "channel_title": video.get("channel_title"),
                    "published_at": video.get("published_at"),
                    "url": video.get("url"),
                    "status": "no_transcript",
                    "retry_count": retry_count,
                })
                failed_videos.append({**video, "status": "no_transcript", "retry_count": retry_count})
                logger.warning("No transcript for %s (retry %d)", video_id, retry_count)
                continue

            # 9c. Summarize
            time.sleep(1)  # Rate limiting between API calls
            summary_data = summarize_transcript(
                transcript_text, video["title"],
                config.openrouter_api_key, config.llm_model,
            )

            if not summary_data:
                logger.warning("Summarization failed for %s, will retry next run", video_id)
                continue

            # 9d. Save to DB
            upsert_video(pool, {
                "video_id": video_id,
                "title": video["title"],
                "channel_title": video.get("channel_title"),
                "published_at": video.get("published_at"),
                "url": video.get("url"),
                "status": "ok",
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "summary": summary_data["summary"],
                "key_ideas": summary_data["key_ideas"],
                "category": summary_data["category"],
                "transcript_language": lang,
            })

            videos_with_summaries.append({
                **video,
                "summary": summary_data["summary"],
                "key_ideas": summary_data["key_ideas"],
                "category": summary_data["category"],
            })
            logger.info("Successfully processed: %s", video["title"])

        # 10. Check if there's anything to report
        if not videos_with_summaries and not failed_videos:
            logger.info("No videos processed and no failures to report.")
            return

        # 11. Generate report
        md_path = generate_report(videos_with_summaries, failed_videos, config.output_dir)

        # 12. Convert to PDF
        pdf_path = md_path.replace(".md", ".pdf")
        markdown_to_pdf(md_path, pdf_path)

        # 13. Send via Telegram
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        caption = f"Daily Video Insight Report — {now} — {len(videos_with_summaries)} videos"
        telegram_sent = send_pdf(config.telegram_bot_token, config.telegram_chat_id, pdf_path, caption)

        # 14. Log run
        run_id = log_run(pool, {
            "videos_found": len(new_videos),
            "videos_processed": len(videos_with_summaries),
            "videos_skipped": len(failed_videos),
            "report_path": pdf_path,
            "success": True,
            "telegram_sent": telegram_sent,
        })

        # 15. If Telegram failed, send error message
        if not telegram_sent:
            error_msg = f"VIS: PDF delivery failed. Report saved locally at {pdf_path}."
            send_error_message(config.telegram_bot_token, config.telegram_chat_id, error_msg)

        logger.info(
            "Pipeline complete: %d processed, %d failed, telegram=%s",
            len(videos_with_summaries), len(failed_videos), telegram_sent,
        )

    except Exception as e:
        logger.error("Pipeline failed: %s", e, exc_info=True)
        log_run(pool, {
            "success": False,
            "error_message": str(e),
        })
        sys.exit(1)
    finally:
        # 16. Close DB pool
        close_pool(pool)


if __name__ == "__main__":
    run()
