from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DocChunk(BaseModel):
    """A page-stamped slice of document text.

    The chunker (#15) is the source of truth for `page`. The executor never
    asks the LLM for page numbers — it back-references the LLM's evidence
    quote against the chunks that were sent in the prompt.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    page: int


class Document(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str  # sha256(pdf_bytes), populated by the ingest pipeline (#15)
    chunks: tuple[DocChunk, ...]

    def joined_text(self) -> str:
        """Render the document with [page N] markers for the LLM prompt."""
        return "\n\n".join(f"[page {c.page}]\n{c.text}" for c in self.chunks)
