"""Facade-level contract tests for the cloud vector store backends.

Every other test in this directory either mocks a backend's internals or
injects a fake directly into ``VectorStore._backend_store``. Both bypass
``_init_backend_store``, which is where the qdrant/pinecone/milvus/weaviate
adapters are actually constructed, so a backend can look fully covered while
being unusable through the public facade.

These tests construct each backend through the real facade path and assert on
the two capabilities ``store migrate`` depends on: an established connection,
and a write path the facade can dispatch to.

Gaps are recorded as strict xfail rather than as assertions that the gap
exists. When the wiring lands these turn into XPASS, which strict mode reports
as a failure, so whoever fixes it is told to remove the marker instead of the
pin silently rotting.

Related: #1265 (enumeration), #1019 (backend conformance).
"""

from unittest.mock import patch

import numpy as np
import pytest

from semantica.vector_store import VectorStore

# Backends whose adapters need a network connection established before use.
_AVAILABILITY_FLAG = {
    "qdrant": "semantica.vector_store.qdrant_store.QDRANT_AVAILABLE",
    "pinecone": "semantica.vector_store.pinecone_store.PINECONE_AVAILABLE",
    "milvus": "semantica.vector_store.milvus_store.MILVUS_AVAILABLE",
    "weaviate": "semantica.vector_store.weaviate_store.WEAVIATE_AVAILABLE",
}

CLOUD_BACKENDS = sorted(_AVAILABILITY_FLAG)

# The facade dispatches store_vectors() to `add` or `add_vectors`. Milvus
# happens to expose add_vectors, so it already resolves; the other three name
# their write method differently and fall through to NotImplementedError.
_NO_WRITE_DISPATCH = {"qdrant", "pinecone", "weaviate"}


def _construct(backend):
    """Build a VectorStore through the real _init_backend_store path."""
    with patch(_AVAILABILITY_FLAG[backend], True):
        return VectorStore(backend=backend, config={"dimension": 3})


def _live_handle(backend_store):
    """The attribute each adapter uses to hold its connected resource."""
    for name in ("collection", "index"):
        if hasattr(backend_store, name):
            return getattr(backend_store, name)
    return None


def _param(backend, broken_for, reason):
    marks = [pytest.mark.xfail(strict=True, reason=reason)] if backend in broken_for else []
    return pytest.param(backend, marks=marks)


@pytest.mark.parametrize("backend", CLOUD_BACKENDS)
def test_facade_constructs_an_adapter(backend):
    """The adapter object itself is built. This part already works."""
    store = _construct(backend)

    assert store._backend_store is not None
    assert store.backend == backend


@pytest.mark.parametrize(
    "backend",
    [
        _param(b, CLOUD_BACKENDS, "_init_backend_store never connects or selects a collection")
        for b in CLOUD_BACKENDS
    ],
)
def test_backend_is_connected_after_construction(backend):
    """A constructed store should be usable without the caller reaching past
    the facade to call connect() and get_collection() itself.

    Today _init_backend_store constructs the adapter and stops, so every read
    path raises "Collection not initialized" / "Index not initialized".
    """
    store = _construct(backend)

    assert _live_handle(store._backend_store) is not None


@pytest.mark.parametrize(
    "backend",
    [
        _param(b, _NO_WRITE_DISPATCH, "facade dispatches only to add/add_vectors")
        for b in CLOUD_BACKENDS
    ],
)
def test_store_vectors_dispatch_resolves(backend):
    """store_vectors() should reach the backend's write method.

    This isolates dispatch from connectivity on purpose: any error other than
    NotImplementedError means the facade found a method and the failure came
    from further down, which is the connection gap covered above.
    """
    store = _construct(backend)

    try:
        store.store_vectors([np.zeros(3)], [{}], ids=["a"])
    except NotImplementedError as exc:
        pytest.fail(f"no write dispatch for {backend}: {exc}")
    except Exception:
        pass


def test_milvus_write_dispatch_already_resolves():
    """Guards the assumption behind _NO_WRITE_DISPATCH.

    Milvus is the control case: it exposes add_vectors, which the existing
    dispatch chain already matches. If this ever stops holding, the xfail list
    above is wrong rather than the feature being broken.
    """
    store = _construct("milvus")

    assert hasattr(store._backend_store, "add_vectors")
