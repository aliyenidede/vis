import logging
import os
from collections import OrderedDict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _group_videos_by_source(videos: list) -> OrderedDict:
    """Group videos by source. Playlist first, then channels alphabetically."""
    groups = OrderedDict()
    for v in videos:
        source = v.get("source", "playlist")
        if source not in groups:
            groups[source] = []
        groups[source].append(v)

    # Sort: playlist first, then channels alphabetically
    sorted_groups = OrderedDict()
    if "playlist" in groups:
        sorted_groups["playlist"] = groups.pop("playlist")
    for key in sorted(groups.keys()):
        sorted_groups[key] = groups[key]
    return sorted_groups


def _source_heading(source: str) -> str:
    """Convert source key to a readable section heading."""
    if source == "playlist":
        return "Playlist"
    if source.startswith("channel:"):
        channel = source[len("channel:") :]
        return f"Channel: {channel}"
    return source


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
    lines.append("# VIS Daily Report")
    lines.append(f"**Date:** {timestamp}")
    lines.append(f"**Videos processed:** {len(videos_with_summaries)}")
    lines.append(f"**Videos failed:** {len(failed_videos)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Group videos by source (playlist vs channels)
    groups = _group_videos_by_source(videos_with_summaries)
    multiple_sources = len(groups) > 1

    i = 0
    for source, group_videos in groups.items():
        if multiple_sources:
            lines.append(f"# {_source_heading(source)}")
            lines.append("")

        for video in group_videos:
            i += 1
            headline = video.get("headline", video["title"])
            lines.append(f"## {i}. {headline}")
            lines.append(
                f"**Source:** {video.get('channel_title', 'Unknown')} — {video['title']}"
            )
            lines.append(f"**Published:** {video.get('published_at', 'Unknown')}")
            lines.append(f"**Link:** {video.get('url', '')}")
            lines.append(f"**Category:** {video.get('category', 'Other')}")
            lines.append("")

            # TL;DR
            tldr = video.get("tldr", "")
            if tldr:
                lines.append("### TL;DR")
                lines.append(tldr)
                lines.append("")

            # Briefing (main educational content)
            lines.append("### Briefing")
            lines.append(
                video.get("briefing", video.get("summary", "No briefing available."))
            )
            lines.append("")

            # Key Insights
            lines.append("### Key Insights")
            for insight in video.get("key_insights", video.get("key_ideas", [])):
                lines.append(f"- {insight}")
            lines.append("")

            # Analysis
            analysis = video.get("analysis", {})
            if analysis:
                if analysis.get("why_it_matters"):
                    lines.append("### Why It Matters")
                    lines.append(analysis["why_it_matters"])
                    lines.append("")
                if analysis.get("critical_perspective"):
                    lines.append("### Critical Perspective")
                    lines.append(analysis["critical_perspective"])
                    lines.append("")
                if analysis.get("open_questions"):
                    lines.append("### Open Questions")
                    for q in analysis["open_questions"]:
                        lines.append(f"- {q}")
                    lines.append("")

            # Infographic box
            infographic = video.get("infographic", {})
            if infographic and infographic.get("topic"):
                lines.append("### Infographic")
                lines.append(f"**Topic:** {infographic['topic']}")
                if infographic.get("key_stats"):
                    lines.append("**Key Stats:**")
                    for stat in infographic["key_stats"]:
                        lines.append(f"- {stat}")
                if infographic.get("key_terms"):
                    lines.append("**Key Terms:**")
                    for term in infographic["key_terms"]:
                        lines.append(f"- {term}")
                if infographic.get("bottom_line"):
                    lines.append(f"**Bottom Line:** {infographic['bottom_line']}")
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

            lines.append(
                f"| {i} | {title} | {channel} | [Link]({url}) | {status_text} |"
            )
        lines.append("")
        lines.append("---")
        lines.append("")

    report_path = os.path.join(output_dir, f"report_{file_timestamp}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info("Report generated: %s", report_path)
    return report_path
