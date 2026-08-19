"""The vocabulary must stay true to what the exporters emit (issue #1107).

A vocabulary document that drifts from the code is worse than none, because it
states that terms mean something while the exporters emit different ones. These
tests tie the two together: every term the serializers can write must be
declared here, so adding a term to an exporter without declaring it fails the
build rather than shipping an undeclared IRI.
"""

import pytest

rdflib = pytest.importorskip("rdflib")

from semantica.export.rdf_exporter import (  # noqa: E402
    DEFAULT_ENTITY_TYPE,
    DEFAULT_RELATION_TYPE,
    SEMANTICA_NS,
)
from semantica.ontology.vocabulary import (  # noqa: E402
    NAMESPACE,
    vocabulary_path,
    vocabulary_turtle,
)

#: Every term the exporters emit in the Semantica namespace, by local name.
#: RDF and OWL-Time paths in export/rdf_exporter.py, document and relationship
#: terms in export/json_exporter.py, roles in provenance/manager.py.
EMITTED_TERMS = {
    "Entity",
    "Relationship",
    "text",
    "confidence",
    "metadata",
    "related_to",
    "source",
    "target",
    "type",
    "entities",
    "relationships",
    "exportedAt",
    "openEndedInterval",
    "role_generator",
}


@pytest.fixture(scope="module")
def graph():
    g = rdflib.Graph()
    g.parse(data=vocabulary_turtle(), format="turtle")
    return g


def test_vocabulary_ships_with_the_package():
    assert vocabulary_path().is_file()


def test_vocabulary_parses(graph):
    assert len(graph) > 0


def test_namespace_matches_the_one_the_exporters_use():
    assert NAMESPACE == SEMANTICA_NS


def test_every_emitted_term_is_declared(graph):
    declared = {
        str(s)[len(NAMESPACE) :]
        for s in set(graph.subjects())
        if isinstance(s, rdflib.URIRef) and str(s).startswith(NAMESPACE)
    }
    missing = EMITTED_TERMS - declared
    assert not missing, f"emitted but not declared in the vocabulary: {sorted(missing)}"


def test_the_defaults_the_exporters_fall_back_to_are_declared(graph):
    for iri in (DEFAULT_ENTITY_TYPE, DEFAULT_RELATION_TYPE):
        assert (rdflib.URIRef(iri), None, None) in graph, f"{iri} is not declared"


def test_every_declared_term_carries_a_label_and_a_comment(graph):
    for subject in set(graph.subjects()):
        if not (isinstance(subject, rdflib.URIRef) and str(subject).startswith(NAMESPACE)):
            continue
        assert graph.value(subject, rdflib.RDFS.label), f"{subject} has no rdfs:label"
        assert graph.value(subject, rdflib.RDFS.comment), f"{subject} has no rdfs:comment"
