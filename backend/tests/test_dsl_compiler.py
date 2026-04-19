from textwrap import dedent

import pytest

from compliance_workflow_demo.dsl import (
    Rule,
    compile_rule,
    compile_rules,
    load_rule,
)


def _rule(yaml_text: str) -> Rule:
    return load_rule(dedent(yaml_text))


def test_leaf_only_rule_emits_one_node():
    rule = _rule(
        """
        id: R1
        name: leaf
        op: REQUIRES_CLAUSE
        clause: past performance is disclosed
        """
    )
    graph = compile_rule(rule)

    assert len(graph.nodes) == 1
    (node,) = graph.nodes.values()
    assert node.op == "REQUIRES_CLAUSE"
    assert node.params == {"clause": "past performance is disclosed"}
    assert node.child_ids == ()
    assert node.prompt_template == "requires_clause"
    assert node.is_leaf
    assert graph.roots == {"R1": node.id}
    assert graph.topo_order == (node.id,)


def test_nested_rule_topo_order_has_leaves_before_aggregator():
    rule = _rule(
        """
        id: R1
        name: nested
        op: ALL_OF
        children:
          - op: REQUIRES_CLAUSE
            clause: a
          - op: FORBIDS_PHRASE
            phrase: b
        """
    )
    graph = compile_rule(rule)

    assert len(graph.nodes) == 3
    root_id = graph.roots["R1"]
    root = graph.nodes[root_id]
    assert root.op == "ALL_OF"
    assert root.prompt_template is None
    assert not root.is_leaf

    # root must come last; both children must precede it
    assert graph.topo_order[-1] == root_id
    leaf_ids = set(graph.topo_order[:-1])
    assert leaf_ids == set(root.child_ids)


def test_identical_subexpressions_collapse_across_rules():
    rules = [
        _rule(
            """
            id: R1
            name: one
            op: ALL_OF
            children:
              - op: REQUIRES_CLAUSE
                clause: shared
              - op: FORBIDS_PHRASE
                phrase: never
            """
        ),
        _rule(
            """
            id: R2
            name: two
            op: ANY_OF
            children:
              - op: REQUIRES_CLAUSE
                clause: shared
              - op: CITES
                target: risk disclaimer
            """
        ),
    ]
    graph = compile_rules(rules)

    shared_clauses = [
        n for n in graph.nodes.values()
        if n.op == "REQUIRES_CLAUSE" and n.params == {"clause": "shared"}
    ]
    assert len(shared_clauses) == 1

    # Both roots should reference the shared leaf id
    shared_id = shared_clauses[0].id
    assert shared_id in graph.nodes[graph.roots["R1"]].child_ids
    assert shared_id in graph.nodes[graph.roots["R2"]].child_ids


def test_aggregator_is_commutative_in_id():
    rule_a = _rule(
        """
        id: R1
        name: ab
        op: ALL_OF
        children:
          - op: REQUIRES_CLAUSE
            clause: a
          - op: REQUIRES_CLAUSE
            clause: b
        """
    )
    rule_b = _rule(
        """
        id: R2
        name: ba
        op: ALL_OF
        children:
          - op: REQUIRES_CLAUSE
            clause: b
          - op: REQUIRES_CLAUSE
            clause: a
        """
    )
    graph = compile_rules([rule_a, rule_b])

    assert graph.roots["R1"] == graph.roots["R2"]


def test_compilation_is_deterministic_across_runs():
    rule = _rule(
        """
        id: R1
        name: nested
        op: ANY_OF
        children:
          - op: ALL_OF
            children:
              - op: REQUIRES_CLAUSE
                clause: x
              - op: FORBIDS_PHRASE
                phrase: y
          - op: CITES
            target: z
        """
    )
    g1 = compile_rule(rule)
    g2 = compile_rule(rule)

    assert g1.roots == g2.roots
    assert set(g1.nodes.keys()) == set(g2.nodes.keys())


def test_node_id_is_64_hex_chars():
    rule = _rule(
        """
        id: R1
        name: leaf
        op: CITES
        target: rule 2210
        """
    )
    graph = compile_rule(rule)
    (node,) = graph.nodes.values()
    assert len(node.id) == 64
    assert all(c in "0123456789abcdef" for c in node.id)


def test_duplicate_rule_id_rejected():
    rule = _rule(
        """
        id: R1
        name: leaf
        op: CITES
        target: x
        """
    )
    with pytest.raises(ValueError, match="duplicate rule id"):
        compile_rules([rule, rule])


def test_leaf_with_different_params_does_not_collapse():
    rules = [
        _rule(
            """
            id: R1
            name: a
            op: REQUIRES_CLAUSE
            clause: alpha
            """
        ),
        _rule(
            """
            id: R2
            name: b
            op: REQUIRES_CLAUSE
            clause: beta
            """
        ),
    ]
    graph = compile_rules(rules)
    assert len(graph.nodes) == 2
    assert graph.roots["R1"] != graph.roots["R2"]


def test_leaves_helper_returns_only_leaf_nodes():
    rule = _rule(
        """
        id: R1
        name: nested
        op: ALL_OF
        children:
          - op: REQUIRES_CLAUSE
            clause: a
          - op: ANY_OF
            children:
              - op: FORBIDS_PHRASE
                phrase: b
              - op: CITES
                target: c
        """
    )
    graph = compile_rule(rule)
    leaves = graph.leaves()
    assert len(leaves) == 3
    assert all(n.is_leaf for n in leaves)
    assert {n.op for n in leaves} == {"REQUIRES_CLAUSE", "FORBIDS_PHRASE", "CITES"}
