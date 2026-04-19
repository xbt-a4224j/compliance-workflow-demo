from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from compliance_workflow_demo.ingest.chunker import ChunkerConfig, chunk_pages
from compliance_workflow_demo.ingest.types import Document


def parse_pdf_bytes(data: bytes, *, config: ChunkerConfig | None = None) -> Document:
    """Read a PDF blob, extract text per page, hash the bytes for the doc id,
    and run the chunker. The doc id being content-addressed makes ingest
    idempotent — uploading the same file twice produces the same Document."""
    doc_id = hashlib.sha256(data).hexdigest()
    reader = PdfReader(BytesIO(data))
    pages = [(page.extract_text() or "") for page in reader.pages]
    chunks = chunk_pages(pages, config=config)
    return Document(id=doc_id, chunks=chunks)


def parse_pdf_path(path: str | Path, *, config: ChunkerConfig | None = None) -> Document:
    return parse_pdf_bytes(Path(path).read_bytes(), config=config)
