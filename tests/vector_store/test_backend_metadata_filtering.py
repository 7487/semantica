import unittest
from unittest.mock import MagicMock, patch
import numpy as np

from semantica.vector_store.faiss_store import FAISSStore
from semantica.vector_store.qdrant_store import QdrantStore
from semantica.vector_store.pinecone_store import PineconeStore
from semantica.vector_store.milvus_store import MilvusStore
from semantica.vector_store.pgvector_store import PgVectorStore
from semantica.vector_store.weaviate_store import WeaviateStore


class TestBackendMetadataFiltering(unittest.TestCase):

    def test_faiss_store_filter_by_metadata(self):
        store = FAISSStore(dimension=2)
        mock_index = MagicMock()
        mock_index.metadata = {
            "v1": {"category": "finance", "score": 10},
            "v2": {"category": "tech", "score": 20},
        }
        mock_index.get_vector.side_effect = lambda vid: np.array([1.0, 0.0]) if vid == "v1" else np.array([0.0, 1.0])
        store.index = mock_index

        results = store.filter_by_metadata({"category": "finance"}, limit=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "v1")
        self.assertEqual(results[0]["metadata"], {"category": "finance", "score": 10})

    @patch('semantica.vector_store.qdrant_store.FieldCondition', MagicMock())
    @patch('semantica.vector_store.qdrant_store.MatchValue', MagicMock())
    @patch('semantica.vector_store.qdrant_store.Filter', MagicMock())
    @patch('semantica.vector_store.qdrant_store.QDRANT_AVAILABLE', True)
    def test_qdrant_store_filter_by_metadata(self):
        store = QdrantStore()
        mock_collection = MagicMock()
        mock_collection.collection_name = "test_coll"
        store.collection = mock_collection
        mock_client = MagicMock()
        rec = MagicMock()
        rec.id = "q1"
        rec.payload = {"env": "prod"}
        rec.vector = [0.1, 0.2]
        mock_client.scroll.return_value = ([rec], None)
        store.client = mock_client

        results = store.filter_by_metadata({"env": "prod"}, limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "q1")
        self.assertEqual(results[0]["metadata"], {"env": "prod"})
        mock_client.scroll.assert_called_once()

    @patch('semantica.vector_store.pinecone_store.PINECONE_AVAILABLE', True)
    def test_pinecone_store_filter_by_metadata(self):
        store = PineconeStore()
        mock_index_wrapper = MagicMock()
        mock_inner_index = MagicMock()

        match_obj = MagicMock()
        match_obj.id = "p1"
        match_obj.metadata = {"status": "active"}
        match_obj.values = [0.1, 0.9]

        response = MagicMock()
        response.matches = [match_obj]
        mock_inner_index.query.return_value = response
        mock_index_wrapper.index = mock_inner_index
        store.index = mock_index_wrapper

        results = store.filter_by_metadata({"status": "active"}, limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "p1")
        self.assertEqual(results[0]["metadata"], {"status": "active"})

    @patch('semantica.vector_store.milvus_store.MILVUS_AVAILABLE', True)
    def test_milvus_store_filter_by_metadata(self):
        store = MilvusStore()
        mock_coll_wrapper = MagicMock()
        mock_inner_coll = MagicMock()
        mock_inner_coll.query.return_value = [
            {"id": "m1", "vector": [0.3, 0.4], "metadata": {"lang": "py"}}
        ]
        mock_coll_wrapper.collection = mock_inner_coll
        store.collection = mock_coll_wrapper

        results = store.filter_by_metadata({"lang": "py"}, limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "m1")
        self.assertEqual(results[0]["metadata"], {"lang": "py"})

    @patch('semantica.vector_store.pgvector_store.PSYCOPG3_AVAILABLE', True)
    @patch('semantica.vector_store.pgvector_store.psycopg_sql')
    def test_pgvector_store_filter_by_metadata(self, mock_sql):
        store = object.__new__(PgVectorStore)
        store.table_name = "test_vectors"
        store._is_safe_identifier = lambda k: True

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            ("pg1", [0.1, 0.2], {"org": "acme"})
        ]
        mock_conn.cursor.return_value = mock_cur

        with patch.object(PgVectorStore, '_get_connection', return_value=MagicMock(__enter__=MagicMock(return_value=mock_conn), __exit__=MagicMock())):
            results = store.filter_by_metadata({"org": "acme"}, limit=10)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["id"], "pg1")
            self.assertEqual(results[0]["metadata"], {"org": "acme"})

    def test_weaviate_store_filter_by_metadata(self):
        store = WeaviateStore()
        mock_coll = MagicMock()
        obj1 = MagicMock()
        obj1.uuid = "w-uuid-1"
        obj1.properties = {"dept": "eng"}
        obj1.vector = [0.5, 0.5]
        objs = MagicMock()
        objs.objects = [obj1]
        mock_coll.query.fetch_objects.return_value = objs
        store.collection = mock_coll

        with patch('semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE', True):
            results = store.filter_by_metadata({"dept": "eng"}, limit=5)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["id"], "w-uuid-1")
            self.assertEqual(results[0]["metadata"], {"dept": "eng"})


if __name__ == "__main__":
    unittest.main()
