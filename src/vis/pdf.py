import logging
import re

from fpdf import FPDF

logger = logging.getLogger(__name__)

# Unicode chars that Helvetica (latin-1) can't render
_UNICODE_REPLACEMENTS = {
    "\u2014": "--",   # em-dash
    "\u2013": "-",    # en-dash
    "\u2018": "'",    # left single quote
    "\u2019": "'",    # right single quote
    "\u201c": '"',    # left double quote
    "\u201d": '"',    # right double quote
    "\u2026": "...",  # ellipsis
    "\u2022": "-",    # bullet
    "\u00a0": " ",    # non-breaking space
}


def _sanitize(text: str) -> str:
    """Replace Unicode characters unsupported by Helvetica/latin-1."""
    for char, replacement in _UNICODE_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    # Fallback: strip remaining non-latin-1 chars
    return text.encode("latin-1", errors="replace").decode("latin-1")


class ReportPDF(FPDF):
    """Custom PDF with cover page, table of contents, and proper formatting."""

    def __init__(self):
        super().__init__()
        self._toc_entries = []

    def header(self):
        if self.page_no() <= 2:
            return
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 8, "Daily Video Insight Report", align="R")
        self.ln(10)

    def footer(self):
        if self.page_no() <= 1:
            return
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no() - 1}", align="C")

    def add_toc_entry(self, title: str, level: int = 1):
        self._toc_entries.append((title, self.page_no(), level))


def markdown_to_pdf(md_path: str, pdf_path: str) -> str:
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Sanitize all content for latin-1 compatibility (Helvetica font)
    content = _sanitize(content)
    lines = content.split("\n")

    meta = _parse_metadata(lines)
    videos = _parse_video_sections(lines)

    pdf = ReportPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(20, 20, 20)

    # --- Cover Page ---
    _render_cover_page(pdf, meta)

    # --- Table of Contents ---
    pdf.add_page()
    _render_toc(pdf, videos)

    # --- Content Pages ---
    # Skip lines until first H2 (header metadata is already on cover page)
    content_started = False

    for line in lines:
        stripped = line.strip()

        # Skip everything before the first H2
        if not content_started:
            if stripped.startswith("## "):
                content_started = True
            else:
                continue

        if not stripped:
            pdf.ln(4)
            continue

        # Horizontal rule
        if stripped == "---":
            pdf.ln(3)
            y = pdf.get_y()
            pdf.set_draw_color(200, 200, 200)
            pdf.line(20, y, pdf.w - 20, y)
            pdf.ln(6)
            continue

        # H1 — skip
        if stripped.startswith("# ") and not stripped.startswith("## "):
            continue

        # H2 — video title or section header
        if stripped.startswith("## "):
            text = stripped[3:]
            # New page for each numbered video section
            if re.match(r"^\d+\.", text):
                pdf.add_page()
                pdf.add_toc_entry(text, level=1)
            else:
                # Non-numbered H2 (e.g. "Videos Without Transcript")
                pdf.ln(6)
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_text_color(0, 51, 102)
            pdf.multi_cell(0, 8, text)
            pdf.ln(3)
            continue

        # H3
        if stripped.startswith("### "):
            text = stripped[4:]
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(51, 51, 51)
            pdf.multi_cell(0, 7, text)
            pdf.ln(2)
            continue

        # Metadata lines (**Key:** Value)
        if stripped.startswith("**") and ":**" in stripped:
            _render_metadata_line(pdf, stripped)
            continue

        # Table row
        if stripped.startswith("|"):
            _render_table_row(pdf, stripped)
            continue

        # Bullet point
        if stripped.startswith("- "):
            text = stripped[2:]
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(0, 0, 0)
            x = pdf.get_x()
            pdf.set_x(x + 8)
            pdf.cell(5, 6, "-")
            pdf.set_x(x + 14)
            pdf.multi_cell(pdf.w - 20 - x - 14, 6, text)
            pdf.ln(1)
            continue

        # Regular paragraph
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 6, stripped)
        pdf.ln(2)

    pdf.output(pdf_path)
    logger.info("PDF generated: %s (%d pages)", pdf_path, pdf.page_no())
    return pdf_path


def _parse_metadata(lines: list) -> dict:
    meta = {"date": "", "processed": "0", "failed": "0"}
    for line in lines[:10]:
        stripped = line.strip()
        if stripped.startswith("**Date:**"):
            meta["date"] = stripped.replace("**Date:**", "").strip()
        elif stripped.startswith("**Videos processed:**"):
            meta["processed"] = stripped.replace("**Videos processed:**", "").strip()
        elif stripped.startswith("**Videos failed:**"):
            meta["failed"] = stripped.replace("**Videos failed:**", "").strip()
    return meta


def _parse_video_sections(lines: list) -> list:
    videos = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") and re.match(r"^## \d+\.", stripped):
            title = stripped[3:]
            videos.append(title)
    return videos


