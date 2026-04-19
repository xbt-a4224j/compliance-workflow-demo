from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

NodeOp = Literal["ALL_OF", "ANY_OF", "REQUIRES_CLAUSE", "FORBIDS_PHRASE", "CITES"]
LeafOp = Literal["REQUIRES_CLAUSE", "FORBIDS_PHRASE", "CITES"]
AggregatorOp = Literal["ALL_OF", "ANY_OF"]

LEAF_OPS: frozenset[str] = frozenset({"REQUIRES_CLAUSE", "FORBIDS_PHRASE", "CITES"})
AGGREGATOR_OPS: frozenset[str] = frozenset({"ALL_OF", "ANY_OF"})

PROMPT_TEMPLATES: dict[str, str] = {
    "REQUIRES_CLAUSE": "requires_clause",
    "FORBIDS_PHRASE": "forbids_phrase",
    "CITES": "cites",
}


class GraphNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    op: NodeOp
    params: dict[str, str]
    child_ids: tuple[str, ...]
    prompt_template: str | None

    @property
    def is_leaf(self) -> bool:
        return self.op in LEAF_OPS


class ExecutionGraph(BaseModel):
    model_config = ConfigDict(frozen=True)

    nodes: dict[str, GraphNode]
    topo_order: tuple[str, ...]
    roots: dict[str, str]

    def leaves(self) -> tuple[GraphNode, ...]:
        return tuple(self.nodes[nid] for nid in self.topo_order if self.nodes[nid].is_leaf)
