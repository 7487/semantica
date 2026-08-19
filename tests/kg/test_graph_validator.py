from semantica.kg.graph_builder import GraphBuilder
from semantica.kg.graph_validator import GraphValidator


def test_entity_id_aliases_are_validated_across_graph_structure():
    """Entity aliases should work for schema and structural validation."""
    graph = GraphBuilder(
        merge_entities=True,
        entity_resolution_strategy="exact",
        resolve_conflicts=False,
    ).build(
        {
            "entities": [
                {"entity_id": "alice:1", "name": "Alice", "type": "Person"},
                {"entity_id": "alice:2", "name": " Alice ", "type": "Person"},
                {"entity_id": "org:1", "name": "Acme", "type": "Organization"},
            ],
            "relationships": [
                {
                    "source_id": "alice:2",
                    "target_id": "org:1",
                    "type": "WORKS_FOR",
                }
            ],
        }
    )

    result = GraphValidator().validate(graph)

    assert result.is_valid
    assert not any(
        issue.code in {"MISSING_FIELD", "DANGLING_EDGE", "ORPHAN_NODES"}
        for issue in result.issues
    )
