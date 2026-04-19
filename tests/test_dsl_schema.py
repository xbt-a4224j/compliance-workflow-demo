from textwrap import dedent

import pytest
from pydantic import ValidationError

from compliance_workflow_demo.dsl import (
    AllOfNode,
    AnyOfNode,
    CitesNode,
    ForbidsPhraseNode,
    RequiresClauseNode,
    Rule,
    load_rule,
)


def test_parse_flat_rule():
    rule = load_rule(
        dedent(
            """
            id: FINRA-2210-PERF
            name: Past performance must include disclaimer
            op: ALL_OF
            children:
              - op: REQUIRES_CLAUSE
                clause: "past performance is disclosed"
              - op: REQUIRES_CLAUSE
                clause: "no guarantee of future results"
            """
        )
    )
    assert rule.id == "FINRA-2210-PERF"
    assert isinstance(rule.root, AllOfNode)
    assert len(rule.root.children) == 2
    first = rule.root.children[0]
    assert isinstance(first, RequiresClauseNode)
    assert first.clause == "past performance is disclosed"


def test_parse_nested_rule_with_all_ops():
    rule = load_rule(
        dedent(
            """
            id: R1
            name: Nested
            op: ALL_OF
            children:
              - op: ANY_OF
                children:
                  - op: REQUIRES_CLAUSE
                    clause: a
                  - op: FORBIDS_PHRASE
                    phrase: b
              - op: CITES
                target: risk disclaimer
            """
        )
    )
    assert isinstance(rule.root, AllOfNode)
    inner_any = rule.root.children[0]
    assert isinstance(inner_any, AnyOfNode)
    assert isinstance(inner_any.children[0], RequiresClauseNode)
    assert isinstance(inner_any.children[1], ForbidsPhraseNode)
    assert isinstance(rule.root.children[1], CitesNode)
    assert rule.root.children[1].target == "risk disclaimer"


def test_parse_explicit_root_form():
    rule = load_rule(
        dedent(
            """
            id: R1
            name: x
            root:
              op: REQUIRES_CLAUSE
              clause: ok
            """
        )
    )
    assert isinstance(rule.root, RequiresClauseNode)
    assert rule.root.clause == "ok"


def test_reject_unknown_op():
    with pytest.raises(ValidationError):
        load_rule(
            dedent(
                """
                id: R1
                name: x
                op: WUT
                phrase: hi
                """
            )
        )


def test_reject_missing_required_field():
    with pytest.raises(ValidationError):
        load_rule(
            dedent(
                """
                id: R1
                name: x
                op: REQUIRES_CLAUSE
                """
            )
        )


def test_reject_extra_field_on_node():
    with pytest.raises(ValidationError):
        load_rule(
            dedent(
                """
                id: R1
                name: x
                op: REQUIRES_CLAUSE
                clause: hello
                bogus: true
                """
            )
        )


def test_reject_non_mapping_yaml():
    with pytest.raises(ValueError):
        load_rule("- not a mapping")


def test_rule_roundtrip_via_model_dump_model_validate():
    original = Rule.model_validate(
        {
            "id": "R1",
            "name": "x",
            "root": {"op": "FORBIDS_PHRASE", "phrase": "guaranteed returns"},
        }
    )
    redumped = Rule.model_validate(original.model_dump())
    assert redumped == original
