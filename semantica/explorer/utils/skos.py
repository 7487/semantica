"""Validation helpers for SKOS graph relationships."""

from collections import defaultdict
from typing import Iterable, Mapping


_HIERARCHY_EDGE_TYPES = frozenset({"skos:broader", "skos:narrower"})


def validate_skos_hierarchy(
    edges: Iterable[Mapping[str, object]],
) -> None:
    """Raise ``ValueError`` when SKOS hierarchy edges contain a cycle.

    ``skos:broader`` points from a concept to its parent while
    ``skos:narrower`` expresses the same relationship in the opposite
    direction.  Both forms are normalized to a child-to-parent adjacency
    map before cycle detection.
    """

    parents: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        edge_type = edge.get("type")
        if edge_type not in _HIERARCHY_EDGE_TYPES:
            continue

        source = str(edge.get("source", edge.get("source_id", "")))
        target = str(edge.get("target", edge.get("target_id", "")))
        if not source or not target:
            continue

        child, parent = (
            (source, target)
            if edge_type == "skos:broader"
            else (target, source)
        )
        parents[child].add(parent)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(concept: str) -> None:
        if concept in visiting:
            raise ValueError(
                f"SKOS hierarchy contains a cycle involving '{concept}'."
            )
        if concept in visited:
            return

        visiting.add(concept)
        for parent in parents.get(concept, ()):
            visit(parent)
        visiting.remove(concept)
        visited.add(concept)

    for concept in parents:
        visit(concept)
