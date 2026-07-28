"""
Tests for ProvenanceManager wiring into Explorer routes and application startup.
"""

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from semantica.context.context_graph import ContextGraph
from semantica.explorer.app import create_app
from semantica.explorer.session import GraphSession
from semantica.provenance import ProvenanceManager
from semantica.provenance.storage import SQLiteStorage


@pytest.fixture
def session():
    sess = GraphSession(ContextGraph(advanced_analytics=False))
    return sess


@pytest.fixture
def client(session):
    app = create_app(session=session)
    with TestClient(app) as tc:
        yield tc


def test_provenance_manager_wiring_audit_path(client, session):
    """Test that a multi-hop track_entity chain is returned from /api/provenance with source='audit'."""
    pm = session.provenance_manager
    pm.track_entity(entity_id="grandparent", source="doc_1", entity_type="document")
    pm.track_entity(
        entity_id="parent",
        source="doc_1",
        metadata={"derived_from": "grandparent"},
        entity_type="chunk",
    )
    pm.track_entity(
        entity_id="child",
        source="doc_1",
        metadata={"derived_from": "parent"},
        entity_type="named_entity",
    )

    response = client.get("/api/provenance", params={"node_id": "child"})
    assert response.status_code == 200
    data = response.json()

    assert data.get("source") == "audit"
    node_ids = {n["id"] for n in data["nodes"]}
    assert {"grandparent", "parent", "child"}.issubset(node_ids)
    edge_pairs = {(e["source"], e["target"]) for e in data["edges"]}
    assert ("grandparent", "parent") in edge_pairs
    assert ("parent", "child") in edge_pairs

    # Confirm /api/provenance/report also uses audit path
    rep_response = client.get("/api/provenance/report", params={"node_id": "child"})
    assert rep_response.status_code == 200
    report_data = rep_response.json()
    assert report_data.get("source") == "audit"
    assert report_data["lineage"].get("source") == "audit"


def test_provenance_manager_wiring_fallback_no_records(client, session):
    """Test that a node with no audit records falls back cleanly to source='graph_traversal'."""
    session.add_node("orphan_node", content="Orphan Node Content", node_type="entity")

    response = client.get("/api/provenance", params={"node_id": "orphan_node"})
    assert response.status_code == 200
    data = response.json()

    assert data.get("source") == "graph_traversal"
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["id"] == "orphan_node"


def test_provenance_manager_wiring_error_graceful_degradation(client, session):
    """Test that a simulated ProvenanceManager error degrades gracefully to naive traversal (200, not 500)."""
    session.add_node("some_node", content="Some Node", node_type="entity")

    with patch.object(
        session.provenance_manager,
        "get_lineage",
        side_effect=RuntimeError("Simulated storage failure"),
    ):
        response = client.get("/api/provenance", params={"node_id": "some_node"})
        assert response.status_code == 200
        data = response.json()
        assert data.get("source") == "graph_traversal"
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["id"] == "some_node"


def test_create_app_provenance_storage_path_wiring(tmp_path):
    """Test that create_app(provenance_storage_path=...) sets per-instance storage without global mutation."""
    test_path = str(tmp_path / "test_explorer_prov.db")
    app = create_app(provenance_storage_path=test_path)

    with TestClient(app):
        assert app.state.session._provenance_storage_path == test_path
        assert isinstance(app.state.session.provenance_manager.storage, SQLiteStorage)


def test_provenance_storage_isolation_between_sessions(tmp_path):
    """Test that two GraphSessions with different storage paths do not leak state across instances."""
    path1 = str(tmp_path / "session1.db")
    path2 = str(tmp_path / "session2.db")
    sess1 = GraphSession(ContextGraph(advanced_analytics=False), provenance_storage_path=path1)
    sess2 = GraphSession(ContextGraph(advanced_analytics=False), provenance_storage_path=path2)

    pm1 = sess1.provenance_manager
    pm2 = sess2.provenance_manager

    assert pm1.storage.db_path == path1
    assert pm2.storage.db_path == path2
    assert pm1 is not pm2
    assert pm1.storage is not pm2.storage

    # Write an entity to sess1 and confirm it does NOT appear in sess2
    pm1.track_entity(entity_id="node_in_1", source="doc_A", entity_type="entity")
    assert pm1.storage.retrieve("node_in_1") is not None
    assert pm2.storage.retrieve("node_in_1") is None
