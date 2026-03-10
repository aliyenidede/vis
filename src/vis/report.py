import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def generate_report(
    videos_with_summaries: list,
    failed_videos: list,
    output_dir: str,
) -> str:
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    file_timestamp = now.strftime("%Y-%m-%d_%H%M%S")

    os.makedirs(output_dir, exist_ok=True)

    lines = []
    lines.append("# Daily Video Insight Report")
    lines.append(f"**Date:** {timestamp}")
    lines.append(f"**Videos processed:** {len(videos_with_summaries)}")
    lines.append(f"**Videos failed:** {len(failed_videos)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for i, video in enumerate(videos_with_summaries, 1):
        lines.append(f"## {i}. {video['title']}")
        lines.append(f"**Channel:** {video.get('channel_title', 'Unknown')}")
        lines.append(f"**Published:** {video.get('published_at', 'Unknown')}")
        lines.append(f"**Link:** {video.get('url', '')}")
        lines.append(f"**Category:** {video.get('category', 'Other')}")
        lines.append("")
        lines.append("### Summary")
        lines.append(video.get("summary", "No summary available."))
        lines.append("")
        lines.append("### Key Ideas & Takeaways")
        for idea in video.get("key_ideas", []):
            lines.append(f"- {idea}")
        lines.append("")
        lines.append("---")
        lines.append("")

    if failed_videos:
        lines.append("## Videos Without Transcript")
        lines.append("")
        lines.append("| # | Title | Channel | Link | Status |")
        lines.append("|---|-------|---------|------|--------|")
        for i, video in enumerate(failed_videos, 1):
            title = video.get("title", "Unknown")
            channel = video.get("channel_title", "Unknown")
            url = video.get("url", "")
            status = video.get("status", "no_transcript")
            retry_count = video.get("retry_count", 0)

            if status == "gave_up":
                status_text = f"Gave up after {retry_count} retries --watch manually"
            else:
                status_text = f"No transcript (attempt {retry_count + 1})"

            lines.append(f"| {i} | {title} | {channel} | [Link]({url}) | {status_text} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    report_path = os.path.join(output_dir, f"report_{file_timestamp}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info("Report generated: %s", report_path)
    return report_path
