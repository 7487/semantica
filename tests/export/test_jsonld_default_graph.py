"""Every JSON-LD export must put its payload in the default graph.

A JSON-LD document carrying a top-level ``@id`` *and* a top-level ``@graph`` is
a **named graph**: the contents of ``@graph`` are quads named by that ``@id``,
not triples in the default graph. ``rdflib.Graph.parse()`` — the ordinary way a
Python consumer loads RDF — keeps the default graph and discards the rest,
without an error. ``JSONExporter`` emitted exactly that shape:

* ``_convert_to_jsonld`` wrote the payload into ``@graph`` and then stamped a
  document ``@id`` beside it, so every list export and every generic-dict
  export was named;
* ``export_knowledge_graph`` converted the graph to JSON-LD and handed the
  finished document back to ``export()``, which converted it a *second* time.
  The converted document no longer has ``entities``/``relationships`` keys, so
  the second pass treated it as opaque and wrapped it in ``@graph`` — burying
  a whole knowledge graph, entities, relationships and all, inside a named
  graph whose name is a wall-clock timestamp.

Measured on v0.6.6: a two-entity, one-relationship graph exported to JSON-LD
parsed as **2 triples** with ``Graph()`` and 21 quads with ``Dataset()``. The 19
missing triples were the entire knowledge graph, and nothing reported a
problem. Semantica's own reader has the mirror of this bug (#1129), so the
export could not even be read back by Semantica.
"""

import json

import pytest
from rdflib import Dataset, Graph

from semantica.export.json_exporter import JSONExporter

KG = {
    "entities": [
        {"id": "https://example.org/e1", "text": "Acme Corp", "type": "ORG"},
        {"id": "https://example.org/e2", "text": "Jane Roe", "type": "PERSON"},
    ],
    "relationships": [
        {
            "source_id": "https://example.org/e1",
            "target_id": "https://example.org/e2",
            "type": "employs",
        }
    ],
    "metadata": {"source_document": "contract.pdf"},
}

RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"

PAYLOADS = {
    "knowledge_graph": KG,
    "list": [
        {"@id": "https://example.org/a", RDFS_LABEL: "A"},
        {"@id": "https://example.org/b", RDFS_LABEL: "B"},
    ],
    "generic_dict": {"@id": "https://example.org/x", RDFS_LABEL: "X"},
}


def _write(payload, tmp_path, name="out.jsonld", **options):
    path = tmp_path / name
    JSONExporter().export(payload, path, format="json-ld", **options)
    return path


def _counts(path):
    """Triples a default-graph reader sees, and quads a quad reader sees."""
    graph = Graph()
    graph.parse(str(path), format="json-ld")
    dataset = Dataset()
    dataset.parse(str(path), format="json-ld")
    return len(graph), sum(1 for _ in dataset.quads((None, None, None, None)))


@pytest.mark.parametrize("name", sorted(PAYLOADS))
def test_no_export_hides_its_payload_in_a_named_graph(name, tmp_path):
    """A top-level @id beside a top-level @graph names the graph."""
    path = _write(PAYLOADS[name], tmp_path, f"{name}.jsonld")
    document = json.loads(path.read_text())

    assert not ("@id" in document and "@graph" in document), (
        f"{name}: @id + @graph at the top level makes a named graph, "
        "which a default-graph reader discards in full"
    )


@pytest.mark.parametrize("name", sorted(PAYLOADS))
def test_a_plain_graph_reader_loses_nothing(name, tmp_path):
    """Graph() and Dataset() must agree: no triple may live outside the default graph."""
    path = _write(PAYLOADS[name], tmp_path, f"{name}.jsonld")
    triples, quads = _counts(path)

    assert triples == quads, (
        f"{name}: Graph() read {triples} of {quads} statements; "
        f"{quads - triples} were dropped silently"
    )


def test_exported_knowledge_graph_survives_a_default_graph_read(tmp_path):
    """The entities and the relationship must be there after a plain parse."""
    path = tmp_path / "kg.jsonld"
    JSONExporter().export_knowledge_graph(KG, path, format="json-ld")

    graph = Graph()
    graph.parse(str(path), format="json-ld")
    subjects = {str(s) for s in graph.subjects()}
    objects = {str(o) for o in graph.objects()}

    assert "https://example.org/e1" in subjects
    assert "https://example.org/e2" in subjects
    assert "Acme Corp" in objects
    assert "Jane Roe" in objects
    assert "employs" in objects


def test_knowledge_graph_is_not_converted_twice(tmp_path):
    """A nested @context is the signature of the document being re-converted."""
    path = tmp_path / "kg.jsonld"
    JSONExporter().export_knowledge_graph(KG, path, format="json-ld")
    document = json.loads(path.read_text())

    nested = [
        node
        for node in document.get("@graph", [])
        if isinstance(node, dict) and "@context" in node
    ]
    assert nested == [], "the knowledge graph was converted, then converted again"


def test_document_provenance_still_reaches_the_default_graph(tmp_path):
    """Keeping the payload readable must not cost the export its own metadata."""
    path = _write(PAYLOADS["list"], tmp_path)

    graph = Graph()
    graph.parse(str(path), format="json-ld")
    predicates = {str(p) for p in graph.predicates()}

    assert "https://semantica.dev/ns#exportedAt" in predicates
    assert "https://semantica.dev/ns#format" in predicates
    assert {"https://example.org/a", "https://example.org/b"} <= {
        str(s) for s in graph.subjects()
    }
    assert {"A", "B"} <= {str(o) for o in graph.objects()}
