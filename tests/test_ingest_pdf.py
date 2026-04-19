from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from compliance_workflow_demo.ingest import parse_pdf_bytes, parse_pdf_path


def _make_pdf(pages: list[str]) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER
    for idx, page in enumerate(pages):
        y = height - 72
        for line in page.splitlines():
            c.drawString(72, y, line)
            y -= 14
        if idx < len(pages) - 1:
            c.showPage()
    c.save()
    return buf.getvalue()


def test_parse_pdf_bytes_round_trip():
    data = _make_pdf(["First page text.", "Second page text."])
    doc = parse_pdf_bytes(data)
    assert len(doc.chunks) == 2
    assert {c.page for c in doc.chunks} == {1, 2}
    assert "First page" in doc.chunks[0].text
    assert "Second page" in doc.chunks[1].text


def test_parse_pdf_id_is_sha256_of_bytes():
    """Same bytes → same id. Different bytes → different id. Idempotent ingest
    is the whole point of content-addressing the doc."""
    import hashlib

    data = _make_pdf(["hello"])
    doc = parse_pdf_bytes(data)
    assert doc.id == hashlib.sha256(data).hexdigest()
    assert len(doc.id) == 64

    other = parse_pdf_bytes(_make_pdf(["different"]))
    assert other.id != doc.id


def test_parse_synthetic_corpus_doc_pages_match_source(tmp_path: Path):
    """Round-trip a generated corpus PDF to confirm the chunker recovers the
    same page count as the source's {{PAGE_BREAK}} markers."""
    corpus = Path(__file__).resolve().parent.parent / "corpus"
    pdf = corpus / "synth_fund_01.pdf"
    src = corpus / "sources" / "synth_fund_01.txt"
    if not pdf.exists() or not src.exists():
        pytest.skip("corpus not generated; run scripts/generate_corpus.py")

    expected_pages = src.read_text().count("{{PAGE_BREAK}}") + 1
    doc = parse_pdf_path(pdf)
    actual_pages = len({c.page for c in doc.chunks})
    assert actual_pages == expected_pages
