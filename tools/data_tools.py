"""Data export tools for PLECS MCP."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from tools.context import plecs_context


def register_data_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def plecs_export_scope(scope_path: str, output_path: str) -> str:
        """Export waveform data from a PLECS Scope to CSV."""

        client = plecs_context.require_client()
        abs_path = os.path.abspath(os.path.expanduser(output_path))
        os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
        client.export_scope_csv(scope_path, abs_path)
        return f"Scope data exported to: {abs_path}"
