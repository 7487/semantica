"""Metadata must survive serialization (issue #1154).

``convert_kg_to_rdf`` copies ``metadata`` into the RDF-ready dictionary at
rdf_exporter.py:302, and no serializer has ever read it back out. Turtle,
N-Triples, RDF/XML and RDFExporter's JSON-LD all write the entity's id, type,
text and confidence, and none of them writes a single metadata statement, so an
entity keeps its confidence score and loses what produced it: the source
document, the page, the extractor, the reviewer. JSONExporter's json-ld path
keeps all of them, which is how the same knowledge graph exported two ways came
to carry ten triples of user data through one exporter and none through the
other.

The keys Semantica itself produces (GraphBuilder writes num_entities,
num_relationships, temporal_enabled, timestamp and entity_resolution_applied;
the Neo4j loader writes source, uri and database) are Semantica's own
vocabulary, so they are minted in the declared namespace and declared in
semantica-ns.ttl. Keys the caller supplied are not: which namespace those
belong in is issue #1146, and until that is settled the exporter refuses to
guess rather than inventing an IRI, warns, and takes an explicit
``metadata_terms`` mapping from any caller who already knows the answer.
"""

import json

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD

from semantica.export.rdf_exporter import (
    DEFAULT_METADATA_TERMS,
    RDFSerializer,
    SEMANTICA_NS,
    mint_entity_iri,
)

ENTITY_IRI = "https://example.org/e1"

# The provenance fields the issue names, plus one key Semantica itself writes.
GRAPH_WITH_METADATA = {
    "entities": [
        {
            "id": ENTITY_IRI,
            "type": "https://example.org/Org",
            "text": "Acme Corp",
            "confidence": 0.91,
            "metadata": {"num_entities": 1, "temporal_enabled": True},
        }
    ],
    "relationships": [],
    "metadata": {
        "num_entities": 1,
        "num_relationships": 0,
        "temporal_enabled": False,
        "entity_resolution_applied": True,
    },
}

NUM_ENTITIES = URIRef(f"{SEMANTICA_NS}numEntities")
TEMPORAL_ENABLED = URIRef(f"{SEMANTICA_NS}temporalEnabled")


def _parse(text: str, fmt: str) -> Graph:
    """Assert on the parsed graph, never on the serialized text."""
    g = Graph()
    g.parse(data=text, format=fmt)
    return g


def _serialize(serializer: RDFSerializer, fmt: str, data, **options) -> Graph:
    method, parse_as = {
        "turtle": (serializer.serialize_to_turtle, "turtle"),
        "ntriples": (serializer.serialize_to_ntriples, "nt"),
        "rdfxml": (serializer.serialize_to_rdfxml, "xml"),
        "jsonld": (serializer.serialize_to_jsonld, "json-ld"),
    }[fmt]
    return _parse(method(data, **options), parse_as)


FORMATS = ["turtle", "ntriples", "rdfxml", "jsonld"]


@pytest.mark.parametrize("fmt", FORMATS)
def test_entity_metadata_reaches_every_serialization(fmt):
    """The headline defect: the statement is absent from all four formats."""
    g = _serialize(RDFSerializer(), fmt, GRAPH_WITH_METADATA)
    assert (URIRef(ENTITY_IRI), NUM_ENTITIES, Literal(1)) in g


@pytest.mark.parametrize("fmt", FORMATS)
def test_entity_metadata_booleans_keep_their_datatype(fmt):
    g = _serialize(RDFSerializer(), fmt, GRAPH_WITH_METADATA)
    assert (URIRef(ENTITY_IRI), TEMPORAL_ENABLED, Literal(True)) in g


def test_every_format_writes_the_same_metadata_triples():
    """A value must not change datatype with the serializer, as #1100 found."""
    per_format = {}
    for fmt in FORMATS:
        g = _serialize(RDFSerializer(), fmt, GRAPH_WITH_METADATA)
        per_format[fmt] = {
            (p, o) for s, p, o in g if str(p).startswith(SEMANTICA_NS) and "numEntities" in str(p)
        }
    assert len(set(map(frozenset, per_format.values()))) == 1, per_format


def test_graph_metadata_needs_a_subject_the_caller_named():
    """Graph-level metadata hangs off graph_uri; #1147 owns the default."""
    doc = URIRef("https://example.org/graph/1")
    g = _serialize(
        RDFSerializer(),
        "turtle",
        GRAPH_WITH_METADATA,
        graph_uri=str(doc),
    )
    assert (doc, NUM_ENTITIES, Literal(1)) in g
    assert (doc, URIRef(f"{SEMANTICA_NS}entityResolutionApplied"), Literal(True)) in g


