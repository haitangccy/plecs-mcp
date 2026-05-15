"""Shared server context for PLECS MCP tools."""

from __future__ import annotations

import os
from typing import Any

from plecs_client import PlecsClient


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


class PlecsContext:
    def __init__(self) -> None:
        self.client = PlecsClient(
            host=os.getenv("PLECS_HOST", "localhost"),
            port=_env_int("PLECS_PORT", 1080),
            timeout=_env_float("PLECS_TIMEOUT", 300.0),
        )
        self.version: str | None = None

    def connect(
        self,
        host: str = "localhost",
        port: int = 1080,
        timeout: float = 300.0,
    ) -> str:
        self.client = PlecsClient(host=host, port=port, timeout=timeout)
        self.version = self.client.connect()
        return self.version

    def require_client(self) -> PlecsClient:
        if not self.client.is_connected():
            raise RuntimeError(
                "PLECS is not connected. Call plecs_connect first and ensure "
                "PLECS Standalone has XML-RPC enabled."
            )
        return self.client


plecs_context = PlecsContext()


def stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return repr(value)
