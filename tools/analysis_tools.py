"""Analysis tools for PLECS MCP."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from tools.context import plecs_context
from tools.formatting import format_ac_result, parse_json_object


def register_analysis_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def plecs_ac_sweep(
        model_name: str,
        analysis_name: str,
        f_start: float,
        f_stop: float,
        num_points: int = 50,
        amplitude: float = 1.0,
        extra_options: str = "{}",
    ) -> str:
        """Run an AC sweep analysis and return a Bode-data summary."""

        client = plecs_context.require_client()
        opts: dict[str, Any] = {
            "Name": analysis_name,
            "FreqRange": [f_start, f_stop],
            "NumPoints": num_points,
            "Amplitude": amplitude,
        }
        opts.update(parse_json_object(extra_options, "extra_options"))
        result = client.analyze(model_name, "ACSweep", opts)
        return format_ac_result(result)

    @mcp.tool()
    def plecs_analyze(model_name: str, analysis_type: str, options: str = "{}") -> str:
        """Run a generic PLECS analysis with JSON options."""

        client = plecs_context.require_client()
        opts = parse_json_object(options, "options")
        result = client.analyze(model_name, analysis_type, opts)
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)
