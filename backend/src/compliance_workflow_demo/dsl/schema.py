from __future__ import annotations

from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _DslModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequiresClauseNode(_DslModel):
    op: Literal["REQUIRES_CLAUSE"]
    clause: str


class ForbidsPhraseNode(_DslModel):
    op: Literal["FORBIDS_PHRASE"]
    phrase: str


class CitesNode(_DslModel):
    op: Literal["CITES"]
    target: str


class AllOfNode(_DslModel):
    op: Literal["ALL_OF"]
    children: list[Node]


class AnyOfNode(_DslModel):
    op: Literal["ANY_OF"]
    children: list[Node]


Node = Annotated[
    AllOfNode | AnyOfNode | RequiresClauseNode | ForbidsPhraseNode | CitesNode,
    Field(discriminator="op"),
]


AllOfNode.model_rebuild()
AnyOfNode.model_rebuild()


class Rule(_DslModel):
    id: str
    name: str
    root: Node

    @model_validator(mode="before")
    @classmethod
    def _accept_flat_form(cls, data: Any) -> Any:
        # Accept the flat YAML form where op/children/phrase live beside id/name,
        # in addition to the explicit {id, name, root: {...}} form.
        if isinstance(data, dict) and "root" not in data and "op" in data:
            meta_keys = {"id", "name"}
            meta = {k: v for k, v in data.items() if k in meta_keys}
            root_payload = {k: v for k, v in data.items() if k not in meta_keys}
            return {**meta, "root": root_payload}
        return data


def load_rule(yaml_text: str) -> Rule:
    data = yaml.safe_load(yaml_text)
    if not isinstance(data, dict):
        raise ValueError("rule YAML must decode to a mapping at the top level")
    return Rule.model_validate(data)
