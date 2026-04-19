from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from compliance_workflow_demo.dsl.graph import (
    AGGREGATOR_OPS,
    LEAF_OPS,
    PROMPT_TEMPLATES,
    ExecutionGraph,
    GraphNode,
)
from compliance_workflow_demo.dsl.schema import (
    AllOfNode,
    AnyOfNode,
    CitesNode,
    ForbidsPhraseNode,
    Node,
    RequiresClauseNode,
    Rule,
)


def _canonical_json(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _hash_node(op: str, params: dict[str, str], child_ids: Iterable[str]) -> str:
    payload = {
        "op": op,
        "params": dict(sorted(params.items())),
        "children": sorted(child_ids),
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _leaf_params(node: Node) -> dict[str, str]:
    if isinstance(node, RequiresClauseNode):
        return {"clause": node.clause}
    if isinstance(node, ForbidsPhraseNode):
        return {"phrase": node.phrase}
    if isinstance(node, CitesNode):
        return {"target": node.target}
    raise TypeError(f"not a leaf node: {type(node).__name__}")


class _Builder:
    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.topo_order: list[str] = []

    def visit(self, node: Node) -> str:
        if isinstance(node, AllOfNode | AnyOfNode):
            child_ids = [self.visit(child) for child in node.children]
            sorted_children = tuple(sorted(child_ids))
            node_id = _hash_node(node.op, {}, sorted_children)
            self._register(
                GraphNode(
                    id=node_id,
                    op=node.op,
                    params={},
                    child_ids=sorted_children,
                    prompt_template=None,
                )
            )
            return node_id

        if node.op in LEAF_OPS:
            params = _leaf_params(node)
            node_id = _hash_node(node.op, params, ())
            self._register(
                GraphNode(
                    id=node_id,
                    op=node.op,
                    params=params,
                    child_ids=(),
                    prompt_template=PROMPT_TEMPLATES[node.op],
                )
            )
            return node_id

        raise ValueError(f"unknown op: {node.op!r}")

    def _register(self, gnode: GraphNode) -> None:
        if gnode.id in self.nodes:
            return
        self.nodes[gnode.id] = gnode
        self.topo_order.append(gnode.id)


def compile_rule(rule: Rule) -> ExecutionGraph:
    return compile_rules([rule])


def compile_rules(rules: Iterable[Rule]) -> ExecutionGraph:
    builder = _Builder()
    roots: dict[str, str] = {}
    for rule in rules:
        if rule.id in roots:
            raise ValueError(f"duplicate rule id: {rule.id!r}")
        roots[rule.id] = builder.visit(rule.root)

    # Sanity: aggregators must come after their children in topo_order. The
    # post-order DFS guarantees this, but a cheap assertion catches future
    # refactors that break the invariant.
    seen: set[str] = set()
    for nid in builder.topo_order:
        gnode = builder.nodes[nid]
        if gnode.op in AGGREGATOR_OPS and not all(c in seen for c in gnode.child_ids):
            raise AssertionError(f"topo order violated at node {nid}")
        seen.add(nid)

    return ExecutionGraph(
        nodes=builder.nodes,
        topo_order=tuple(builder.topo_order),
        roots=roots,
    )
