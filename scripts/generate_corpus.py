"""Render every corpus/sources/*.txt into a real text-PDF in corpus/.

Source files use {{PAGE_BREAK}} markers; each section between markers
becomes one PDF page so the chunker recovers true page numbers from
pypdf's extraction.

Run from the project root:
    uv run python scripts/generate_corpus.py
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

PAGE_BREAK = "{{PAGE_BREAK}}"

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "corpus" / "sources"
OUTPUT = ROOT / "corpus"


def render_pdf(source_path: Path, dest_path: Path) -> None:
    pages = source_path.read_text().split(PAGE_BREAK)

    c = canvas.Canvas(str(dest_path), pagesize=LETTER)
    width, height = LETTER
    left_margin = 72
    top_margin = 72
    line_height = 14
    font_name = "Helvetica"
    font_size = 10
    c.setFont(font_name, font_size)

    for page_index, page_text in enumerate(pages):
        y = height - top_margin
        for line in page_text.strip().splitlines():
            if y < 72:  # bottom margin
                # If a single source page would overflow one PDF page, just
                # truncate. Synthetic docs are short by design — we don't
                # want soft page breaks confusing the page-stamping contract.
                break
            c.drawString(left_margin, y, line)
            y -= line_height
        if page_index < len(pages) - 1:
            c.showPage()
            c.setFont(font_name, font_size)
    c.save()


def main() -> None:
    sources = sorted(SOURCES.glob("*.txt"))
    if not sources:
        raise SystemExit(f"no source files in {SOURCES}")
    for src in sources:
        dest = OUTPUT / f"{src.stem}.pdf"
        render_pdf(src, dest)
        print(f"  {src.name}  ->  {dest.relative_to(ROOT)}")
    print(f"\nrendered {len(sources)} files")


if __name__ == "__main__":
    main()
