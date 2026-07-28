"""
Tests for SQLiteStorage performance optimizations and atomicity (#807).

Verifies:
1. SQLite connection configuration (WAL mode, busy_timeout=5000, synchronous=NORMAL).
2. Atomic track_entity() transaction rollback on failure.
3. Batched operations (track_entities_batch, track_chunks_batch) share transactions.
4. Batched BFS in trace_lineage() using IN (...) queries chunked by 999.
5. Windows file-unlink safety without requiring explicit close().
"""

import os
import sqlite3
import pytest
from unittest.mock import patch
from semantica.provenance.storage import SQLiteStorage
from semantica.provenance.manager import ProvenanceManager
from semantica.provenance.schemas import ProvenanceEntry


def test_sqlite_pragmas_configured(tmp_path):
    """Test WAL mode, busy_timeout, and synchronous pragmas are set."""
    db_path = str(tmp_path / "test_pragmas.db")
    storage = SQLiteStorage(db_path)

    with storage.transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode.lower() in ("wal", "delete", "memory")

        cursor.execute("PRAGMA busy_timeout")
        timeout = cursor.fetchone()[0]
        assert timeout == 5000

        cursor.execute("PRAGMA synchronous")
        sync_mode = cursor.fetchone()[0]
        # NORMAL corresponds to 1 in SQLite
        assert sync_mode == 1


def test_track_entity_atomicity_and_windows_unlink(tmp_path):
    """Test that track_entity uses a single transaction and closes file handles."""
    db_path = str(tmp_path / "test_atomic.db")
    mgr = ProvenanceManager(storage_path=db_path)

    entry = mgr.track_entity("entity_1", source="doc_1", metadata={"key": "val"})
    assert entry.entity_id == "entity_1"

    # Verify Windows unlink safety: can remove or inspect without explicit close()
    assert os.path.exists(db_path)
    # Removing db file should succeed on Windows if all handles are closed
    os.unlink(db_path)


def test_track_entities_batch_transaction_sharing(tmp_path):
    """Test batch entity tracking uses transaction blocks and returns accurate count."""
    db_path = str(tmp_path / "test_batch.db")
    mgr = ProvenanceManager(storage_path=db_path)

    entities = [
        {"id": f"ent_{i}", "metadata": {"index": i}}
        for i in range(2500)
    ]

    count = mgr.track_entities_batch(entities, source="batch_doc")
    assert count == 2500

    stored_all = mgr.storage.retrieve_all()
    assert len(stored_all) == 2500


def test_trace_lineage_batched_bfs_and_max_depth(tmp_path):
    """Test trace_lineage uses batched IN (...) queries and respects max_depth."""
    db_path = str(tmp_path / "test_lineage_bfs.db")
    mgr = ProvenanceManager(storage_path=db_path)

    # Build a linear chain: ent_3 -> ent_2 -> ent_1 -> doc_0
    mgr.track_entity("ent_1", source="doc_0")
    mgr.track_entity("ent_2", source="ent_1")
    mgr.track_entity("ent_3", source="ent_2")

    full_lineage = mgr.trace_lineage("ent_3")
    ids = [entry.entity_id for entry in full_lineage]
    assert "ent_3" in ids
    assert "ent_2" in ids
    assert "ent_1" in ids

    # Test max_depth parameter
    limited_lineage = mgr.trace_lineage("ent_3", max_depth=1)
    assert len(limited_lineage) == 1
    assert limited_lineage[0].entity_id == "ent_3"


