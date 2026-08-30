"""Tests for WeaviateStore.iter_all() cursor enumeration.

weaviate-client is not installed in this environment, so these drive the real
WeaviateStore against MagicMocks, following the pattern already used for
weaviate in test_backend_metadata_filtering.py.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from semantica.utils.exceptions import ProcessingError
from semantica.vector_store.weaviate_store import WeaviateStore


def _obj(uuid, properties=None, vector=None):
    """Stand-in for a weaviate v4 returned object."""
    obj = MagicMock()
    obj.uuid = uuid
    obj.properties = properties
    obj.vector = vector
    return obj


def _page(objects):
    """Stand-in for a fetch_objects() response."""
    response = MagicMock()
    response.objects = objects
    return response


def _store_with_pages(*pages):
    store = WeaviateStore()
    store.collection = MagicMock()
    store.collection.query.fetch_objects.side_effect = list(pages)
    return store


@patch("semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE", True)
def test_iter_all_threads_uuid_cursor_across_pages():
    """The next page must continue after the last object's UUID."""
    store = _store_with_pages(
        _page([_obj("uuid-1"), _obj("uuid-2")]),
        _page([_obj("uuid-3")]),
    )

    result = list(store.iter_all(batch_size=2))

    assert [item["id"] for item in result] == ["uuid-1", "uuid-2", "uuid-3"]
    calls = store.collection.query.fetch_objects.call_args_list
    assert "after" not in calls[0][1]
    assert calls[1][1]["after"] == "uuid-2"


@patch("semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE", True)
def test_iter_all_stops_on_short_page():
    """A page smaller than batch_size means the collection is exhausted."""
    store = _store_with_pages(_page([_obj("uuid-1")]))

    result = list(store.iter_all(batch_size=5))

    assert [item["id"] for item in result] == ["uuid-1"]
    assert store.collection.query.fetch_objects.call_count == 1


@patch("semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE", True)
def test_iter_all_stops_when_cursor_stops_advancing():
    """A full scan has no result cap, so a stalled cursor would loop forever.

    Pathological rather than expected from a real server, but termination is
    the property that matters: this must not hang.
    """
    store = WeaviateStore()
    store.collection = MagicMock()
    store.collection.query.fetch_objects.return_value = _page(
        [_obj("same-uuid"), _obj("same-uuid")]
    )

    result = list(store.iter_all(batch_size=2))

    assert store.collection.query.fetch_objects.call_count == 2
    assert len(result) == 4


@patch("semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE", True)
def test_iter_all_empty_collection_yields_nothing():
    store = _store_with_pages(_page([]))

    assert list(store.iter_all()) == []


@patch("semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE", True)
def test_iter_all_converts_objects_to_the_shared_result_shape():
    store = _store_with_pages(
        _page([_obj("uuid-7", properties={"tag": "x"}, vector=[0.1, 0.2, 0.3])]),
    )

    item = list(store.iter_all())[0]

    assert item["id"] == "uuid-7"
    assert item["metadata"] == {"tag": "x"}
    np.testing.assert_allclose(item["vector"], np.array([0.1, 0.2, 0.3]))


@patch("semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE", True)
def test_iter_all_handles_missing_properties_and_vector():
    store = _store_with_pages(_page([_obj("uuid-1", properties=None, vector=None)]))

    item = list(store.iter_all())[0]

    assert item["metadata"] == {}
    assert item["vector"] is None


@patch("semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE", True)
def test_iter_all_treats_empty_vector_as_none():
    store = _store_with_pages(_page([_obj("uuid-1", vector=[])]))

    assert list(store.iter_all())[0]["vector"] is None


@patch("semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE", True)
def test_iter_all_requests_vectors():
    """Weaviate omits vectors unless include_vector is set."""
    store = _store_with_pages(_page([]))

    list(store.iter_all(batch_size=64))

    kwargs = store.collection.query.fetch_objects.call_args[1]
    assert kwargs["include_vector"] is True
    assert kwargs["limit"] == 64


@patch("semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE", True)
def test_iter_all_falls_back_to_offset_when_after_unsupported():
    """Older clients reject `after`; the scan degrades to numeric offset."""
    store = WeaviateStore()
    store.collection = MagicMock()
    seen = {"calls": 0}

    def _fetch(**kwargs):
        if "after" in kwargs:
            raise TypeError("unexpected keyword argument 'after'")
        seen["calls"] += 1
        if seen["calls"] == 1:
            return _page([_obj("uuid-1"), _obj("uuid-2")])
        return _page([_obj("uuid-3")])

    store.collection.query.fetch_objects.side_effect = _fetch

    result = list(store.iter_all(batch_size=2))

    assert [item["id"] for item in result] == ["uuid-1", "uuid-2", "uuid-3"]
    offsets = [
        c[1]["offset"]
        for c in store.collection.query.fetch_objects.call_args_list
        if "offset" in c[1]
    ]
    assert offsets == [2]


@patch("semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE", True)
def test_iter_all_raises_when_collection_not_initialized():
    """Must fail loudly, not yield nothing.

    An empty scan is indistinguishable from an empty source, which would let
    `store migrate` report success having copied nothing (issue #1083).
    """
    store = WeaviateStore()

    with pytest.raises(ProcessingError, match="Collection not initialized"):
        list(store.iter_all())


@patch("semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE", False)
def test_iter_all_raises_when_weaviate_unavailable():
    store = WeaviateStore()
    store.collection = MagicMock()

    with pytest.raises(ProcessingError):
        list(store.iter_all())


@patch("semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE", True)
def test_iter_all_propagates_fetch_errors():
    store = WeaviateStore()
    store.collection = MagicMock()
    store.collection.query.fetch_objects.side_effect = RuntimeError("connection reset")

    with pytest.raises(RuntimeError, match="connection reset"):
        list(store.iter_all())
