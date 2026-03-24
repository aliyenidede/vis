"""Generate dark-theme HTML report and convert to PDF via Playwright (Chromium)."""

import logging
import os

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


def generate_pdf(
    videos: list,
    failed_videos: list,
    pdf_path: str,
    output_dir: str | None = None,
) -> str:
    """Generate a dark-theme PDF report from structured video data.

    Args:
        videos: List of processed video dicts (with summary, key_ideas, etc.)
        failed_videos: List of failed video dicts
        pdf_path: Output path for the PDF file
        output_dir: Directory for intermediate HTML file (defaults to pdf_path dir)

    Returns:
        The pdf_path on success.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d %H:%M:%S")

    html = _generate_html(
        videos=videos,
        failed_videos=failed_videos,
        date_str=date_str,
        processed=len(videos),
        failed=len(failed_videos),
    )

    # Save intermediate HTML (useful for debugging)
    if output_dir is None:
        output_dir = os.path.dirname(pdf_path)
    os.makedirs(output_dir, exist_ok=True)

    html_path = pdf_path.replace(".pdf", ".html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("HTML report saved: %s", html_path)

    # Convert HTML to PDF via Playwright (Chromium)
    html_abs = os.path.abspath(html_path)
    pdf_abs = os.path.abspath(pdf_path)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"file:///{html_abs.replace(os.sep, '/')}")
        page.pdf(
            path=pdf_abs,
            print_background=True,
            prefer_css_page_size=True,
        )
        browser.close()

    logger.info("PDF generated: %s", pdf_abs)
    return pdf_path


def _generate_html(videos, failed_videos, date_str, processed, failed):
    """Generate the full dark-theme HTML report."""

    video_sections = ""
    toc_items = ""

    for i, v in enumerate(videos, 1):
        headline = v.get("headline", v["title"])
        toc_items += f'<div class="toc-item"><span class="toc-num">{i:02d}</span><span class="toc-title">{headline}</span></div>\n'

        # Infographic
        infographic_html = ""
        info = v.get("infographic", {})
        if info and info.get("topic"):
            stats_html = ""
            for stat in info.get("key_stats", []):
                stats_html += f"<li>{stat}</li>"

            terms_html = ""
            for term in info.get("key_terms", []):
                terms_html += f"<li>{term}</li>"

            bottom = info.get("bottom_line", "")

            infographic_html = f"""
            <div class="infographic">
                <div class="infographic-header">INFOGRAPHIC</div>
                <div class="infographic-topic">{info["topic"]}</div>
                <div class="infographic-grid">
                    <div class="infographic-col">
                        <div class="infographic-label">Key Stats</div>
                        <ul>{stats_html}</ul>
                    </div>
                    <div class="infographic-col">
                        <div class="infographic-label">Key Terms</div>
                        <ul>{terms_html}</ul>
                    </div>
                </div>
                <div class="infographic-bottom">{bottom}</div>
            </div>"""

        # Key insights
        insights_html = ""
        for insight in v.get("key_insights", v.get("key_ideas", [])):
            insights_html += (
                f'<li><span class="bullet-icon">&rsaquo;</span> {insight}</li>'
            )

        # TL;DR
        tldr_html = ""
        if v.get("tldr"):
            tldr_html = f"""
            <div class="tldr-box">
                <div class="tldr-label">TL;DR</div>
                <p>{v["tldr"]}</p>
            </div>"""

        # Briefing paragraphs
        briefing_text = v.get("briefing", v.get("summary", ""))
        briefing_paras = ""
        for para in briefing_text.split("\n\n"):
            if para.strip():
                briefing_paras += f"<p>{para.strip()}</p>"
        if not briefing_paras:
            briefing_paras = f"<p>{briefing_text or 'No briefing available.'}</p>"

        # Analysis section
        analysis_html = ""
        analysis = v.get("analysis", {})
        if analysis and (
            analysis.get("why_it_matters")
            or analysis.get("critical_perspective")
            or analysis.get("open_questions")
        ):
            why_html = ""
            if analysis.get("why_it_matters"):
                why_html = f"""
                <div class="analysis-block">
                    <div class="analysis-label">Why It Matters</div>
                    <p>{analysis["why_it_matters"]}</p>
                </div>"""

            critical_html = ""
            if analysis.get("critical_perspective"):
                critical_html = f"""
                <div class="analysis-block">
                    <div class="analysis-label">Critical Perspective</div>
                    <p>{analysis["critical_perspective"]}</p>
                </div>"""

            questions_html = ""
            if analysis.get("open_questions"):
                q_items = ""
                for q in analysis["open_questions"]:
                    q_items += f"<li>{q}</li>"
                questions_html = f"""
                <div class="analysis-block">
                    <div class="analysis-label">Open Questions</div>
                    <ul class="open-questions">{q_items}</ul>
                </div>"""

            analysis_html = f"""
            <div class="analysis-section">
                <h3>Analysis</h3>
                {why_html}
                {critical_html}
                {questions_html}
            </div>"""

        # YouTube link
        video_id = v.get("video_id", "")
        yt_link = ""
        if video_id:
            yt_link = f'<a class="meta-tag video-link" href="https://www.youtube.com/watch?v={video_id}" target="_blank"><span class="meta-icon">&#128279;</span> YouTube</a>'

        video_sections += f"""
        <div class="video-page">
            <div class="video-header">
                <div class="video-num">{i:02d}</div>
                <h2>{headline}</h2>
            </div>
            <div class="video-meta">
                <span class="meta-tag source-tag"><span class="meta-icon">&#9654;</span> {v.get("channel_title", "Unknown")} — {v["title"]}</span>
                <span class="meta-tag"><span class="meta-icon">&#9670;</span> {v.get("category", "Other")}</span>
                {yt_link}
            </div>

            {tldr_html}

            <div class="section">
                <h3>Briefing</h3>
                {briefing_paras}
            </div>

            <div class="section">
                <h3>Key Insights</h3>
                <ul class="key-ideas">{insights_html}</ul>
            </div>

            {analysis_html}

            {infographic_html}
        </div>
        """

    # Failed videos section
    failed_section = ""
    if failed_videos:
        failed_rows = ""
        for i, fv in enumerate(failed_videos, 1):
            status = fv.get("status", "no_transcript")
            retry_count = fv.get("retry_count", 0)
            if status == "gave_up":
                status_text = f"Gave up after {retry_count} retries"
            else:
                status_text = f"No transcript (attempt {retry_count + 1})"

            video_id = fv.get("video_id", "")
            link_html = (
                f'<a href="https://www.youtube.com/watch?v={video_id}" class="video-link">Link</a>'
                if video_id
                else ""
            )

            failed_rows += f"""
            <tr>
                <td>{i}</td>
                <td>{fv.get("title", "Unknown")}</td>
                <td>{fv.get("channel_title", "Unknown")}</td>
                <td>{link_html}</td>
                <td>{status_text}</td>
            </tr>"""

        failed_section = f"""
        <div class="failed-section">
            <h2>Videos Without Transcript</h2>
            <table class="failed-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Title</th>
                        <th>Channel</th>
                        <th>Link</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>{failed_rows}</tbody>
            </table>
        </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: 210mm 15000mm;
        margin: 0;
    }}

    * {{
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }}

    html, body {{
        background: #0c0f2d;
    }}

    body {{
        font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        color: #e0e0e0;
        font-size: 25pt;
        line-height: 1.6;
        width: 210mm;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
    }}

    /* ============ COVER PAGE ============ */
    .cover {{
        width: 210mm;
        height: 297mm;
        background: linear-gradient(135deg, #0a0e27 0%, #1a0a2e 40%, #0f1a3a 70%, #0a1e2e 100%);
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        position: relative;
        overflow: hidden;
    }}

    .cover::before {{
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, #00d4ff, #a855f7, #ec4899, #00d4ff);
    }}

    .cover::after {{
        content: "";
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, #ec4899, #a855f7, #00d4ff, #ec4899);
    }}

    .cover-glow-1 {{
        position: absolute;
        width: 300px;
        height: 300px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(0, 212, 255, 0.08) 0%, transparent 70%);
        top: -50px;
        right: -50px;
    }}

    .cover-glow-2 {{
        position: absolute;
        width: 400px;
        height: 400px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(168, 85, 247, 0.06) 0%, transparent 70%);
        bottom: -100px;
        left: -100px;
    }}

    .cover-glow-3 {{
        position: absolute;
        width: 200px;
        height: 200px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(236, 72, 153, 0.06) 0%, transparent 70%);
        top: 40%;
        left: 20%;
    }}

    .cover-content {{
        text-align: center;
        position: relative;
        z-index: 1;
    }}

    .cover-title {{
        font-size: 90pt;
        font-weight: 800;
        color: #ffffff;
        letter-spacing: 2px;
        margin-bottom: 8px;
    }}

    .cover-subtitle {{
        font-size: 28pt;
        color: #9ca3af;
        letter-spacing: 4px;
        text-transform: uppercase;
        margin-bottom: 40px;
    }}

    .cover-line {{
        width: 120px;
        height: 2px;
        background: linear-gradient(90deg, #00d4ff, #a855f7, #ec4899);
        margin: 0 auto 40px auto;
    }}

    .cover-date {{
        font-size: 35pt;
        color: #e0e0e0;
        margin-bottom: 50px;
    }}

    .cover-stats {{
        display: flex;
        gap: 40px;
        justify-content: center;
    }}

    .stat-box {{
        border: 1px solid rgba(0, 212, 255, 0.2);
        border-radius: 12px;
        padding: 20px 30px;
        background: rgba(15, 21, 53, 0.6);
        text-align: center;
        min-width: 140px;
    }}

    .stat-num {{
        font-size: 70pt;
        font-weight: 800;
        background: linear-gradient(135deg, #00d4ff, #a855f7);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }}

    .stat-label {{
        font-size: 20pt;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 2px;
        margin-top: 4px;
    }}

    .cover-footer {{
        position: absolute;
        bottom: 30px;
        font-size: 20pt;
        color: #4a5568;
        letter-spacing: 1px;
    }}

    /* ============ TOC PAGE ============ */
    .toc-page {{
        padding: 10mm 15mm;
    }}

    .toc-title-header {{
        font-size: 50pt;
        font-weight: 700;
        color: #ffffff;
        margin-bottom: 8px;
    }}

    .toc-line {{
        width: 60px;
        height: 2px;
        background: linear-gradient(90deg, #00d4ff, #a855f7);
        margin-bottom: 40px;
    }}

    .toc-item {{
        display: flex;
        align-items: baseline;
        gap: 16px;
        padding: 12px 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }}

    .toc-num {{
        font-size: 35pt;
        font-weight: 700;
        color: #00d4ff;
        min-width: 36px;
    }}

    .toc-title {{
        font-size: 25pt;
        color: #e0e0e0;
    }}

    /* ============ VIDEO PAGES ============ */
    .video-page {{
        padding: 10mm 15mm;
    }}

    .video-header {{
        display: flex;
        align-items: flex-start;
        gap: 16px;
        margin-bottom: 16px;
        padding-bottom: 16px;
        border-bottom: 2px solid;
        border-image: linear-gradient(90deg, #00d4ff, #a855f7, #ec4899) 1;
    }}

    .video-num {{
        font-size: 55pt;
        font-weight: 800;
        background: linear-gradient(135deg, #00d4ff, #a855f7);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        line-height: 1;
        min-width: 100px;
    }}

    .video-header h2 {{
        font-size: 35pt;
        font-weight: 700;
        color: #ffffff;
        line-height: 1.3;
    }}

    .video-meta {{
        display: flex;
        gap: 12px;
        margin-bottom: 24px;
        flex-wrap: wrap;
    }}

    .meta-tag {{
        font-size: 20pt;
        color: #9ca3af;
        background: rgba(255, 255, 255, 0.05);
        padding: 4px 12px;
        border-radius: 20px;
        border: 1px solid rgba(255, 255, 255, 0.08);
    }}

    .video-link {{
        color: #00d4ff;
        text-decoration: none;
    }}

    .meta-icon {{
        color: #00d4ff;
        margin-right: 4px;
    }}

    /* TL;DR Box */
    .tldr-box {{
        background: rgba(0, 212, 255, 0.05);
        border-left: 3px solid #00d4ff;
        border-radius: 0 8px 8px 0;
        padding: 16px 20px;
        margin-bottom: 24px;
    }}

    .tldr-label {{
        font-size: 20pt;
        font-weight: 700;
        color: #00d4ff;
        text-transform: uppercase;
        letter-spacing: 2px;
        margin-bottom: 6px;
    }}

    .tldr-box p {{
        color: #e0e0e0;
        font-size: 25pt;
        line-height: 1.6;
    }}

    /* Sections */
    .section {{
        margin-top: 24px;
        margin-bottom: 24px;
    }}

    .section h3 {{
        font-size: 28pt;
        font-weight: 700;
        color: #a855f7;
        margin-bottom: 12px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}

    .section p {{
        color: #d1d5db;
        margin-bottom: 10px;
        font-size: 24pt;
        line-height: 1.7;
    }}

    /* Key Ideas */
    .key-ideas {{
        list-style: none;
        padding: 0;
    }}

    .key-ideas li {{
        color: #d1d5db;
        font-size: 24pt;
        padding: 6px 0 6px 4px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        line-height: 1.5;
    }}

    .bullet-icon {{
        color: #00d4ff;
        font-weight: 700;
        font-size: 30pt;
        margin-right: 8px;
    }}

    /* ============ ANALYSIS SECTION ============ */
    .analysis-section {{
        margin-top: 24px;
        margin-bottom: 24px;
    }}

    .analysis-section h3 {{
        font-size: 28pt;
        font-weight: 700;
        color: #a855f7;
        margin-bottom: 16px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}

    .analysis-block {{
        background: rgba(168, 85, 247, 0.04);
        border-left: 3px solid rgba(168, 85, 247, 0.3);
        border-radius: 0 8px 8px 0;
        padding: 14px 20px;
        margin-bottom: 14px;
    }}

    .analysis-label {{
        font-size: 20pt;
        font-weight: 700;
        color: #ec4899;
        text-transform: uppercase;
        letter-spacing: 2px;
        margin-bottom: 6px;
    }}

    .analysis-block p {{
        color: #d1d5db;
        font-size: 24pt;
        line-height: 1.7;
    }}

    .open-questions {{
        list-style: none;
        padding: 0;
    }}

    .open-questions li {{
        color: #d1d5db;
        font-size: 24pt;
        padding: 6px 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        line-height: 1.5;
    }}

    .open-questions li::before {{
        content: "?";
        color: #ec4899;
        font-weight: 700;
        font-size: 28pt;
        margin-right: 10px;
    }}

    .source-tag {{
        font-size: 18pt;
        color: #6b7280;
    }}

    /* ============ INFOGRAPHIC ============ */
    .infographic {{
        background: rgba(15, 21, 53, 0.8);
        border: 1px solid rgba(168, 85, 247, 0.2);
        border-radius: 12px;
        padding: 24px;
        margin-top: 20px;
        position: relative;
        overflow: hidden;
    }}

    .infographic::before {{
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, #00d4ff, #a855f7, #ec4899);
    }}

    .infographic-header {{
        font-size: 18pt;
        font-weight: 700;
        color: #a855f7;
        letter-spacing: 3px;
        text-transform: uppercase;
        margin-bottom: 4px;
    }}

    .infographic-topic {{
        font-size: 33pt;
        font-weight: 700;
        color: #ffffff;
        margin-bottom: 16px;
    }}

    .infographic-grid {{
        display: flex;
        gap: 24px;
        margin-bottom: 16px;
    }}

    .infographic-col {{
        flex: 1;
    }}

    .infographic-label {{
        font-size: 18pt;
        font-weight: 700;
        color: #00d4ff;
        text-transform: uppercase;
        letter-spacing: 2px;
        margin-bottom: 8px;
    }}

    .infographic-col ul {{
        list-style: none;
        padding: 0;
    }}

    .infographic-col li {{
        font-size: 21pt;
        color: #d1d5db;
        padding: 3px 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }}

    .infographic-bottom {{
        background: linear-gradient(90deg, rgba(236, 72, 153, 0.1), rgba(168, 85, 247, 0.1));
        border-radius: 8px;
        padding: 12px 16px;
        font-size: 24pt;
        font-weight: 600;
        color: #ec4899;
        text-align: center;
    }}

    /* ============ FAILED VIDEOS TABLE ============ */
    .failed-section {{
        padding: 10mm 15mm;
    }}

    .failed-section h2 {{
        font-size: 35pt;
        font-weight: 700;
        color: #ffffff;
        margin-bottom: 20px;
    }}

    .failed-table {{
        width: 100%;
        border-collapse: collapse;
    }}

    .failed-table th {{
        font-size: 18pt;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 1px;
        text-align: left;
        padding: 8px 12px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }}

    .failed-table td {{
        font-size: 23pt;
        color: #d1d5db;
        padding: 8px 12px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }}
</style>
</head>
<body>

    <!-- COVER PAGE -->
    <div class="cover">
        <div class="cover-glow-1"></div>
        <div class="cover-glow-2"></div>
        <div class="cover-glow-3"></div>
        <div class="cover-content">
            <div class="cover-title">VIS</div>
            <div class="cover-subtitle">Video Insight System</div>
            <div class="cover-line"></div>
            <div class="cover-date">{date_str}</div>
            <div class="cover-stats">
                <div class="stat-box">
                    <div class="stat-num">{processed}</div>
                    <div class="stat-label">Processed</div>
                </div>
                <div class="stat-box">
                    <div class="stat-num">{failed}</div>
                    <div class="stat-label">Failed</div>
                </div>
            </div>
        </div>
        <div class="cover-footer">Generated by VIS (Video Insight System)</div>
    </div>

    <!-- TABLE OF CONTENTS -->
    <div class="toc-page">
        <div class="toc-title-header">Contents</div>
        <div class="toc-line"></div>
        {toc_items}
    </div>

    <!-- VIDEO PAGES -->
    {video_sections}

    <!-- FAILED VIDEOS -->
    {failed_section}

</body>
</html>"""

    return html