def test_graph_metadata_is_not_invented_without_a_subject():
    g = _serialize(RDFSerializer(), "turtle", GRAPH_WITH_METADATA)
    assert not list(g.subjects(NUM_ENTITIES, Literal(0)))
    # the entity keeps its own metadata; only the graph-level block waits
    assert (URIRef(ENTITY_IRI), NUM_ENTITIES, Literal(1)) in g


def test_an_unknown_key_is_refused_out_loud_not_dropped_in_silence(caplog):
    """#1146 owns which namespace a caller's key belongs in. Until then: warn."""
    data = {
        "entities": [
            {"id": ENTITY_IRI, "text": "Acme", "metadata": {"reviewed_by": "fabio"}}
        ],
        "relationships": [],
    }
    with caplog.at_level("WARNING"):
        g = _serialize(RDFSerializer(), "turtle", data)
    assert not any("reviewed_by" in str(p) for p in g.predicates())
    assert any("reviewed_by" in r.getMessage() for r in caplog.records)
    assert any("1146" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("fmt", FORMATS)
def test_a_caller_who_knows_the_answer_can_supply_the_term(fmt):
    data = {
        "entities": [
            {"id": ENTITY_IRI, "text": "Acme", "metadata": {"reviewed_by": "fabio"}}
        ],
        "relationships": [],
    }
    terms = {"reviewed_by": "http://purl.org/dc/terms/creator"}
    g = _serialize(RDFSerializer(), fmt, data, metadata_terms=terms)
    assert (
        URIRef(ENTITY_IRI),
        URIRef("http://purl.org/dc/terms/creator"),
        Literal("fabio"),
    ) in g


def test_a_literal_with_a_quote_or_newline_still_parses():
    """Metadata is user text; #1098 is the same class of defect one field over."""
    data = {
        "entities": [
            {
                "id": ENTITY_IRI,
                "text": "Acme",
                "metadata": {"source": 'the "Q3" report\nsecond line'},
            }
        ],
        "relationships": [],
    }
    for fmt in FORMATS:
        g = _serialize(RDFSerializer(), fmt, data)
        assert (
            URIRef(ENTITY_IRI),
            URIRef(f"{SEMANTICA_NS}sourceSystem"),
            Literal('the "Q3" report\nsecond line'),
        ) in g


def test_an_iri_valued_key_is_written_as_a_node_not_a_string():
    """The Neo4j loader's ``uri`` key. Note the term is sem:sourceUri, not
    sem:uri: the key names a field, the term names a relation."""
    data = {
        "entities": [
            {"id": ENTITY_IRI, "text": "Acme", "metadata": {"uri": "https://example.org/db"}}
        ],
        "relationships": [],
    }
    g = _serialize(RDFSerializer(), "turtle", data)
    assert (
        URIRef(ENTITY_IRI),
        URIRef(f"{SEMANTICA_NS}sourceUri"),
        URIRef("https://example.org/db"),
    ) in g


def test_output_is_unchanged_when_no_metadata_is_present():
    plain = {
        "entities": [{"id": ENTITY_IRI, "type": "https://example.org/Org", "text": "Acme"}],
        "relationships": [{"source_id": ENTITY_IRI, "target_id": "https://example.org/e2"}],
    }
    serializer = RDFSerializer()
    assert serializer.serialize_to_turtle(plain) == serializer.serialize_to_turtle(plain)
    g = _parse(serializer.serialize_to_turtle(plain), "turtle")
    assert len(g) == 4


def test_every_default_term_is_declared_in_the_shipped_vocabulary():
    """Drift guard: a term the exporter emits and the vocabulary omits is a bug."""
    from semantica.ontology.vocabulary import vocabulary_path

    vocab = Graph()
    vocab.parse(vocabulary_path(), format="turtle")
    declared = {str(s) for s in vocab.subjects()}
    missing = sorted(set(DEFAULT_METADATA_TERMS.values()) - declared)
    assert not missing, f"emitted but undeclared: {missing}"


def test_jsonld_metadata_survives_a_real_jsonld_processor():
    data = {
        "entities": [
            {"id": ENTITY_IRI, "text": "Acme", "metadata": {"num_entities": 3}}
        ],
        "relationships": [],
    }
    raw = RDFSerializer().serialize_to_jsonld(data)
    json.loads(raw)  # must be valid JSON before it can be valid JSON-LD
    g = _parse(raw, "json-ld")
    assert (URIRef(ENTITY_IRI), NUM_ENTITIES, Literal(3)) in g
