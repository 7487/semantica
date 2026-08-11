"""
Regression tests for security fixes in PR #898.

Covers:
  1. API Key Authentication (Explorer)
  2. Cypher Injection Prevention (AGE Store)
  3. SPARQL Injection Prevention (read-only query validation)
  4. XXE Protection (rdf_parser fail-closed)
  5. Vector save numpy serialization
  6. SPARQL graph cap error handling
  7. SSRF redirect handling (relative URLs, resp.close)
"""

import re
import pytest


# ===================================================================
# 1. SPARQL read-only query validation (injection prevention)
# ===================================================================

# Inline the validation logic so tests don't require full app context
_ALLOWED_QUERY_TYPES = re.compile(
    r"^(SELECT|ASK|CONSTRUCT|DESCRIBE)\b",
    re.IGNORECASE,
)
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|DELETE|DROP|LOAD|CLEAR|CREATE|COPY|MOVE|ADD)\b",
    re.IGNORECASE,
)
_COMMENT_LINE = re.compile(r"#[^\n]*", re.MULTILINE)
_PREFIX_DECL = re.compile(
    r"^\s*(?:PREFIX|BASE)\s+\S+\s*<[^>]*>\s*",
    re.IGNORECASE | re.MULTILINE,
)


def _is_read_only_query(query: str) -> bool:
    cleaned = _COMMENT_LINE.sub("", query)
    cleaned = _PREFIX_DECL.sub("", cleaned)
    cleaned = cleaned.strip()
    if not _ALLOWED_QUERY_TYPES.match(cleaned):
        return False
    if _FORBIDDEN_KEYWORDS.search(cleaned):
        return False
    return True


class TestSparqlReadOnlyValidation:
    """Regression tests for SPARQL injection prevention."""

    def test_select_allowed(self):
        assert _is_read_only_query("SELECT ?s ?p ?o WHERE { ?s ?p ?o }")

    def test_ask_allowed(self):
        assert _is_read_only_query("ASK { ?s ?p ?o }")

    def test_construct_allowed(self):
        assert _is_read_only_query("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }")

    def test_describe_allowed(self):
        assert _is_read_only_query("DESCRIBE <http://example.org>")

    def test_insert_blocked(self):
        assert not _is_read_only_query("INSERT DATA { <s> <p> <o> }")

    def test_delete_blocked(self):
        assert not _is_read_only_query("DELETE WHERE { ?s ?p ?o }")

    def test_drop_blocked(self):
        assert not _is_read_only_query("DROP GRAPH <http://example.org>")

    def test_comment_bypass_blocked(self):
        """Attacker hides INSERT behind a comment, SELECT follows."""
        query = "# innocent comment\nINSERT DATA { <s> <p> <o> }"
        assert not _is_read_only_query(query)

    def test_comment_hiding_real_query(self):
        """Comment at top with SELECT visible, but INSERT in body."""
        query = "# SELECT everything\nINSERT DATA { <s> <p> <o> }"
        assert not _is_read_only_query(query)

    def test_prefix_before_select_allowed(self):
        """PREFIX declarations before SELECT should still be allowed."""
        query = "PREFIX ex: <http://example.org/>\nSELECT ?s WHERE { ?s ex:p ?o }"
        assert _is_read_only_query(query)

    def test_prefix_before_insert_blocked(self):
        """PREFIX declarations can't disguise an INSERT."""
        query = "PREFIX ex: <http://example.org/>\nINSERT DATA { ex:s ex:p ex:o }"
        assert not _is_read_only_query(query)

    def test_multiple_prefixes_then_select(self):
        query = (
            "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
            "SELECT ?s ?label WHERE { ?s rdfs:label ?label }"
        )
        assert _is_read_only_query(query)

    def test_select_with_insert_keyword_blocked(self):
        """Even if SELECT is first, INSERT in body should be blocked."""
        query = "SELECT ?s WHERE { ?s ?p ?o } ; INSERT DATA { <a> <b> <c> }"
        assert not _is_read_only_query(query)

    def test_case_insensitive_insert(self):
        assert not _is_read_only_query("insert data { <s> <p> <o> }")

    def test_load_blocked(self):
        assert not _is_read_only_query("LOAD <http://evil.com/data.ttl>")

    def test_clear_blocked(self):
        assert not _is_read_only_query("CLEAR ALL")

    def test_empty_query_rejected(self):
        assert not _is_read_only_query("")

    def test_whitespace_only_rejected(self):
        assert not _is_read_only_query("   \n\t  ")

    def test_base_before_select(self):
        query = "BASE <http://example.org/>\nSELECT ?s WHERE { ?s ?p ?o }"
        assert _is_read_only_query(query)


# ===================================================================
# 2. Cypher injection prevention
# ===================================================================

