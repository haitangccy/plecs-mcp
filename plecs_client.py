"""Small XML-RPC client wrapper for PLECS Standalone."""

from __future__ import annotations

import socket
import xmlrpc.client
from dataclasses import dataclass
from typing import Any


class TimeoutTransport(xmlrpc.client.Transport):
    """XML-RPC transport that applies a socket timeout to HTTP calls."""

    def __init__(self, timeout: float) -> None:
        super().__init__()
        self.timeout = timeout

    def make_connection(self, host: str):  # type: ignore[no-untyped-def]
        connection = super().make_connection(host)
        connection.timeout = self.timeout
        return connection


@dataclass(slots=True)
class PlecsConnectionInfo:
    host: str = "localhost"
    port: int = 1080
    timeout: float = 300.0

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/RPC2"


class PlecsClient:
    """PLECS Standalone XML-RPC client.

    The PLECS XML-RPC server must be enabled in PLECS Standalone preferences.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1080,
        timeout: float = 300.0,
    ) -> None:
        self.info = PlecsConnectionInfo(host=host, port=port, timeout=timeout)
        self._proxy: xmlrpc.client.ServerProxy | None = None

    @property
    def proxy(self) -> xmlrpc.client.ServerProxy:
        if self._proxy is None:
            raise RuntimeError("Not connected to PLECS. Call plecs_connect first.")
        return self._proxy

    def connect(self) -> str:
        """Connect to PLECS and return its version string."""

        transport = TimeoutTransport(timeout=self.info.timeout)
        proxy = xmlrpc.client.ServerProxy(
            self.info.url,
            allow_none=True,
            transport=transport,
        )
        try:
            version = proxy.plecs.get("", "Version")
        except (OSError, socket.timeout, xmlrpc.client.Error) as exc:
            raise ConnectionError(
                f"Could not connect to PLECS XML-RPC server at {self.info.url}: {exc}"
            ) from exc
        self._proxy = proxy
        return str(version)

    def is_connected(self) -> bool:
        if self._proxy is None:
            return False
        try:
            self.get_param("", "Version")
        except Exception:
            return False
        return True

    def get_version(self) -> str:
        return str(self.get_param("", "Version"))

    def load_model(self, path: str) -> str:
        return str(self.proxy.plecs.load(path))

    def simulate(
        self,
        model_name: str,
        model_vars: dict[str, Any] | None = None,
        solver_opts: dict[str, Any] | None = None,
    ) -> Any:
        opts: dict[str, Any] = {}
        if model_vars:
            opts["ModelVars"] = model_vars
        if solver_opts:
            opts["SolverOpts"] = solver_opts
        return self.proxy.plecs.simulate(model_name, opts)

    def get_param(self, component_path: str, parameter: str) -> Any:
        return self.proxy.plecs.get(component_path, parameter)

    def set_param(self, component_path: str, parameter: str, value: Any) -> None:
        self.proxy.plecs.set(component_path, parameter, value)

    def save_model(self, model_name: str) -> None:
        self.proxy.plecs.save(model_name)

    def close_model(self, model_name: str) -> None:
        self.proxy.plecs.close(model_name)

    def scope(self, scope_path: str, command: str, *args: Any) -> Any:
        return self.proxy.plecs.scope(scope_path, command, *args)

    def export_scope_csv(self, scope_path: str, output_path: str) -> None:
        self.scope(scope_path, "ExportCSV", output_path)

    def analyze(self, model_name: str, analysis_type: str, opts: dict[str, Any]) -> Any:
        return self.proxy.plecs.analyze(model_name, analysis_type, opts)
