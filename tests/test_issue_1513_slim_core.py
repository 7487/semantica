from pathlib import Path
from unittest.mock import patch
import pytest
try:
    import tomllib
except ImportError:
    import toml as tomllib

from semantica.parse.docx_parser import DOCXParser
from semantica.parse.excel_parser import ExcelParser
from semantica.parse.html_parser import HTMLParser
from semantica.parse.xml_parser import XMLParser
from semantica.utils.exceptions import ProcessingError


def test_core_dependencies_count():
    """pyproject.toml must contain exactly 22 unique core dependencies."""
    repo_root = Path(__file__).resolve().parents[1]
    with open(repo_root / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    deps = data["project"]["dependencies"]
    normalized_names = {
        d.split(";")[0].split(">=")[0].split("<")[0].split("==")[0].strip()
        for d in deps
    }
    expected_22 = {
        "numpy", "pandas", "scipy", "scikit-learn", "rdflib", "networkx",
        "requests", "chardet", "protobuf", "grpcio", "pillow", "pydantic",
        "click", "rich", "tqdm", "pyyaml", "toml", "python-dotenv",
        "loguru", "structlog", "httpx", "pyarrow"
    }
    assert normalized_names == expected_22
    assert len(normalized_names) == 22


def test_optional_extras_defined():
    """All required optional extras must be declared in pyproject.toml."""
    repo_root = Path(__file__).resolve().parents[1]
    with open(repo_root / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    extras = data["project"]["optional-dependencies"]
    for extra in [
        "documents", "ingest-git", "embeddings-local", "nlp-spacy",
        "viz", "media", "vectorstore-faiss", "graph-embeddings", "all"
    ]:
        assert extra in extras, f"Missing extra {extra}"
    all_extra_str = str(extras["all"])
    for expected_ref in [
        "documents", "ingest-git", "embeddings-local", "nlp-spacy",
        "viz", "media", "graph-embeddings", "vectorstore-all"
    ]:
        assert expected_ref in all_extra_str, f"Missing {expected_ref} in all"
    # And vectorstore-faiss is in vectorstore-all
    assert "vectorstore-faiss" in str(extras["vectorstore-all"])


def test_docx_parser_lazy_construction_and_parse_hint():
    with patch("semantica.parse.docx_parser.Document", None):
        parser = DOCXParser()
        assert parser is not None
        with pytest.raises(ProcessingError, match=r"semantica\[documents\]"):
            parser.parse("nonexistent.docx")


def test_excel_parser_lazy_construction_and_parse_hint():
    with patch("semantica.parse.excel_parser.load_workbook", None):
        parser = ExcelParser()
        assert parser is not None
        with pytest.raises(ProcessingError, match=r"semantica\[documents\]"):
            parser.parse("nonexistent.xlsx")


def test_html_parser_lazy_construction_and_parse_hint():
    with patch("semantica.parse.html_parser.BeautifulSoup", None):
        parser = HTMLParser()
        assert parser is not None
        with pytest.raises(ProcessingError, match=r"semantica\[documents\]"):
            parser.parse("nonexistent.html")


def test_xml_parser_etree_fallback():
    with patch("semantica.parse.xml_parser.etree", None):
        parser = XMLParser()
        assert parser is not None
        result = parser.parse("<root><item id='1'>Test</item></root>")
        assert result is not None
        assert result.root is not None
        assert result.root.tag == "root"


def test_xml_parser_lxml_explicit_requires_documents_extra():
    with patch("semantica.parse.xml_parser.etree", None):
        parser = XMLParser(engine="lxml")
        assert parser is not None
        with pytest.raises(ProcessingError, match=r"semantica\[documents\]"):
            parser.parse("<root/>")


def test_node_embedder_gensim_missing_hint():
    with patch("semantica.kg.node_embeddings.GENSIM_AVAILABLE", False):
        from semantica.kg.node_embeddings import NodeEmbedder
        with pytest.raises(ImportError, match=r"semantica\[graph-embeddings\]"):
            NodeEmbedder()


def test_faiss_store_missing_hint():
    with patch("semantica.vector_store.faiss_store.FAISS_AVAILABLE", False):
        from semantica.vector_store.faiss_store import FAISSIndexBuilder, FAISSStore
        builder = FAISSIndexBuilder(128)
        with pytest.raises(ProcessingError, match=r"semantica\[vectorstore-faiss\]"):
            builder.build_index("flat")
        store = FAISSStore(128)
        with pytest.raises(ProcessingError, match=r"semantica\[vectorstore-faiss\]"):
            store.load_index("nonexistent.faiss")


def test_visualization_missing_hint():
    import numpy as np
    from semantica.visualization.embedding_visualizer import EmbeddingVisualizer
    with patch("semantica.visualization.embedding_visualizer.plt", None):
        visualizer = EmbeddingVisualizer()
        with pytest.raises(ProcessingError, match=r"semantica\[viz\]"):
            visualizer.visualize_2d_projection(np.array([[0.1, 0.2], [0.3, 0.4]]), output="png")


def test_spacy_load_missing_hint():
    from semantica.semantic_extract.methods import load_spacy_model
    with patch("semantica.semantic_extract.methods.spacy", None):
        with pytest.raises(ImportError, match=r"semantica\[nlp-spacy\]"):
            load_spacy_model("en_core_web_sm")
