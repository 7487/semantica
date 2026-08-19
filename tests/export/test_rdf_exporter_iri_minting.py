"""Minted IRIs must be stable and must sit in the declared namespace (issue #1101).

An entity that arrives without an id gets one minted for it. That identifier was
built from Python's builtin ``hash()``, which is randomised per process, so the
same entity received a different IRI on every run and exports could not be
diffed, deduplicated against an earlier load, or joined to a provenance record
written by an earlier process.

It was also written as ``semantica:entity_N`` inside angle brackets, which is an
IRI in the scheme ``semantica`` rather than the expansion of the declared
``semantica:`` prefix, so it never joined with anything written through it.
"""

import subprocess
import sys

from semantica.export.rdf_exporter import (
    DEFAULT_ENTITY_TYPE,
    DEFAULT_RELATION_TYPE,
    RDFExporter,
    SEMANTICA_NS,
    mint_entity_iri,
    mint_relationship_iri,
)

UNIDENTIFIED = {
    "entities": [{"text": "Acme Corp", "type": "https://example.org/Org"}],
    "relationships": [],
}


def test_minted_entity_iri_is_stable_within_a_process():
    assert mint_entity_iri("Acme Corp") == mint_entity_iri("Acme Corp")


def test_minted_entity_iri_is_stable_across_processes():
    """The regression that matters: identity must survive a restart."""
    script = (
        "from semantica.export.rdf_exporter import mint_entity_iri;"
        "print(mint_entity_iri('Acme Corp'))"
    )
    runs = {
        subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
        ).stdout.strip()
        for seed in ("0", "1", "random")
    }
    assert len(runs) == 1, f"minted IRI differs between processes: {runs}"


def test_minted_iris_are_in_the_declared_namespace():
    assert mint_entity_iri("Acme Corp").startswith(SEMANTICA_NS)
    assert mint_relationship_iri(0, "a", "b").startswith(SEMANTICA_NS)


def test_distinct_entities_get_distinct_iris():
    assert mint_entity_iri("Acme Corp") != mint_entity_iri("Acme Corporation")


def test_turtle_export_writes_a_resolvable_minted_iri():
    turtle = RDFExporter().export_to_rdf(UNIDENTIFIED, format="turtle")

    assert f"<{SEMANTICA_NS}entity_" in turtle
    assert "<semantica:entity_" not in turtle, "scheme 'semantica' is not the prefix"


def test_ntriples_export_agrees_with_turtle_on_the_minted_iri():
    exporter = RDFExporter()
    minted = mint_entity_iri("Acme Corp")

    assert minted in exporter.export_to_rdf(UNIDENTIFIED, format="turtle")
    assert minted in exporter.export_to_rdf(UNIDENTIFIED, format="ntriples")


def test_default_types_are_written_as_full_iris_in_turtle():
    untyped = {"entities": [{"id": "https://example.org/e1", "text": "A"}],
               "relationships": [{"source": "https://example.org/e1",
                                  "target": "https://example.org/e2"}]}
    turtle = RDFExporter().export_to_rdf(untyped, format="turtle")

    assert f"<{DEFAULT_ENTITY_TYPE}>" in turtle
    assert f"<{DEFAULT_RELATION_TYPE}>" in turtle
    assert "<semantica:Entity>" not in turtle
    assert "<semantica:related_to>" not in turtle
