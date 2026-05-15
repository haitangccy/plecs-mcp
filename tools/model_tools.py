"""Model lifecycle and parameter tools."""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from tools.context import plecs_context, stringify


def register_model_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def plecs_connect(
        host: str = "localhost",
        port: int = 1080,
        timeout: float = 300.0,
    ) -> str:
        """Connect to a running PLECS Standalone XML-RPC server."""

        version = plecs_context.connect(host=host, port=port, timeout=timeout)
        return f"Connected to PLECS {version} at {host}:{port}."

    @mcp.tool()
    def plecs_status() -> str:
        """Check whether the MCP server can reach PLECS."""

        client = plecs_context.require_client()
        version = client.get_version()
        return f"PLECS connection is healthy. Version: {version}."

    @mcp.tool()
    def plecs_load_model(model_path: str) -> str:
        """Open a .plecs model file in PLECS Standalone."""

        client = plecs_context.require_client()
        abs_path = os.path.abspath(os.path.expanduser(model_path))
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Model file not found: {abs_path}")
        model_name = client.load_model(abs_path)
        return f"Model loaded: {model_name}\nPath: {abs_path}"

    @mcp.tool()
    def plecs_get_param(component_path: str, parameter: str) -> str:
        """Read a model or component parameter."""

        client = plecs_context.require_client()
        value: Any = client.get_param(component_path, parameter)
        return f"{component_path}.{parameter} = {stringify(value)}"

    @mcp.tool()
    def plecs_set_param(component_path: str, parameter: str, value: str) -> str:
        """Set a model or component parameter.

        Pass values as strings when using PLECS expressions, or as JSON literals for
        numbers, arrays, and booleans if the parameter accepts those types.
        """

        client = plecs_context.require_client()
        client.set_param(component_path, parameter, value)
        return f"Set {component_path}.{parameter} = {value}"

    @mcp.tool()
    def plecs_save_model(model_name: str) -> str:
        """Save an open PLECS model."""

        client = plecs_context.require_client()
        client.save_model(model_name)
        return f"Model saved: {model_name}"

    @mcp.tool()
    def plecs_close_model(model_name: str) -> str:
        """Close an open PLECS model."""

        client = plecs_context.require_client()
        client.close_model(model_name)
        return f"Model closed: {model_name}"
