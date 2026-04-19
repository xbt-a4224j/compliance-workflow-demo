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
        "You are a strict compliance auditor. Decide whether a forbidden phrase "
        "appears in a document. Catch near-match marketing-ese, not just exact "
        "string matches. passed=true means the phrase is ABSENT (rule satisfied); "
        "passed=false means the phrase or a near-equivalent IS present."
    )
    user = (
        f'Forbidden phrase or its near-match equivalents: "{node.params["phrase"]}".\n\n'
        f"Question: is this phrase, or a near-match marketing-ese version of it, "
        f"present anywhere in the document below? Set passed=false if you find it "
        f"(rule violated), true if it is absent (rule satisfied).\n\n"
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