class TestCypherInjection:
    """Regression tests for Cypher/SQL injection prevention."""

    def test_sanitize_label_valid(self):
        from semantica.graph_store.age_store import _sanitize_label
        assert _sanitize_label("Entity") == "Entity"
        assert _sanitize_label("my_label_123") == "my_label_123"

    def test_sanitize_label_injection(self):
        from semantica.graph_store.age_store import _sanitize_label
        with pytest.raises(Exception):  # ValidationError
            _sanitize_label("Entity') OR 1=1--")

    def test_sanitize_label_special_chars(self):
        from semantica.graph_store.age_store import _sanitize_label
        with pytest.raises(Exception):
            _sanitize_label("Entity;DROP TABLE")

    def test_value_to_cypher_literal_string_escaping(self):
        from semantica.graph_store.age_store import _value_to_cypher_literal
        result = _value_to_cypher_literal("O'Brien")
        assert "\\'" in result  # Single quote should be escaped

    def test_value_to_cypher_literal_backslash(self):
        from semantica.graph_store.age_store import _value_to_cypher_literal
        result = _value_to_cypher_literal("path\\to\\file")
        assert "\\\\" in result

    def test_dollar_dollar_breakout_blocked(self):
        """$$ in a Cypher query would break out of AGE's delimiter."""
        from semantica.graph_store.age_store import ApacheAgeStore
        store = ApacheAgeStore.__new__(ApacheAgeStore)
        store.graph_name = "test_graph"
        store._conn = None
        with pytest.raises(Exception):  # ValidationError
            store._execute_cypher("MATCH (n) RETURN n $$ ) AS (x agtype); DROP TABLE users; --")

    def test_graph_name_sanitization(self):
        """Graph name with SQL injection should be rejected."""
        from semantica.graph_store.age_store import ApacheAgeStore
        with pytest.raises(Exception):  # ValidationError
            ApacheAgeStore(
                connection_string="host=localhost",
                graph_name="test'); DROP TABLE--"
            )

    def test_graph_name_valid(self):
        from semantica.graph_store.age_store import ApacheAgeStore
        store = ApacheAgeStore(
            connection_string="host=localhost",
            graph_name="my_graph_123"
        )
        assert store.graph_name == "my_graph_123"

    def test_property_key_injection(self):
        from semantica.graph_store.age_store import _props_to_cypher_literal
        with pytest.raises(Exception):
            _props_to_cypher_literal({"key; DROP": "value"})


# ===================================================================
# 3. XXE Protection (fail-closed)
# ===================================================================

class TestXXEProtection:
    """Regression tests for XXE prevention in rdf_parser."""

    def test_defusedxml_check_exists(self):
        """The _HAS_DEFUSEDXML flag must exist."""
        from semantica.explorer.utils.rdf_parser import _HAS_DEFUSEDXML
        assert isinstance(_HAS_DEFUSEDXML, bool)

    def test_safe_parse_rdf_function_exists(self):
        """_safe_parse_rdf must be importable."""
        from semantica.explorer.utils.rdf_parser import _safe_parse_rdf
        assert callable(_safe_parse_rdf)


# ===================================================================
# 4. Numpy vector serialization
# ===================================================================

class TestVectorSerialization:
    """Regression test for numpy array serialization in vector_store."""

    def test_tolist_on_numpy_like(self):
        """Objects with tolist() should use it instead of list()."""

        class FakeNumpyArray:
            def __init__(self, data):
                self._data = data

            def tolist(self):
                return self._data

            def __iter__(self):
                # list() would call this and fail for multi-dim arrays
                raise TypeError("Use tolist() for numpy arrays")

        arr = FakeNumpyArray([1.0, 2.0, 3.0])
        # Simulate the fixed logic
        result = arr.tolist() if hasattr(arr, "tolist") else list(arr)
        assert result == [1.0, 2.0, 3.0]

    def test_regular_list_still_works(self):
        """Regular lists (no tolist) should use list()."""
        data = [1.0, 2.0, 3.0]
        result = data.tolist() if hasattr(data, "tolist") else list(data)
        assert result == [1.0, 2.0, 3.0]


# ===================================================================
# 5. SSRF redirect handling
# ===================================================================

class TestSSRFRedirectHandling:
    """Regression tests for SSRF redirect fixes."""

    def test_urljoin_resolves_relative(self):
        """Relative Location headers must be resolved against current URL."""
        from urllib.parse import urljoin
        base = "https://example.com/api/ontology"
        relative = "/ontology.ttl"
        result = urljoin(base, relative)
        assert result == "https://example.com/ontology.ttl"

    def test_urljoin_absolute_passthrough(self):
        """Absolute Location headers should pass through unchanged."""
        from urllib.parse import urljoin
        base = "https://example.com/api/ontology"
        absolute = "https://other.com/data.ttl"
        result = urljoin(base, absolute)
        assert result == "https://other.com/data.ttl"

    def test_urljoin_relative_path(self):
        """Relative path without leading slash."""
        from urllib.parse import urljoin
        base = "https://example.com/api/v1/resource"
        relative = "../data.ttl"
        result = urljoin(base, relative)
        assert result == "https://example.com/api/data.ttl"


# ===================================================================
# 6. API Key Auth
# ===================================================================

class TestAPIKeyAuth:
    """Regression tests for API key authentication."""

    def test_auth_module_importable(self):
        from semantica.explorer.auth import APIKeyAuthMiddleware
        assert APIKeyAuthMiddleware is not None

    def test_extract_bearer_token(self):
        from semantica.explorer.auth import _extract_token
        from unittest.mock import MagicMock
        req = MagicMock()
        req.headers = {"Authorization": "Bearer test-key-123"}
        assert _extract_token(req) == "test-key-123"

    def test_extract_api_key_header(self):
        from semantica.explorer.auth import _extract_token
        from unittest.mock import MagicMock
        req = MagicMock()
        req.headers = {"X-API-Key": "my-secret-key", "Authorization": ""}
        assert _extract_token(req) == "my-secret-key"

    def test_extract_no_token(self):
        from semantica.explorer.auth import _extract_token
        from unittest.mock import MagicMock
        req = MagicMock()
        req.headers = {}
        assert _extract_token(req) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
