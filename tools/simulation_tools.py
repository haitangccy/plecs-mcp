"""Simulation tools for PLECS MCP."""

from __future__ import annotations

import csv
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from tools.context import plecs_context
from tools.formatting import format_sim_result, parse_json_array, parse_json_object


def _solver_opts(stop_time: float | None, max_step: float | None) -> dict[str, Any]:
    opts: dict[str, Any] = {}
    if stop_time is not None:
        opts["StopTime"] = stop_time
    if max_step is not None:
        opts["MaxStep"] = max_step
    return opts


def register_simulation_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def plecs_run_simulation(
        model_name: str,
        model_vars: str = "{}",
        stop_time: float | None = None,
        max_step: float | None = None,
    ) -> str:
        """Run a PLECS time-domain simulation and return a result summary."""

        client = plecs_context.require_client()
        vars_dict = parse_json_object(model_vars, "model_vars")
        result = client.simulate(model_name, vars_dict, _solver_opts(stop_time, max_step))
        return format_sim_result(result)

    @mcp.tool()
    def plecs_parameter_sweep(
        model_name: str,
        sweep_var: str,
        values: str,
        base_model_vars: str = "{}",
        stop_time: float | None = None,
        max_step: float | None = None,
        output_csv: str | None = None,
    ) -> str:
        """Sweep one model variable across multiple simulation runs."""

        client = plecs_context.require_client()
        sweep_values = parse_json_array(values, "values")
        base_vars = parse_json_object(base_model_vars, "base_model_vars")
        solver = _solver_opts(stop_time, max_step)
        rows: list[dict[str, Any]] = []
        lines = [f"Parameter sweep completed: {sweep_var} over {sweep_values}"]

        for value in sweep_values:
            run_vars = dict(base_vars)
            run_vars[sweep_var] = value
            result = client.simulate(model_name, run_vars, solver)
            summary = format_sim_result(result)
            rows.append({"value": value, "summary": summary})
            lines.append(f"\n{sweep_var}={value}\n{summary}")

        if output_csv:
            abs_path = os.path.abspath(os.path.expanduser(output_csv))
            os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
            with open(abs_path, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=["value", "summary"])
                writer.writeheader()
                writer.writerows(rows)
            lines.append(f"\nCSV summary written to: {abs_path}")

        return "\n".join(lines)
