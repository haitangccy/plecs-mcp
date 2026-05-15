"""PLECS MCP server entry point."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from tools.analysis_tools import register_analysis_tools
from tools.data_tools import register_data_tools
from tools.model_tools import register_model_tools
from tools.simulation_tools import register_simulation_tools


def create_server() -> FastMCP:
    mcp = FastMCP("PLECS MCP Server")
    register_model_tools(mcp)
    register_simulation_tools(mcp)
    register_analysis_tools(mcp)
    register_data_tools(mcp)
    return mcp


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
