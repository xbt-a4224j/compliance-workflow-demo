from __future__ import annotations

from compliance_workflow_demo.dsl.graph import GraphNode

_JSON_INSTRUCTIONS = (
    "Reply with a single JSON object and nothing else (no markdown, no commentary).\n"
    'Schema: {"passed": bool, "evidence": str | null, "confidence": number in [0,1]}\n'
    'When passed=true, "evidence" must be a verbatim quote from the document. '
    'When passed=false, "evidence" may be null or a quote of the offending text.'
)


def _document_block(doc_text: str) -> str:
    return f"DOCUMENT:\n{doc_text}\n\nEND DOCUMENT.\n\n{_JSON_INSTRUCTIONS}"


def requires_clause(node: GraphNode, doc_text: str) -> tuple[str, str]:
    system = (
        "You are a strict compliance auditor. Decide whether a document "
        "communicates a required concept. Paraphrases satisfy the requirement; "
        "the wording need not be exact. Be conservative: if the concept is not "
        'clearly conveyed, answer passed=false.'
    )
    user = (
        f'Required concept: "{node.params["clause"]}".\n\n'
        f"Question: is this concept communicated anywhere in the document below? "
        f"Set passed=true if yes (paraphrases OK), false otherwise.\n\n"
        f"{_document_block(doc_text)}"
    )
    return system, user


def forbids_phrase(node: GraphNode, doc_text: str) -> tuple[str, str]:
    system = (
        "You are a strict compliance auditor. Decide whether a forbidden ASSERTION "
        "appears in a document. Catch near-match marketing-ese — but only when the "
        "document is positively claiming the forbidden thing.\n\n"
        "CRITICAL: distinguish ASSERTIONS from DISCLAIMERS, NEGATIONS, or HEDGED "
        "PROJECTIONS.\n"
        '  - "past performance is not a guarantee of future results" → DISCLAIMER, '
        'does NOT count as a guarantee assertion.\n'
        '  - "we expect 18-22% returns next year" → HEDGED projection ("expect" '
        'carries uncertainty), does NOT count as a guarantee. (It may violate a '
        "DIFFERENT rule — that's fine — but it is not a guarantee assertion.)\n"
        '  - "this fund offers guaranteed returns of 8%" → POSITIVE ASSERTION, '
        "does count.\n"
        "  - \"risk-free investment\" / \"capital is guaranteed\" → POSITIVE ASSERTION.\n\n"
        "Near-match means semantically equivalent (an absolute, unhedged promise of "
        "the forbidden thing), not just topically related. Words like \"expect\", "
        "\"anticipate\", \"target\", \"project\" introduce uncertainty and are NOT "
        "near-matches for \"guaranteed\".\n\n"
        "passed=true means no forbidden assertion is present (rule satisfied). "
        "passed=false means the forbidden assertion (or its semantically equivalent "
        "marketing-ese) is positively asserted somewhere in the document."
    )
    user = (
        f'Forbidden assertion or its semantically equivalent near-matches: '
        f'"{node.params["phrase"]}".\n\n'
        f"Question: does the document POSITIVELY ASSERT this phrase, or a "
        f"semantically equivalent (absolute, unhedged) version of it? Disclaimers, "
        f"negations, and hedged projections (with words like 'expect', 'anticipate', "
        f"'target') do NOT count as the phrase being present.\n\n"
        f"Set passed=false ONLY if you find an unhedged positive assertion. "
        f"Set passed=true otherwise.\n\n"
        f"{_document_block(doc_text)}"
    )
    return system, user


def cites(node: GraphNode, doc_text: str) -> tuple[str, str]:
    system = (
        "You are a strict compliance auditor. Decide whether a document contains "
        "a structured external reference (named document, regulation, standard, "
        "authority, time-window). Vague allusions do not count; the citation must "
        "be specific enough that a reader could look it up."
    )
    user = (
        f'Required citation target: "{node.params["target"]}".\n\n'
        f"Question: does the document below contain a structured external reference "
        f"to this target (specific enough to look up)? Set passed=true only if a "
        f"concrete reference is present.\n\n"
        f"{_document_block(doc_text)}"
    )
    return system, user


_TEMPLATES = {
    "requires_clause": requires_clause,
    "forbids_phrase": forbids_phrase,
    "cites": cites,
}


def build_prompt(node: GraphNode, doc_text: str) -> tuple[str, str]:
    if node.prompt_template is None:
        raise ValueError(f"node {node.id[:8]} ({node.op}) is not a leaf")
    template = _TEMPLATES[node.prompt_template]
    return template(node, doc_text)
