"""
tests/test_plecs_client.py
--------------------------
PlecsClient 单元测试（使用 Mock 模拟 XML-RPC，无需真实 PLECS 实例）。
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from plecs_client import PlecsClient, PlecsConnectionError, PlecsRPCError
import xmlrpc.client


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def mock_proxy():
    """返回一个模拟 XML-RPC proxy 对象。"""
    proxy = MagicMock()
    proxy.plecs.get.return_value = "4.7.0"
    return proxy


@pytest.fixture
def connected_client(mock_proxy):
    """返回一个已连接的 PlecsClient（注入 mock proxy）。"""
    client = PlecsClient(host="localhost", port=1080)
    client._proxy = mock_proxy
    return client


# ── 连接测试 ────────────────────────────────────────────────────────────

class TestConnection:

    def test_connect_success(self, mock_proxy):
        """连接成功时返回 True 并保存 proxy。"""
        client = PlecsClient()
        with patch("xmlrpc.client.ServerProxy", return_value=mock_proxy):
            result = client.connect()
        assert result is True
        assert client._proxy is not None

    def test_connect_refused(self):
        """连接被拒绝时返回 False，不抛异常。"""
        client = PlecsClient()
        with patch(
            "xmlrpc.client.ServerProxy",
            side_effect=ConnectionRefusedError("refused"),
        ):
            result = client.connect()
        assert result is False
        assert client._proxy is None

    def test_proxy_raises_when_not_connected(self):
        """未连接时访问 proxy 属性应抛出 PlecsConnectionError。"""
        client = PlecsClient()
        with pytest.raises(PlecsConnectionError, match="未连接"):
            _ = client.proxy

    def test_disconnect_clears_proxy(self, connected_client):
        connected_client.disconnect()
        assert connected_client._proxy is None


# ── 模型操作测试 ─────────────────────────────────────────────────────────

class TestModelOperations:

    def test_load_model(self, connected_client, mock_proxy):
        mock_proxy.plecs.load.return_value = "BuckConverter"
        name = connected_client.load_model("C:/models/buck.plecs")
        assert name == "BuckConverter"
        mock_proxy.plecs.load.assert_called_once_with("C:/models/buck.plecs")

    def test_load_model_fallback_name(self, connected_client, mock_proxy):
        """当 plecs.load 返回空时，从文件路径提取模型名。"""
        mock_proxy.plecs.load.return_value = ""
        name = connected_client.load_model("C:/models/boost_converter.plecs")
        assert name == "boost_converter"

    def test_save_model(self, connected_client, mock_proxy):
        connected_client.save_model("BuckConverter")
        mock_proxy.plecs.save.assert_called_once_with("BuckConverter")

    def test_close_model(self, connected_client, mock_proxy):
        connected_client.close_model("BuckConverter")
        mock_proxy.plecs.close.assert_called_once_with("BuckConverter")


# ── 参数读写测试 ─────────────────────────────────────────────────────────

class TestParameters:

    def test_get_param(self, connected_client, mock_proxy):
        mock_proxy.plecs.get.return_value = "47e-6"
        val = connected_client.get_param("BuckConverter/L1", "L")
        assert val == "47e-6"

    def test_set_param(self, connected_client, mock_proxy):
        connected_client.set_param("BuckConverter/L1", "L", "100e-6")
        mock_proxy.plecs.set.assert_called_once_with(
            "BuckConverter/L1", "L", "100e-6"
        )

    def test_get_param_rpc_error(self, connected_client, mock_proxy):
        """XML-RPC Fault 应被转换为 PlecsRPCError。"""
        mock_proxy.plecs.get.side_effect = xmlrpc.client.Fault(
            -1, "Unknown component"
        )
        with pytest.raises(PlecsRPCError, match="Unknown component"):
            connected_client.get_param("BuckConverter/NonExistent", "R")


# ── 仿真测试 ────────────────────────────────────────────────────────────

class TestSimulation:

    def test_simulate_basic(self, connected_client, mock_proxy):
        """基本仿真调用，验证参数传递正确。"""
        mock_proxy.plecs.simulate.return_value = {
            "Time":   [0.0, 1e-6, 2e-6],
            "Values": [[48.0, 47.9, 48.1]],
        }
        result = connected_client.simulate("BuckConverter")
        assert "Time" in result
        assert len(result["Time"]) == 3
        mock_proxy.plecs.simulate.assert_called_once_with("BuckConverter", {})

    def test_simulate_with_model_vars(self, connected_client, mock_proxy):
        """验证 ModelVars 字典被正确包装并传递。"""
        mock_proxy.plecs.simulate.return_value = {"Time": [], "Values": []}
        connected_client.simulate(
            "BuckConverter",
            model_vars={"Vin": 48, "R_load": 10},
        )
        call_args = mock_proxy.plecs.simulate.call_args
        opts = call_args[0][1]
        assert opts["ModelVars"]["Vin"] == 48
        assert opts["ModelVars"]["R_load"] == 10

    def test_simulate_with_solver_opts(self, connected_client, mock_proxy):
        """验证 StopTime 等求解器选项被直接合并到 opts 中。"""
        mock_proxy.plecs.simulate.return_value = {}
        connected_client.simulate(
            "BuckConverter",
            solver_opts={"StopTime": 0.01, "MaxStep": 1e-6},
        )
        call_args  = mock_proxy.plecs.simulate.call_args
        opts = call_args[0][1]
        assert opts["StopTime"] == 0.01
        assert opts["MaxStep"] == 1e-6

    def test_simulate_returns_empty_on_none(self, connected_client, mock_proxy):
        """plecs.simulate 返回 None 时应返回空 dict 而非崩溃。"""
        mock_proxy.plecs.simulate.return_value = None
        result = connected_client.simulate("BuckConverter")
        assert result == {}


# ── AC Sweep 测试 ────────────────────────────────────────────────────────

class TestAnalysis:

    def test_ac_sweep(self, connected_client, mock_proxy):
        mock_proxy.plecs.analyze.return_value = {
            "Frequency": [10, 100, 1000],
            "Magnitude": [20.0, 10.0, -3.0],
            "Phase":     [-10.0, -45.0, -135.0],
        }
        result = connected_client.analyze(
            "BuckConverter",
            "ACSweep",
            {"FreqRange": [10, 100e3], "NumPoints": 50},
        )
        assert "Frequency" in result
        assert len(result["Frequency"]) == 3

    def test_analyze_returns_empty_on_none(self, connected_client, mock_proxy):
        mock_proxy.plecs.analyze.return_value = None
        result = connected_client.analyze("BuckConverter", "ACSweep", {})
        assert result == {}


# ── Scope 操作测试 ───────────────────────────────────────────────────────

class TestScope:

    def test_scope_clear(self, connected_client, mock_proxy):
        connected_client.scope_clear("BuckConverter/Scope")
        mock_proxy.plecs.scope.assert_called_with(
            "BuckConverter/Scope", "ClearTraces"
        )

    def test_scope_hold_trace(self, connected_client, mock_proxy):
        connected_client.scope_hold_trace("BuckConverter/Scope", "R=10")
        mock_proxy.plecs.scope.assert_called_with(
            "BuckConverter/Scope", "HoldTrace", "R=10"
        )

    def test_scope_export_csv(self, connected_client, mock_proxy):
        connected_client.scope_export_csv(
            "BuckConverter/Scope", "C:/results/out.csv"
        )
        mock_proxy.plecs.scope.assert_called_with(
            "BuckConverter/Scope", "ExportCSV", "C:/results/out.csv"
        )
