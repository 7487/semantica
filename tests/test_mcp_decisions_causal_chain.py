"""
Regression tests for Issue #781 — Causal chain error signaling & fallback parameter forwarding
in mcp/tools/decisions.py: handle_get_causal_chain.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from unittest.mock import MagicMock, patch
from mcp.tools.decisions import handle_get_causal_chain


class TestMCPDecisionsCausalChain(unittest.TestCase):
    """Test suite covering handle_get_causal_chain execution paths and error shapes."""

    def test_validation_error_missing_decision_id(self):
        """Verify validation error shape when decision_id is missing or empty."""
        response = handle_get_causal_chain({})
        self.assertEqual(
            response,
            {"error": "decision_id is required", "chain": []},
        )
        self.assertNotIn("count", response)
        self.assertNotIn("direction", response)

        response_empty = handle_get_causal_chain({"decision_id": "   "})
        self.assertEqual(
            response_empty,
            {"error": "decision_id is required", "chain": []},
        )

    @patch("mcp.tools.decisions.get_graph")
    def test_runtime_outer_exception_shape(self, mock_get_graph):
        """Verify outer exception handler returns standard error shape without count/direction."""
        mock_get_graph.side_effect = RuntimeError("database failure")
        response = handle_get_causal_chain({"decision_id": "dec_101"})
        self.assertEqual(
            response,
            {"error": "database failure", "chain": []},
        )
        self.assertNotIn("count", response)
        self.assertNotIn("direction", response)

    @patch("mcp.tools.decisions.get_graph")
    @patch("semantica.context.causal_analyzer.CausalChainAnalyzer")
    def test_unsupported_backend_returns_error(self, mock_analyzer_cls, mock_get_graph):
        """
        Issue #781 regression test:
        Verify that when CausalChainAnalyzer fails to load and graph lacks get_causal_chain,
        an explicit error dictionary is returned rather than a silent empty list.
        """
        mock_analyzer_cls.side_effect = ImportError("mocked import error")
        # Graph object without get_causal_chain attribute
        mock_graph = object()
        mock_get_graph.return_value = mock_graph

        response = handle_get_causal_chain({"decision_id": "dec_202", "direction": "downstream"})
        self.assertEqual(
            response,
            {
                "error": "Causal chain analysis is not supported on this graph backend",
                "chain": [],
            },
        )
        self.assertNotIn("count", response)
        self.assertNotIn("direction", response)

    @patch("mcp.tools.decisions.get_graph")
    @patch("semantica.context.causal_analyzer.CausalChainAnalyzer")
    def test_fallback_path_forwards_direction_and_max_depth(self, mock_analyzer_cls, mock_get_graph):
        """Verify fallback graph.get_causal_chain receives direction and max_depth keyword arguments."""
        mock_analyzer_cls.side_effect = ImportError("mocked import error")
        mock_graph = MagicMock()
        mock_graph.get_causal_chain.return_value = ["node_a", "node_b"]
        mock_get_graph.return_value = mock_graph

        response = handle_get_causal_chain(
            {"decision_id": "dec_303", "direction": "upstream", "max_depth": 7}
        )
        mock_graph.get_causal_chain.assert_called_once_with(
            "dec_303",
            direction="upstream",
            max_depth=7,
        )
        self.assertNotIn("error", response)
        self.assertEqual(
            response,
            {"chain": ["node_a", "node_b"], "count": 2, "direction": "upstream"},
        )

    @patch("mcp.tools.decisions.get_graph")
    @patch("semantica.context.causal_analyzer.CausalChainAnalyzer")
    def test_fallback_success_response(self, mock_analyzer_cls, mock_get_graph):
        """Verify fallback graph.get_causal_chain default parameters and success response shape."""
        mock_analyzer_cls.side_effect = AttributeError("mocked attr error")
        mock_graph = MagicMock()
        mock_graph.get_causal_chain.return_value = ["node_default"]
        mock_get_graph.return_value = mock_graph

        response = handle_get_causal_chain({"decision_id": "dec_404"})
        mock_graph.get_causal_chain.assert_called_once_with(
            "dec_404",
            direction="downstream",
            max_depth=5,
        )
        self.assertNotIn("error", response)
        self.assertEqual(
            response,
            {"chain": ["node_default"], "count": 1, "direction": "downstream"},
        )

    @patch("mcp.tools.decisions.get_graph")
    @patch("semantica.context.causal_analyzer.CausalChainAnalyzer")
    def test_primary_analyzer_success_path(self, mock_analyzer_cls, mock_get_graph):
        """Verify normal operation via CausalChainAnalyzer when available."""
        mock_analyzer_instance = MagicMock()
        mock_analyzer_instance.get_causal_chain.return_value = ["dec_down_1", "dec_down_2"]
        mock_analyzer_cls.return_value = mock_analyzer_instance
        mock_graph = MagicMock()
        mock_get_graph.return_value = mock_graph

        response = handle_get_causal_chain(
            {"decision_id": "dec_505", "direction": "downstream", "max_depth": 4}
        )
        mock_analyzer_cls.assert_called_once_with(graph_store=mock_graph)
        mock_analyzer_instance.get_causal_chain.assert_called_once_with(
            "dec_505",
            direction="downstream",
            max_depth=4,
        )
        self.assertNotIn("error", response)
        self.assertEqual(
            response,
            {"chain": ["dec_down_1", "dec_down_2"], "count": 2, "direction": "downstream"},
        )


if __name__ == "__main__":
    unittest.main()
