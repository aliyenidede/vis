import logging
import re

from fpdf import FPDF

logger = logging.getLogger(__name__)


class ReportPDF(FPDF):
    def header(self):
        pass

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


def markdown_to_pdf(md_path: str, pdf_path: str) -> str:
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    pdf = ReportPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()

    for line in content.split("\n"):
        stripped = line.strip()

        if not stripped:
            pdf.ln(3)
            continue

        # Horizontal rule
        if stripped == "---":
            y = pdf.get_y()
            pdf.set_draw_color(200, 200, 200)
            pdf.line(15, y, pdf.w - 15, y)
            pdf.ln(5)
            continue

        # H1
        if stripped.startswith("# ") and not stripped.startswith("## "):
            text = stripped[2:]
            pdf.set_font("Helvetica", "B", 18)
            pdf.set_text_color(0, 51, 102)
            pdf.multi_cell(0, 9, text)
            pdf.ln(3)
            continue

        # H2
        if stripped.startswith("## "):
            text = stripped[3:]
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(0, 8, text)
            pdf.ln(2)
            continue

        # H3
        if stripped.startswith("### "):
            text = stripped[4:]
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(0, 7, text)
            pdf.ln(2)
            continue

        # Table row
        if stripped.startswith("|"):
            _render_table_row(pdf, stripped)
            continue

        # Bullet point
        if stripped.startswith("- "):
            text = stripped[2:]
            pdf.set_font("Helvetica", "", 11)
            pdf.set_text_color(0, 0, 0)
            x = pdf.get_x()
            pdf.set_x(x + 10)
            pdf.cell(5, 6, "-")
            pdf.set_x(x + 15)
            _render_inline_formatted(pdf, text, w=pdf.w - 15 - x - 15)
            pdf.ln(2)
            continue

        # Regular paragraph (may contain bold/links)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(0, 0, 0)
        _render_inline_formatted(pdf, stripped, w=pdf.w - 30)
        pdf.ln(2)

    pdf.output(pdf_path)
    logger.info("PDF generated: %s", pdf_path)
    return pdf_path


def _render_inline_formatted(pdf: FPDF, text: str, w: float = 0):
    if w <= 0:
        w = pdf.w - pdf.l_margin - pdf.r_margin

    # Split text by bold markers and links
    parts = re.split(r"(\*\*.*?\*\*|\[.*?\]\(.*?\))", text)

    for part in parts:
        if not part:
            continue

        # Bold
        if part.startswith("**") and part.endswith("**"):
            pdf.set_font("Helvetica", "B", 11)
            pdf.write(6, part[2:-2])
            pdf.set_font("Helvetica", "", 11)
            continue

        # Link
        link_match = re.match(r"\[(.*?)\]\((.*?)\)", part)
        if link_match:
            link_text = link_match.group(1)
            link_url = link_match.group(2)
            pdf.set_text_color(0, 0, 255)
            pdf.set_font("Helvetica", "U", 11)
            pdf.write(6, link_text, link_url)
            pdf.set_font("Helvetica", "", 11)
            pdf.set_text_color(0, 0, 0)
            continue

        # Plain text
        pdf.write(6, part)


def _render_table_row(pdf: FPDF, row: str):
    cells = [c.strip() for c in row.split("|")[1:-1]]

    if not cells:
        return

    # Skip separator rows
    if all(re.match(r"^-+$", c) for c in cells):
        return

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(0, 0, 0)

    col_count = len(cells)
    available_width = pdf.w - 30
    col_width = available_width / col_count if col_count else available_width

    x_start = pdf.get_x()
    y_start = pdf.get_y()

    for i, cell in enumerate(cells):
        pdf.set_xy(x_start + i * col_width, y_start)
        # Handle links in table cells
        link_match = re.match(r"\[(.*?)\]\((.*?)\)", cell)
        if link_match:
            cell = link_match.group(1)
        pdf.cell(col_width, 6, cell[:30], border=1)

    pdf.ln(6)
