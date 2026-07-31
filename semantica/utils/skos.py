"""Validation helpers for SKOS graph relationships."""

from collections import defaultdict
from typing import Iterable, Mapping


_HIERARCHY_EDGE_TYPES = frozenset({"skos:broader", "skos:narrower"})


def is_skos_hierarchy_edge(edge: Mapping[str, object]) -> bool:
    """Return whether an edge uses a SKOS hierarchy predicate."""
    if not isinstance(edge, Mapping):
        return False
    return any(
        edge.get(key) in _HIERARCHY_EDGE_TYPES
        for key in ("type", "edge_type", "relationship", "predicate", "relation")
    )


def validate_skos_hierarchy(edges: Iterable[Mapping[str, object]]) -> None:
    """Raise ``ValueError`` when SKOS hierarchy edges contain a cycle.

    ``skos:broader`` points from a concept to its parent while
    ``skos:narrower`` expresses the same relationship in the opposite
    direction. Both forms are normalized to child-to-parent adjacency before
    cycle detection.
    """

    parents: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if not isinstance(edge, Mapping) or not is_skos_hierarchy_edge(edge):
            continue
        edge_type = next(
            (
                edge.get(key)
                for key in ("type", "edge_type", "relationship", "predicate", "relation")
                if edge.get(key) in _HIERARCHY_EDGE_TYPES
            ),
            None,
        )
        if edge_type not in _HIERARCHY_EDGE_TYPES:
            continue

        raw_source = edge.get("source", edge.get("source_id"))
        raw_target = edge.get("target", edge.get("target_id"))
        if raw_source is None or raw_target is None:
            continue
        source = str(raw_source).strip()
        target = str(raw_target).strip()
        if not source or not target:
            continue

        child, parent = ((source, target) if edge_type == "skos:broader" else (target, source))
        parents[child].add(parent)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(concept: str) -> None:
        if concept in visiting:
            raise ValueError(f"SKOS hierarchy contains a cycle involving '{concept}'.")
        if concept in visited:
            return

        visiting.add(concept)
        for parent in parents.get(concept, ()):
            visit(parent)
        visiting.remove(concept)
        visited.add(concept)

    for concept in parents:
        visit(concept)
