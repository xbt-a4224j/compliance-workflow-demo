from __future__ import annotations

from dataclasses import dataclass

import tiktoken

from compliance_workflow_demo.ingest.types import DocChunk

# cl100k_base is OpenAI's GPT-4 encoding. Anthropic's tokenizer is not public,
# but cl100k counts are within ~10% of Claude's for English text — close
# enough for chunk-size budgeting. The number that matters here is the chunk
# *boundary*, not exact token billing.
_ENCODING_NAME = "cl100k_base"

_DEFAULT_MAX_TOKENS = 800
_DEFAULT_OVERLAP_TOKENS = 150


@dataclass(frozen=True)
class ChunkerConfig:
    max_tokens: int = _DEFAULT_MAX_TOKENS
    overlap_tokens: int = _DEFAULT_OVERLAP_TOKENS


def chunk_pages(
    pages: list[str],
    *,
    config: ChunkerConfig | None = None,
) -> tuple[DocChunk, ...]:
    """Turn a list of per-page text strings into page-stamped DocChunks.

    Chunks never cross page boundaries — a chunk's `page` is unambiguous,
    which is what the executor's _resolve_page lookup needs to recover
    provenance from the LLM's evidence quote.

    Within a page, if the page exceeds max_tokens, it splits into multiple
    chunks with overlap so a quote landing on a chunk boundary still appears
    in at least one chunk's text intact.
    """
    config = config or ChunkerConfig()
    encoding = tiktoken.get_encoding(_ENCODING_NAME)

    chunks: list[DocChunk] = []
    for page_index, page_text in enumerate(pages, start=1):
        text = page_text.strip()
        if not text:
            continue
        chunks.extend(_chunk_one_page(text, page_index, encoding, config))
    return tuple(chunks)


def _chunk_one_page(
    text: str,
    page: int,
    encoding: tiktoken.Encoding,
    config: ChunkerConfig,
) -> list[DocChunk]:
    tokens = encoding.encode(text)
    if len(tokens) <= config.max_tokens:
        return [DocChunk(text=text, page=page)]

    chunks: list[DocChunk] = []
    step = config.max_tokens - config.overlap_tokens
    if step <= 0:
        raise ValueError("overlap_tokens must be less than max_tokens")

    start = 0
    while start < len(tokens):
        end = min(start + config.max_tokens, len(tokens))
        chunk_text = encoding.decode(tokens[start:end])
        chunks.append(DocChunk(text=chunk_text, page=page))
        if end == len(tokens):
            break
        start += step
    return chunks
