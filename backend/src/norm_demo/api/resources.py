from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from compliance_workflow_demo.api.schemas import DocPage, DocSummary, DocText, RuleSummary

router = APIRouter()


@router.get("/rules", response_model=list[RuleSummary])
async def list_rules(request: Request) -> list[RuleSummary]:
    rules = request.app.state.rules
    return [
        RuleSummary(id=rule.id, name=rule.name, op=rule.root.op)
        for rule in rules.values()
    ]


@router.get("/docs", response_model=list[DocSummary])
async def list_docs(request: Request) -> list[DocSummary]:
    docs = request.app.state.docs
    return [
        DocSummary(
            id=name,
            title=_extract_title(name, doc),
            sha256=doc.id,
            pages=len({c.page for c in doc.chunks}),
        )
        for name, doc in docs.items()
    ]


@router.get("/docs/{doc_id}/text", response_model=DocText)
async def get_doc_text(doc_id: str, request: Request) -> DocText:
    """Return per-page text so the UI can render the doc and highlight
    evidence quotes returned by the LLM."""
    docs = request.app.state.docs
    doc = docs.get(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"unknown doc_id: {doc_id!r}")
    # Concatenate chunks belonging to the same page so split chunks render
    # as one continuous page block in the UI.
    by_page: dict[int, list[str]] = {}
    for chunk in doc.chunks:
        by_page.setdefault(chunk.page, []).append(chunk.text)
    pages = [DocPage(page=p, text="\n\n".join(by_page[p])) for p in sorted(by_page)]
    return DocText(
        id=doc_id,
        title=_extract_title(doc_id, doc),
        sha256=doc.id,
        pages=pages,
    )


def _extract_title(stem: str, doc) -> str:
    """First non-empty line of the first chunk — for our corpus that's the
    fund name (e.g. 'Northwind Capital Growth Fund'). Falls back to the
    filename stem if the doc looks empty."""
    if not doc.chunks:
        return stem
    for line in doc.chunks[0].text.splitlines():
        line = line.strip()
        if line:
            # Title-case the line if it's all caps (synth docs use uppercase
            # headers); leave mixed-case alone (real prospectus already cased).
            return line.title() if line.isupper() else line
    return stem
