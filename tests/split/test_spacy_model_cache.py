from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from semantica.semantic_extract import methods as se_methods
from semantica.split import methods as split_methods
from semantica.split import semantic_chunker


@pytest.fixture(autouse=True)
def clear_cache():
    se_methods.clear_spacy_model_cache()
    yield
    se_methods.clear_spacy_model_cache()


@pytest.fixture(autouse=True)
def force_spacy_available(monkeypatch):
    # split.methods and split.semantic_chunker each compute their own
    # SPACY_AVAILABLE flag from the real environment at import time; force
    # both true so these tests exercise the spaCy branch regardless of
    # whether spaCy is actually installed where they run.
    monkeypatch.setattr(split_methods, "SPACY_AVAILABLE", True)
    monkeypatch.setattr(semantic_chunker, "SPACY_AVAILABLE", True)


def _fake_spacy(load):
    return SimpleNamespace(
        load=load, 
        util=SimpleNamespace(
        is_package=lambda _name: True
        ),
    )


def _nlp_mock(sentences=("Hello world.",)):
    """A stand-in spaCy Language object: callable, returns a doc with .sents."""
    nlp = MagicMock()
    nlp.return_value = SimpleNamespace(
        sents=[SimpleNamespace(text=s) for s in sentences]
    )
    return nlp


class TestSpacyModelCache:
    """split.methods and split.semantic_chunker must share the cached model
    defined in semantic_extract.methods instead of each calling spacy.load()
    independently.
    """

    def test_split_by_sentences_reuses_cached_model(self, monkeypatch):
        calls = []

        def fake_load(name, **kwargs):
            calls.append((name, kwargs))
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(fake_load))

        split_methods.split_by_sentences("Hello world. Bye world.")
        split_methods.split_by_sentences("Another sentence here.")
        split_methods.split_by_sentences("A third call.")

        assert len(calls) == 1, "spacy.load should run once, not once per call"
        assert calls[0][0] == "en_core_web_sm"

    def test_semantic_chunker_reuses_cached_model_across_instances(self, monkeypatch):
        calls = []

        def fake_load(name, **kwargs):
            calls.append((name, kwargs))
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(fake_load))

        chunker1 = semantic_chunker.SemanticChunker()
        chunker2 = semantic_chunker.SemanticChunker()

        assert len(calls) == 1, "each new SemanticChunker should not reload the model"
        assert chunker1.nlp is chunker2.nlp

    def test_split_methods_and_semantic_chunker_share_the_cache(self, monkeypatch):
        calls = []

        def fake_load(name, **kwargs):
            calls.append((name, kwargs))
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(fake_load))

        split_methods.split_by_sentences("Test sentence for split.methods.")
        semantic_chunker.SemanticChunker()

        assert len(calls) == 1, (
            "split.methods and split.semantic_chunker must share one cached "
            "model instead of each loading their own"
        )

    def test_distinct_model_names_load_separately(self, monkeypatch):
        calls = []

        def fake_load(name, **kwargs):
            calls.append((name, kwargs))
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(fake_load))

        sm_chunker = semantic_chunker.SemanticChunker(model="en_core_web_sm")
        lg_chunker = semantic_chunker.SemanticChunker(model="en_core_web_lg")
        sm_chunker_again = semantic_chunker.SemanticChunker(model="en_core_web_sm")

        assert [name for name, _ in calls] == ["en_core_web_sm", "en_core_web_lg"]
        assert sm_chunker.nlp is sm_chunker_again.nlp
        assert sm_chunker.nlp is not lg_chunker.nlp

    def test_no_disable_kwarg_requested(self, monkeypatch):
        """split.methods and split.semantic_chunker both want the full
        pipeline (they need .sents, which requires the parser/senter). If
        either one later starts requesting a trimmed pipeline (e.g.
        disable=["ner"]), the name-only cache key in load_spacy_model would
        silently hand back a cached model built for a different config --
        this test should catch that the moment it happens.
        """
        calls = []

        def fake_load(_name, **kwargs):
            calls.append(kwargs)
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(fake_load))

        split_methods.split_by_sentences("Hello world.")
        se_methods.clear_spacy_model_cache()
        semantic_chunker.SemanticChunker()

        assert len(calls) == 2
        assert all("disable" not in kwargs for kwargs in calls), (
            "neither caller should request a partial pipeline"
        )   

    def test_missing_model_falls_back_without_poisoning_cache(self, monkeypatch):
        attempts = []

        def failing_load(name, **_kwargs):
            attempts.append(name)
            raise OSError(f"Can't find model '{name}'")

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(failing_load))

        # split_by_sentences should fall back to regex splitting, not raise
        chunks = split_methods.split_by_sentences("Hello world. Bye world.")
        assert chunks, "fallback splitting should still produce chunks"

        # SemanticChunker should leave .nlp as None rather than propagate
        chunker = semantic_chunker.SemanticChunker()
        assert chunker.nlp is None

        assert len(attempts) == 2, "a failed load must not be cached"

        # Once the model is available, both callers should now get it, and
        # share a single successful load.
        def working_load(name, **_kwargs):
            attempts.append(name)
            return _nlp_mock()

        monkeypatch.setattr(se_methods, "spacy", _fake_spacy(working_load))

        chunker2 = semantic_chunker.SemanticChunker()
        split_methods.split_by_sentences("One more sentence.")

        assert len(attempts) == 3, (
            "the model should load once after it becomes available"
        )
        assert chunker2.nlp is not None


if __name__ == "__main__":
    pytest.main([__file__])