def _render_cover_page(pdf: FPDF, meta: dict):
    pdf.add_page()
    pdf.ln(50)

    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 15, "Daily Video Insight Report", align="C")
    pdf.ln(20)

    # Decorative line
    y = pdf.get_y()
    pdf.set_draw_color(0, 51, 102)
    pdf.set_line_width(0.8)
    pdf.line(50, y, pdf.w - 50, y)
    pdf.set_line_width(0.2)
    pdf.ln(15)

    # Date
    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 10, meta.get("date", ""), align="C")
    pdf.ln(25)

    # Stats box
    box_x = pdf.w / 2 - 40
    box_y = pdf.get_y()
    pdf.set_fill_color(240, 245, 250)
    pdf.rect(box_x, box_y, 80, 35, "F")

    pdf.set_xy(box_x, box_y + 5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(80, 8, f"Videos Processed: {meta.get('processed', '0')}", align="C")
    pdf.set_xy(box_x, box_y + 18)
    pdf.cell(80, 8, f"Videos Failed: {meta.get('failed', '0')}", align="C")

    pdf.ln(50)

    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 10, "Generated by VIS (Video Insight System)", align="C")


def _render_toc(pdf: FPDF, videos: list):
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 12, "Table of Contents")
    pdf.ln(10)

    pdf.set_draw_color(0, 51, 102)
    pdf.set_line_width(0.5)
    pdf.line(20, pdf.get_y(), pdf.w - 20, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(8)

    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(0, 0, 0)

    for i, title in enumerate(videos, 1):
        if pdf.get_y() > pdf.h - 30:
            pdf.add_page()

        clean_title = re.sub(r"^\d+\.\s*", "", title)
        entry = f"{i}. {clean_title}"
        pdf.multi_cell(0, 7, entry)
        pdf.ln(3)

    if not videos:
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(128, 128, 128)
        pdf.cell(0, 8, "No videos processed in this run.")


def _render_metadata_line(pdf: FPDF, text: str):
    match = re.match(r"\*\*(.*?)\*\*\s*(.*)", text)
    if not match:
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 6, text)
        return

    key = match.group(1)
    value = match.group(2)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(80, 80, 80)
    key_w = pdf.get_string_width(key) + 2
    pdf.cell(key_w, 6, key)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(0, 0, 0)

    link_match = re.match(r"\[(.*?)\]\((.*?)\)", value.strip())
    if link_match:
        pdf.set_text_color(0, 0, 200)
        pdf.cell(0, 6, link_match.group(1), link=link_match.group(2))
        pdf.set_text_color(0, 0, 0)
    else:
        pdf.cell(0, 6, value)

    pdf.ln(6)


def _render_table_row(pdf: FPDF, row: str):
    cells = [c.strip() for c in row.split("|")[1:-1]]

    if not cells:
        return

    # Skip separator rows
    if all(re.match(r"^-+$", c) for c in cells):
        return

    # Use proportional column widths for the failed videos table
    # Columns: #, Title, Channel, Link, Status
    available_width = pdf.w - 40
    col_count = len(cells)

    if col_count == 5:
        # Proportional: #=5%, Title=35%, Channel=20%, Link=10%, Status=30%
        col_widths = [
            available_width * 0.05,
            available_width * 0.35,
            available_width * 0.20,
            available_width * 0.10,
            available_width * 0.30,
        ]
    else:
        col_widths = [available_width / col_count] * col_count

    # Check if we need a new page
    if pdf.get_y() > pdf.h - 25:
        pdf.add_page()

    x_start = pdf.get_x()
    y_start = pdf.get_y()

    # Calculate row height based on longest cell content
    pdf.set_font("Helvetica", "", 8)
    max_lines = 1
    for i, cell_text in enumerate(cells):
        link_match = re.match(r"\[(.*?)\]\((.*?)\)", cell_text)
        if link_match:
            cell_text = link_match.group(1)
        w = col_widths[i] if i < len(col_widths) else col_widths[-1]
        text_w = pdf.get_string_width(cell_text)
        lines_needed = max(1, int(text_w / (w - 2)) + 1)
        max_lines = max(max_lines, lines_needed)

    row_height = max(7, max_lines * 5)

    pdf.set_text_color(0, 0, 0)

    for i, cell_text in enumerate(cells):
        w = col_widths[i] if i < len(col_widths) else col_widths[-1]
        pdf.set_xy(x_start + sum(col_widths[:i]), y_start)

        link_match = re.match(r"\[(.*?)\]\((.*?)\)", cell_text)
        if link_match:
            cell_text = link_match.group(1)

        # Draw border
        pdf.rect(pdf.get_x(), y_start, w, row_height)
        # Write wrapped text inside
        pdf.set_xy(x_start + sum(col_widths[:i]) + 1, y_start + 1)
        pdf.multi_cell(w - 2, 4, cell_text)

    pdf.set_y(y_start + row_height)
