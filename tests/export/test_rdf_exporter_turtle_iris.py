"""Regression tests for valid Turtle IRI generation (issue #1099)."""

from rdflib import RDF, Graph, URIRef

from semantica.export import RDFExporter
from semantica.kg.graph_builder import GraphBuilder


def test_turtle_normalizes_graph_builder_default_identifiers():
    """Default GraphBuilder labels with spaces become stable absolute IRIs."""
    source = {
        "entities": [
            {"id": "Acme Corp", "name": "Acme Corp", "type": "ORG"},
            {"id": "Jane Doe", "name": "Jane Doe", "type": "PERSON"},
        ],
        "relationships": [
            {"source": "Jane Doe", "target": "Acme Corp", "type": "works_for"},
        ],
    }
    graph_data = GraphBuilder(resolve_conflicts=False).build(sources=[source])

    turtle = RDFExporter().export_to_rdf(graph_data, format="turtle")
    parsed = Graph().parse(data=turtle, format="turtle")

    acme = URIRef("https://semantica.dev/ns#Acme%20Corp")
    jane = URIRef("https://semantica.dev/ns#Jane%20Doe")
    assert (acme, RDF.type, URIRef("https://semantica.dev/ns#ORG")) in parsed
    jane_type = URIRef("https://semantica.dev/ns#PERSON")
    assert (jane, RDF.type, jane_type) in parsed
    assert (
        jane,
        URIRef("https://semantica.dev/ns#works_for"),
        acme,
    ) in parsed


def test_turtle_preserves_absolute_iris():
    """Already-valid absolute resource IRIs remain unchanged."""
    turtle = RDFExporter().export_to_rdf(
        {
            "entities": [
                {
                    "id": "https://example.org/entities/jane",
                    "text": "Jane",
                    "type": "urn:example:Person",
                }
            ],
            "relationships": [],
        },
        format="turtle",
    )
    parsed = Graph().parse(data=turtle, format="turtle")

    assert (
        URIRef("https://example.org/entities/jane"),
        RDF.type,
        URIRef("urn:example:Person"),
    ) in parsed


def test_turtle_expands_context_prefixes_and_normalizes_malformed_iris():
    """Prefixes expand and malformed URI-like values are minted."""
    turtle = RDFExporter().export_to_rdf(
        {
            "@context": {"ex": "https://example.org/"},
            "entities": [{"id": "http://[invalid", "type": "ex:Person"}],
            "relationships": [],
        },
        format="turtle",
    )
    parsed = Graph().parse(data=turtle, format="turtle")

    assert (
        URIRef("https://semantica.dev/ns#http%3A%2F%2F%5Binvalid"),
        RDF.type,
        URIRef("https://example.org/Person"),
    ) in parsed
