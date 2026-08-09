"""Regression tests for MCP server version reporting."""

import unittest
from importlib.metadata import PackageNotFoundError, version

import semantica
from semantica import mcp_server


class TestMCPServerVersion(unittest.TestCase):
    def test_server_info_uses_distribution_version(self):
        try:
            expected = version("semantica")
        except PackageNotFoundError:
            expected = semantica.__version__

        self.assertEqual(mcp_server.SERVER_INFO["version"], expected)

    def test_initialize_reports_package_version(self):
        response = mcp_server._handle(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        )

        self.assertIsNotNone(response)
        self.assertEqual(
            response["result"]["serverInfo"]["version"], semantica.__version__
        )

    def test_schema_info_resource_reports_package_version(self):
        resource = mcp_server._read_resource("semantica://schema/info")

        self.assertEqual(resource["version"], semantica.__version__)


if __name__ == "__main__":
    unittest.main()
