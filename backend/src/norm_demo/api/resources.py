from __future__ import annotations

from fastapi import APIRouter, Request

from compliance_workflow_demo.api.schemas import DocSummary, RuleSummary

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
        DocSummary(id=name, sha256=doc.id, pages=len({c.page for c in doc.chunks}))
        for name, doc in docs.items()
    ]
