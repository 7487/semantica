from semantica.ontology import (
    OntologyEngine,
    OntologyQualityGate,
    QualitySeverity,
    ontology_quality_check,
)


def _ontology():
    return {
        "classes": [
            {"name": "Person", "uri": "https://example.org/Person"},
            {"name": "Company", "uri": "https://example.org/Company"},
        ],
        "properties": [
            {
                "name": "worksFor",
                "type": "object",
                "domain": ["Person"],
                "range": ["Company"],
            },
            {
                "name": "name",
                "type": "data",
                "domain": ["Person"],
                "range": "string",
            },
        ],
    }


def test_quality_gate_reports_a_healthy_ontology():
    report = ontology_quality_check(_ontology())

    assert report.passed
    assert report.metrics["coverage"] == 1.0
    assert report.error_count == 0
    assert report.to_dict()["stats"]["properties"] == 2


def test_quality_gate_finds_schema_and_endpoint_problems():
    ontology = {
        "classes": [{"name": "Person"}, {"name": "Unused"}],
        "properties": [
            {
                "name": "worksFor",
                "type": "object",
                "domain": ["Person"],
                "range": ["MissingCompany"],
            },
            {"name": "unattached", "type": "data"},
        ],
    }
    graph = {
        "entities": [{"id": "p1", "type": "Person"}],
        "relationships": [
            {"source_id": "p1", "target_id": "missing", "type": "worksFor"}
        ],
    }

    report = OntologyQualityGate().check(ontology, graph_data=graph)
    codes = {issue.code for issue in report.issues}

    assert not report.passed
    assert "UNKNOWN_RANGE" in codes
    assert "UNRESOLVED_RELATIONSHIP_ENDPOINT" in codes
    assert "ORPHAN_CLASS" in codes
    assert "MISSING_RANGE" in codes
    assert any(issue.severity == QualitySeverity.WARNING for issue in report.issues)


def test_quality_gate_supports_thresholds_and_legacy_endpoint_keys():
    ontology = {
        "classes": [{"name": "Person"}],
        "properties": [
            {
                "name": "name",
                "type": "data",
                "domain": "Person",
                "range": "xsd:string",
            }
        ],
    }
    graph = {
        "entities": [{"entity_id": "p1", "type": "Person", "name": "Alice"}],
        "relationships": [{"source": "p1", "target": "p1", "type": "knows"}],
    }

    report = ontology_quality_check(
        ontology,
        graph_data=graph,
        thresholds={"min_coverage": 1.0},
    )

    assert report.passed
    assert report.threshold_failures == []
    assert report.stats["relationships"] == 1


def test_quality_gate_can_fail_on_warnings():
    report = ontology_quality_check(
        {"classes": [{"name": "Person"}], "properties": []},
        fail_on_warnings=True,
    )

    assert not report.passed
    assert "fail_on_warnings" in report.threshold_failures


def test_engine_exposes_quality_check():
    report = OntologyEngine().quality_check(_ontology())

    assert report.passed