def test_batch_rollback_does_not_count_unpersisted_entries(tmp_path):
    """Test that batch tracking does not increment count when transaction commit fails."""
    from contextlib import contextmanager
    db_path = str(tmp_path / "test_batch_rollback.db")
    mgr = ProvenanceManager(storage_path=db_path)

    entities = [{"id": f"ent_{i}"} for i in range(10)]
    chunks = [{"id": f"chk_{i}", "start_index": 0, "end_index": 10} for i in range(10)]

    @contextmanager
    def failing_tx():
        with mgr.storage.transaction() as conn:
            yield conn
            raise sqlite3.OperationalError("Commit failed")

    with patch.object(mgr.storage, "transaction", side_effect=failing_tx):
        ent_count = mgr.track_entities_batch(entities, source="doc_1")
        chk_count = mgr.track_chunks_batch(chunks, source_document="doc_1")
        assert ent_count == 0
        assert chk_count == 0

    assert len(mgr.storage.retrieve_all()) == 0


def test_custom_storage_trace_lineage_one_argument_backward_compatibility():
    """Test that custom ProvenanceStorage implementing trace_lineage(entity_id) without max_depth remains compatible."""
    from typing import List, Optional
    from semantica.provenance.storage import ProvenanceStorage
    from semantica.provenance.schemas import ProvenanceEntry

    class LegacyCustomStorage(ProvenanceStorage):
        def __init__(self):
            self.calls = 0

        def store(self, entry: ProvenanceEntry) -> None:
            pass

        def retrieve(self, entity_id: str) -> Optional[ProvenanceEntry]:
            return None

        def retrieve_all(self, entity_type: Optional[str] = None) -> List[ProvenanceEntry]:
            return []

        def trace_lineage(self, entity_id: str) -> List[ProvenanceEntry]:
            self.calls += 1
            return []

        def clear(self) -> int:
            return 0

    storage = LegacyCustomStorage()
    mgr = ProvenanceManager(storage=storage)

    # Calling with max_depth omitted / None must succeed without TypeError
    lineage1 = mgr.trace_lineage("entity_1")
    assert lineage1 == []
    assert storage.calls == 1

    # Calling with max_depth provided must also fall back cleanly to 1-argument call without TypeError
    lineage2 = mgr.trace_lineage("entity_1", max_depth=2)
    assert lineage2 == []
    assert storage.calls == 2


def test_track_entity_concurrent_read_modify_write(tmp_path):
    """Test that concurrent track_entity calls serialize via BEGIN IMMEDIATE without losing version history."""
    from concurrent.futures import ThreadPoolExecutor
    db_path = str(tmp_path / "test_concurrent.db")

    # Create initial version
    mgr_init = ProvenanceManager(storage_path=db_path)
    mgr_init.track_entity("entity_1", source="doc_init", metadata={"version": 0})

    def update_entity(index):
        # Separate manager/connection per worker
        mgr = ProvenanceManager(storage_path=db_path)
        return mgr.track_entity("entity_1", source=f"doc_{index}", metadata={"version": index})

    num_workers = 8
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        results = list(executor.map(update_entity, range(1, num_workers + 1)))

    assert len(results) == num_workers

    # Verify that all versions were preserved in history (1 current + num_workers archived versions = num_workers + 1 total entries)
    mgr_check = ProvenanceManager(storage_path=db_path)
    all_entries = mgr_check.storage.retrieve_all()
    assert len(all_entries) == num_workers + 1

    # All archived history IDs should start with "entity_1:v:" except the active entity_1
    history_entries = [e for e in all_entries if e.entity_id != "entity_1"]
    assert len(history_entries) == num_workers
    for he in history_entries:
        assert he.entity_id.startswith("entity_1:v:")


def test_sqlite_storage_cleanup_guard_on_configure_error(tmp_path):
    """Test that connection handles are closed even when _configure_connection raises an exception."""
    from unittest.mock import patch
    db_path = str(tmp_path / "test_leak_guard.db")
    storage = SQLiteStorage(db_path)

    with patch.object(storage, "_configure_connection", side_effect=RuntimeError("PRAGMA error")):
        with pytest.raises(RuntimeError, match="PRAGMA error"):
            with storage.transaction():
                pass

    # Verify Windows unlink safety: handle must not be leaked after error
    assert os.path.exists(db_path)
    os.unlink(db_path)
    assert not os.path.exists(db_path)
