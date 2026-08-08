import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from semantica.vector_store.vector_store import VectorStore

class TestVectorStore(unittest.TestCase):

    def setUp(self):
        self.mock_logger = MagicMock()
        self.mock_tracker = MagicMock()
        
        self.logger_patcher = patch('semantica.vector_store.vector_store.get_logger', return_value=self.mock_logger)
        self.tracker_patcher = patch('semantica.vector_store.vector_store.get_progress_tracker', return_value=self.mock_tracker)
        self.indexer_patcher = patch('semantica.vector_store.vector_store.VectorIndexer')
        self.retriever_patcher = patch('semantica.vector_store.vector_store.VectorRetriever')
        
        self.logger_patcher.start()
        self.tracker_patcher.start()
        self.MockVectorIndexer = self.indexer_patcher.start()
        self.MockVectorRetriever = self.retriever_patcher.start()

    def tearDown(self):
        self.logger_patcher.stop()
        self.tracker_patcher.stop()
        self.indexer_patcher.stop()
        self.retriever_patcher.stop()

    def test_initialization(self):
        store = VectorStore(backend="inmemory", dimension=128)
        self.assertEqual(store.dimension, 128)
        self.MockVectorIndexer.assert_called_once()
        self.MockVectorRetriever.assert_called_once()

    def test_store_vectors(self):
        store = VectorStore(backend="inmemory")
        vectors = [np.array([0.1, 0.2]), np.array([0.3, 0.4])]
        metadata = [{"id": "1"}, {"id": "2"}]

        ids = store.store_vectors(vectors, metadata)

        self.assertEqual(len(ids), 2)
        self.assertEqual(len(store.vectors), 2)
        self.assertEqual(len(store.metadata), 2)
        store.indexer.create_index.assert_called_once()

    def test_search_vectors(self):
        store = VectorStore(backend="inmemory")
        # Pre-populate store (though search uses retriever which we mock)
        store.vectors = {"v1": np.array([0.1]), "v2": np.array([0.2])}

        query_vector = np.array([0.15])
        expected_results = [{"id": "v1", "score": 0.9}]
        store.retriever.search_similar.return_value = expected_results

        results = store.search_vectors(query_vector, k=5)

        self.assertEqual(results, expected_results)
        store.retriever.search_similar.assert_called_once()

    def test_update_vectors(self):
        store = VectorStore(backend="inmemory")
        store.vectors = {"v1": np.array([0.1])}

        new_vector = np.array([0.9])
        store.update_vectors(["v1"], [new_vector])

        np.testing.assert_array_equal(store.vectors["v1"], new_vector)
        store.indexer.create_index.assert_called()

    def test_delete_vectors(self):
        store = VectorStore(backend="inmemory")
        store.vectors = {"v1": np.array([0.1]), "v2": np.array([0.2])}
        store.metadata = {"v1": {}, "v2": {}}

        store.delete_vectors(["v1"])

        self.assertNotIn("v1", store.vectors)
        self.assertIn("v2", store.vectors)
        store.indexer.create_index.assert_called()

    def test_get_vector_and_metadata(self):
        store = VectorStore(backend="inmemory")
        vec = np.array([0.1])
        meta = {"info": "test"}
        store.vectors = {"v1": vec}
        store.metadata = {"v1": meta}
        
        self.assertTrue(np.array_equal(store.get_vector("v1"), vec))
        self.assertEqual(store.get_metadata("v1"), meta)
        self.assertIsNone(store.get_vector("nonexistent"))

    def test_store_vectors_metadata_forwarding(self):
        """Test that metadata is correctly forwarded to backends that support it."""
        store = VectorStore(backend="inmemory")
        
        class MockBackendWithMetadata:
            def __init__(self):
                self.received_metadata = None
                
            def add_vectors(self, vectors, ids=None, metadata=None, **options):
                self.received_metadata = metadata
                return ["vec1"]
                
        mock_backend = MockBackendWithMetadata()
        store._backend_store = mock_backend
        
        vectors = [np.array([0.1, 0.2])]
        metadata = [{"id": "1"}]
        
        store.store_vectors(vectors, metadata=metadata)
        
        self.assertEqual(mock_backend.received_metadata, metadata)

    def test_store_vectors_strict_backend(self):
        """Test that metadata is dropped for strict backends without TypeError."""
        store = VectorStore(backend="inmemory")
        
        class MockBackendStrict:
            def __init__(self):
                self.called = False
                
            def add_vectors(self, vectors):
                self.called = True
                return ["vec1"]
                
        mock_backend = MockBackendStrict()
        store._backend_store = mock_backend
        
        vectors = [np.array([0.1, 0.2])]
        metadata = [{"id": "1"}]
        
        # This should not raise TypeError since metadata is dropped
        store.store_vectors(vectors, metadata=metadata)
        
        self.assertTrue(mock_backend.called)

    def test_filter_by_metadata_inmemory(self):
        """Test _filter_by_metadata on inmemory backend."""
        store = VectorStore(backend="inmemory")
        store.metadata = {
            "v1": {"category": "finance", "amount": 100, "tags": ["a", "b"]},
            "v2": {"category": "finance", "amount": 500, "tags": ["b", "c"]},
            "v3": {"category": "tech", "amount": 200, "tags": ["c"]},
        }
        store.vectors = {
            "v1": np.array([0.1]),
            "v2": np.array([0.2]),
            "v3": np.array([0.3]),
        }

        # Exact filter
        results = store._filter_by_metadata({"category": "finance"}, limit=10)
        self.assertEqual(len(results), 2)
        res_ids = {r["id"] for r in results}
        self.assertEqual(res_ids, {"v1", "v2"})

        # Range filter
        results = store._filter_by_metadata({"amount": {"min": 150}}, limit=10)
        self.assertEqual(len(results), 2)
        res_ids = {r["id"] for r in results}
        self.assertEqual(res_ids, {"v2", "v3"})

        # List intersection filter
        results = store._filter_by_metadata({"tags": ["a"]}, limit=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "v1")

    def test_filter_by_metadata_persistent_backend_delegation(self):
        """Test that persistent backend delegates filter_by_metadata without AttributeError."""
        store = VectorStore(backend="inmemory")
        # Simulate persistent backend by deleting self.metadata attribute if any
        if hasattr(store, "metadata"):
            delattr(store, "metadata")

        mock_backend = MagicMock()
        mock_backend.filter_by_metadata.return_value = [
            {"id": "p1", "metadata": {"category": "test"}, "vector": np.array([0.5])}
        ]
        store._backend_store = mock_backend
        store.backend = "faiss"

        # Should NOT raise AttributeError: 'VectorStore' object has no attribute 'metadata'
        results = store._filter_by_metadata({"category": "test"}, limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "p1")
        mock_backend.filter_by_metadata.assert_called_once_with(filters={"category": "test"}, limit=5)

    def test_filter_by_metadata_backend_not_implemented(self):
        """Test that missing filter_by_metadata method raises NotImplementedError."""
        store = VectorStore(backend="inmemory")
        if hasattr(store, "metadata"):
            delattr(store, "metadata")

        store.backend = "unknown"
        store._backend_store = object()

        with self.assertRaises(NotImplementedError):
            store._filter_by_metadata({"key": "val"}, limit=10)

if __name__ == '__main__':
    unittest.main()
