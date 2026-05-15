"""Formatting helpers for MCP tool responses."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import Any


Number = int | float


def parse_json_object(raw: str, field_name: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must be a valid JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object.")
    return value


def parse_json_array(raw: str, field_name: str) -> list[Any]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must be a valid JSON array: {exc}") from exc
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a JSON array.")
    return value


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return []


def _numeric_stats(values: Sequence[Any]) -> tuple[float, float, float] | None:
    nums: list[float] = []
    for item in values:
        if isinstance(item, (int, float)) and math.isfinite(float(item)):
            nums.append(float(item))
    if not nums:
        return None
    return min(nums), max(nums), sum(nums) / len(nums)


def _values_channels(values: Any) -> list[Sequence[Any]]:
    if not isinstance(values, list):
        return []
    if not values:
        return []
    if all(isinstance(item, (int, float)) for item in values):
        return [values]
    channels: list[Sequence[Any]] = []
    for item in values:
        seq = _as_sequence(item)
        if seq:
            channels.append(seq)
    return channels


def format_sim_result(result: Any) -> str:
    """Format common PLECS simulate() return shapes into a concise summary."""

    if not isinstance(result, dict):
        return f"Simulation completed. Raw result: {compact_json(result)}"

    time = result.get("Time") or result.get("time") or []
    time_seq = _as_sequence(time)
    values = result.get("Values", result.get("values", []))
    channels = _values_channels(values)

    if not time_seq and not channels:
        return f"Simulation completed. Raw result: {compact_json(result)}"

    lines: list[str] = []
    if time_seq:
        lines.append(
            "Simulation completed: "
            f"t={float(time_seq[0]):.6g}s..{float(time_seq[-1]):.6g}s, "
            f"{len(time_seq)} samples"
        )
    else:
        lines.append("Simulation completed.")

    if not channels:
        lines.append("No output channels found. Check whether the model has output ports.")
        return "\n".join(lines)

    for idx, channel in enumerate(channels, start=1):
        stats = _numeric_stats(channel)
        if stats is None:
            lines.append(f"Output {idx}: {len(channel)} samples")
            continue
        mn, mx, avg = stats
        lines.append(f"Output {idx}: min={mn:.6g}, max={mx:.6g}, avg={avg:.6g}")
    return "\n".join(lines)


def format_ac_result(result: Any, preview_points: int = 5) -> str:
    if not isinstance(result, dict):
        return f"AC analysis completed. Raw result: {compact_json(result)}"

    freq = list(_as_sequence(result.get("Frequency") or result.get("frequency") or []))
    mag = list(_as_sequence(result.get("Magnitude") or result.get("magnitude") or []))
    phase = list(_as_sequence(result.get("Phase") or result.get("phase") or []))

    lines = [f"AC analysis completed: {len(freq)} frequency points"]
    mag_stats = _numeric_stats(mag)
    phase_stats = _numeric_stats(phase)
    if mag_stats:
        lines.append(f"Magnitude: {mag_stats[0]:.6g}..{mag_stats[1]:.6g} dB")
    if phase_stats:
        lines.append(f"Phase: {phase_stats[0]:.6g}..{phase_stats[1]:.6g} deg")

    if freq:
        lines.append("Preview:")
        count = min(preview_points, len(freq), len(mag) or len(freq), len(phase) or len(freq))
        for i in range(count):
            mag_text = f", {float(mag[i]):.6g} dB" if i < len(mag) else ""
            phase_text = f", {float(phase[i]):.6g} deg" if i < len(phase) else ""
            lines.append(f"  {float(freq[i]):.6g} Hz{mag_text}{phase_text}")

    return "\n".join(lines)
