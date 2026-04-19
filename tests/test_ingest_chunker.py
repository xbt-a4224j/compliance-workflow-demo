from __future__ import annotations

from compliance_workflow_demo.ingest import ChunkerConfig, chunk_pages


def test_one_chunk_per_short_page():
    pages = ["short page one", "another short page", "third page"]
    chunks = chunk_pages(pages)
    assert len(chunks) == 3
    assert [c.page for c in chunks] == [1, 2, 3]
    assert chunks[0].text == "short page one"


def test_empty_pages_skipped():
    pages = ["page 1 text", "", "   ", "page 4 text"]
    chunks = chunk_pages(pages)
    assert [c.page for c in chunks] == [1, 4]


def test_long_page_splits_into_multiple_chunks_with_overlap():
    """A page exceeding max_tokens splits into chunks; each chunk inherits
    the page's number so the executor can recover provenance unambiguously."""
    long_text = ("compliance lorem ipsum text " * 200).strip()
    config = ChunkerConfig(max_tokens=50, overlap_tokens=10)
    chunks = chunk_pages([long_text], config=config)

    assert len(chunks) > 1
    assert all(c.page == 1 for c in chunks)  # all chunks stamped with the same page


def test_chunks_never_cross_page_boundaries():
    """Two pages, both long enough to split, never produce a chunk
    containing text from both pages."""
    page_a = "alpha-token " * 200
    page_b = "beta-token " * 200
    config = ChunkerConfig(max_tokens=50, overlap_tokens=10)
    chunks = chunk_pages([page_a, page_b], config=config)

    for c in chunks:
        if c.page == 1:
            assert "beta-token" not in c.text
        else:
            assert "alpha-token" not in c.text


def test_overlap_must_be_less_than_max():
    import pytest
    pages = ["x " * 1000]
    with pytest.raises(ValueError, match="overlap"):
        chunk_pages(pages, config=ChunkerConfig(max_tokens=50, overlap_tokens=50))
