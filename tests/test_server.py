"""
tests/test_server.py
--------------------
MCP tool 单元测试，按 RPC 接口一一对应验证。
用 stub 替代 mcp 包，用 Mock 替代真实 PLECS。
"""

import sys, os, types, json
from unittest.mock import MagicMock, patch
import pytest

# ── FastMCP stub ──────────────────────────────────────────────────────────

class _FakeFastMCP:
    def __init__(self, name="", **kw):
        self._tools = {}
    def tool(self):
        def deco(fn):
            self._tools[fn.__name__] = fn
            return fn
        return deco
    def run(self, **kw):
        pass

_mcp = types.ModuleType("mcp")
_srv = types.ModuleType("mcp.server")
_fmcp = types.ModuleType("mcp.server.fastmcp")
_fmcp.FastMCP = _FakeFastMCP
_mcp.server = _srv
_srv.fastmcp = _fmcp
sys.modules.setdefault("mcp", _mcp)
sys.modules.setdefault("mcp.server", _srv)
sys.modules.setdefault("mcp.server.fastmcp", _fmcp)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from plecs_client import PlecsClient, PlecsError

# ── 辅助：构建工具集 ──────────────────────────────────────────────────────

def _make_tools(mock_client):
    """注入 mock client，返回已注册工具字典。"""
    import server as srv_mod

    cfg = {"host": "localhost", "port": 1080}
    mcp = srv_mod.build_server(cfg)

    # 注入 mock
    # build_server 使用闭包，需通过调用 plecs_connect 来设置 client
    # 这里直接 monkey-patch _state
    # 找到工具的闭包里的 _state
    # 更简单：让 plecs_connect 成功后设置，或直接 patch PlecsClient
    return mcp._tools, cfg


@pytest.fixture
def mock_client():
    c = MagicMock(spec=PlecsClient)
    c.is_connected.return_value = True
    c.statistics.return_value = {
        "version": "4.7.4",
        "build": "4f3b445a 15.06.2023 16:17",
        "models": ["BuckConverter"],
    }
    c.load.return_value = "BuckConverter"
    c.get.return_value = "47e-6"
    c.simulate.return_value = {
        "Time":   list(range(100)),
        "Values": [
            [48.0 + i*0.01 for i in range(100)],
            [5.0  - i*0.001 for i in range(100)],
        ],
    }
    c.analyze.return_value = {
        "Frequencies": [10, 100, 1000, 10000, 100000],
        "Magnitude":   [20.0, 15.0, 5.0, -3.0, -20.0],
        "Phase":       [-10.0, -30.0, -90.0, -150.0, -175.0],
    }
    c.scope.return_value = None
    c.webserver.return_value = {"status": "running"}
    c.codegen.return_value = {"output": "C:/gen"}
    return c


@pytest.fixture
def tools(mock_client):
    """返回所有已注册 MCP 工具，内部 client 指向 mock_client。"""
    import server as srv_mod

    cfg = {"host": "localhost", "port": 1080}
    mock_client.connect.return_value = mock_client.statistics.return_value

    with patch("server.PlecsClient") as MockCls:
        MockCls.return_value = mock_client
        mcp = srv_mod.build_server(cfg)
        # patch 仍在生效范围内时调用 connect，client 会被正确注入
        mcp._tools["plecs_connect"]()

    return mcp._tools


# ── plecs_connect ─────────────────────────────────────────────────────────

class TestConnect:
    def test_success(self, mock_client):
        import server as srv_mod
        cfg = {"host": "localhost", "port": 1080}
        mock_client.connect.return_value = mock_client.statistics.return_value
        with patch("server.PlecsClient") as MockCls:
            MockCls.return_value = mock_client
            mcp = srv_mod.build_server(cfg)
            result = mcp._tools["plecs_connect"]()
        assert "✓" in result
        assert "4.7.4" in result
        assert "BuckConverter" in result

    def test_failure(self):
        import server as srv_mod
        cfg = {"host": "localhost", "port": 1080}
        with patch("server.PlecsClient") as MockCls:
            bad = MagicMock()
            bad.connect.side_effect = PlecsError("连接被拒")
            MockCls.return_value = bad
            mcp = srv_mod.build_server(cfg)
            result = mcp._tools["plecs_connect"]()
        assert "✗" in result
        assert "连接被拒" in result


# ── plecs_status ──────────────────────────────────────────────────────────

class TestStatus:
    def test_returns_version(self, tools, mock_client):
        result = tools["plecs_status"]()
        assert "4.7.4" in result
        assert "BuckConverter" in result
        mock_client.statistics.assert_called()


# ── plecs_load ────────────────────────────────────────────────────────────

class TestLoad:
    def test_success(self, tools, mock_client):
        result = tools["plecs_load"](path="C:/models/buck.plecs")
        assert "✓" in result
        assert "BuckConverter" in result
        mock_client.load.assert_called_with("C:/models/buck.plecs")

    def test_failure(self, tools, mock_client):
        mock_client.load.side_effect = PlecsError("文件不存在")
        result = tools["plecs_load"](path="/bad/path.plecs")
        assert "✗" in result
        assert "文件不存在" in result


# ── plecs_close ───────────────────────────────────────────────────────────

class TestClose:
    def test_success(self, tools, mock_client):
        result = tools["plecs_close"](model_name="BuckConverter")
        assert "✓" in result
        mock_client.close.assert_called_with("BuckConverter")

    def test_failure(self, tools, mock_client):
        mock_client.close.side_effect = PlecsError("模型未打开")
        result = tools["plecs_close"](model_name="NoModel")
        assert "✗" in result


# ── plecs_get ─────────────────────────────────────────────────────────────

class TestGet:
    def test_reads_param(self, tools, mock_client):
        result = tools["plecs_get"](path="BuckConverter/L1", param="L")
        assert "47e-6" in result
        mock_client.get.assert_called_with("BuckConverter/L1", "L")

    def test_failure(self, tools, mock_client):
        mock_client.get.side_effect = PlecsError("参数不存在")
        result = tools["plecs_get"](path="BuckConverter/X", param="bad")
        assert "✗" in result


# ── plecs_set ─────────────────────────────────────────────────────────────

class TestSet:
    def test_sets_param(self, tools, mock_client):
        result = tools["plecs_set"](path="BuckConverter/L1", param="L", value="100e-6")
        assert "✓" in result
        mock_client.set_param.assert_called_with("BuckConverter/L1", "L", "100e-6")

    def test_shows_old_value(self, tools, mock_client):
        """set 应先 get 旧值做对比显示。"""
        mock_client.get.return_value = "47e-6"
        result = tools["plecs_set"](path="BuckConverter/L1", param="L", value="100e-6")
        assert "47e-6" in result  # 原值出现在输出中

    def test_failure(self, tools, mock_client):
        mock_client.set_param.side_effect = PlecsError("只读参数")
        result = tools["plecs_set"](path="BuckConverter/L1", param="L", value="0")
        assert "✗" in result


# ── plecs_simulate ────────────────────────────────────────────────────────

class TestSimulate:
    def test_basic(self, tools, mock_client):
        result = tools["plecs_simulate"](model_name="BuckConverter")
        assert "✓" in result
        assert "通道" in result
        mock_client.simulate.assert_called_with("BuckConverter", None)

    def test_with_model_vars(self, tools, mock_client):
        tools["plecs_simulate"](
            model_name="BuckConverter",
            opts='{"ModelVars": {"Vin": 48, "R_load": 10}}',
        )
        call_opts = mock_client.simulate.call_args[0][1]
        assert call_opts["ModelVars"]["Vin"] == 48

    def test_with_stop_time(self, tools, mock_client):
        tools["plecs_simulate"](
            model_name="BuckConverter",
            opts='{"StopTime": 0.005}',
        )
        call_opts = mock_client.simulate.call_args[0][1]
        assert call_opts["StopTime"] == 0.005

    def test_invalid_json(self, tools, mock_client):
        result = tools["plecs_simulate"](model_name="BuckConverter", opts="{bad}")
        assert "✗" in result
        mock_client.simulate.assert_not_called()

    def test_empty_result(self, tools, mock_client):
        mock_client.simulate.return_value = {}
        result = tools["plecs_simulate"](model_name="BuckConverter")
        assert "无数据" in result or "Output" in result

    def test_no_channels(self, tools, mock_client):
        mock_client.simulate.return_value = {"Time": [0, 1e-3], "Values": []}
        result = tools["plecs_simulate"](model_name="BuckConverter")
        assert "Output" in result or "输出" in result


# ── plecs_analyze ─────────────────────────────────────────────────────────

class TestAnalyze:
    def test_ac_sweep_basic(self, tools, mock_client):
        result = tools["plecs_analyze"](
            model_name="BuckConverter",
            analysis_type="ACSweep",
            opts='{"SysName": "loopgain"}',
        )
        assert "✓" in result
        assert "Hz" in result
        mock_client.analyze.assert_called_with("BuckConverter", "ACSweep", {"SysName": "loopgain"})

    def test_ac_sweep_phase_margin(self, tools, mock_client):
        """增益穿越 0dB 时应计算相位裕度。"""
        mock_client.analyze.return_value = {
            "Frequencies": [100, 1000, 10000],
            "Magnitude":   [10.0, 0.5, -10.0],
            "Phase":       [-90.0, -120.0, -150.0],
        }
        result = tools["plecs_analyze"](
            model_name="BuckConverter", analysis_type="ACSweep", opts="{}"
        )
        assert "相位裕度" in result

    def test_ac_sweep_low_pm_warning(self, tools, mock_client):
        mock_client.analyze.return_value = {
            "Frequencies": [100, 1000, 10000],
            "Magnitude":   [10.0, 0.5, -10.0],
            "Phase":       [-90.0, -160.0, -175.0],
        }
        result = tools["plecs_analyze"](
            model_name="BuckConverter", analysis_type="ACSweep", opts="{}"
        )
        assert "⚠" in result or "✗" in result

    def test_invalid_json(self, tools, mock_client):
        result = tools["plecs_analyze"](
            model_name="BuckConverter", analysis_type="ACSweep", opts="{bad}"
        )
        assert "✗" in result
        mock_client.analyze.assert_not_called()

    def test_other_analysis_type(self, tools, mock_client):
        mock_client.analyze.return_value = {"result": "ok"}
        result = tools["plecs_analyze"](
            model_name="BuckConverter", analysis_type="SteadyState", opts="{}"
        )
        assert "SteadyState" in result


# ── plecs_scope ───────────────────────────────────────────────────────────

class TestScope:
    def test_clear_traces(self, tools, mock_client):
        result = tools["plecs_scope"](
            scope_path="BuckConverter/Scope", command="ClearTraces"
        )
        mock_client.scope.assert_called_with("BuckConverter/Scope", "ClearTraces")
        assert "✓" in result

    def test_hold_trace_with_label(self, tools, mock_client):
        result = tools["plecs_scope"](
            scope_path="BuckConverter/Scope",
            command="HoldTrace",
            args='["R=10Ω"]',
        )
        mock_client.scope.assert_called_with("BuckConverter/Scope", "HoldTrace", "R=10Ω")
        assert "✓" in result

    def test_export_csv(self, tools, mock_client):
        result = tools["plecs_scope"](
            scope_path="BuckConverter/Scope",
            command="ExportCSV",
            args='["C:/out/wave.csv"]',
        )
        mock_client.scope.assert_called_with(
            "BuckConverter/Scope", "ExportCSV", "C:/out/wave.csv"
        )

    def test_invalid_args_json(self, tools, mock_client):
        result = tools["plecs_scope"](
            scope_path="BuckConverter/Scope", command="HoldTrace", args="bad"
        )
        assert "✗" in result
        mock_client.scope.assert_not_called()

    def test_scope_returns_data(self, tools, mock_client):
        mock_client.scope.return_value = {"t": [0, 1], "v": [0, 48]}
        result = tools["plecs_scope"](
            scope_path="BuckConverter/Scope", command="GetCursorData", args="[[0, 0.001]]"
        )
        assert "✓" in result


# ── plecs_webserver ───────────────────────────────────────────────────────

class TestWebserver:
    def test_status(self, tools, mock_client):
        result = tools["plecs_webserver"](command="status")
        mock_client.webserver.assert_called_with("status")
        assert "✓" in result

    def test_failure(self, tools, mock_client):
        mock_client.webserver.side_effect = PlecsError("webserver 未启用")
        result = tools["plecs_webserver"](command="start")
        assert "✗" in result


# ── plecs_codegen ─────────────────────────────────────────────────────────

class TestCodegen:
    def test_basic(self, tools, mock_client):
        result = tools["plecs_codegen"](model_name="BuckConverter")
        mock_client.codegen.assert_called_with("BuckConverter", None)
        assert "✓" in result

    def test_with_opts(self, tools, mock_client):
        tools["plecs_codegen"](
            model_name="BuckConverter",
            opts='{"GenerateCode": true, "BuildCode": true}',
        )
        call_opts = mock_client.codegen.call_args[0][1]
        assert call_opts["GenerateCode"] is True

    def test_invalid_json(self, tools, mock_client):
        result = tools["plecs_codegen"](model_name="BuckConverter", opts="{bad}")
        assert "✗" in result
        mock_client.codegen.assert_not_called()

    def test_failure(self, tools, mock_client):
        mock_client.codegen.side_effect = PlecsError("Coder 未授权")
        result = tools["plecs_codegen"](model_name="BuckConverter")
        assert "✗" in result


# ── plecs_client 单元测试 ─────────────────────────────────────────────────

class TestPlecsClient:
    @pytest.fixture
    def mock_proxy(self):
        p = MagicMock()
        p.plecs.statistics.return_value = {
            "version": "4.7.4", "build": "test", "models": []
        }
        return p

    def test_connect_success(self, mock_proxy):
        c = PlecsClient()
        with patch("xmlrpc.client.ServerProxy", return_value=mock_proxy):
            stats = c.connect()
        assert stats["version"] == "4.7.4"
        assert c._proxy is not None

    def test_connect_refused(self):
        c = PlecsClient()
        with patch("xmlrpc.client.ServerProxy", side_effect=ConnectionRefusedError):
            with pytest.raises(PlecsError, match="无法连接"):
                c.connect()

    def test_call_without_connect(self):
        c = PlecsClient()
        with pytest.raises(PlecsError, match="未连接"):
            c.get("Model", "Param")

    def test_get(self, mock_proxy):
        c = PlecsClient()
        c._proxy = mock_proxy
        mock_proxy.plecs.get.return_value = "47e-6"
        assert c.get("Model/L1", "L") == "47e-6"

    def test_set_param(self, mock_proxy):
        c = PlecsClient()
        c._proxy = mock_proxy
        c.set_param("Model/L1", "L", "100e-6")
        mock_proxy.plecs.set.assert_called_with("Model/L1", "L", "100e-6")

    def test_simulate_passes_opts(self, mock_proxy):
        c = PlecsClient()
        c._proxy = mock_proxy
        mock_proxy.plecs.simulate.return_value = {"Time": [], "Values": []}
        opts = {"ModelVars": {"Vin": 48}, "StopTime": 0.01}
        c.simulate("Model", opts)
        mock_proxy.plecs.simulate.assert_called_with("Model", opts)

    def test_simulate_returns_empty_on_none(self, mock_proxy):
        c = PlecsClient()
        c._proxy = mock_proxy
        mock_proxy.plecs.simulate.return_value = None
        assert c.simulate("Model") == {}

    def test_analyze(self, mock_proxy):
        c = PlecsClient()
        c._proxy = mock_proxy
        mock_proxy.plecs.analyze.return_value = {"Frequencies": [100]}
        result = c.analyze("Model", "ACSweep", {"SysName": "lg"})
        assert result["Frequencies"] == [100]

    def test_scope_clear(self, mock_proxy):
        c = PlecsClient()
        c._proxy = mock_proxy
        c.scope("Model/Scope", "ClearTraces")
        mock_proxy.plecs.scope.assert_called_with("Model/Scope", "ClearTraces")

    def test_scope_export_csv(self, mock_proxy):
        c = PlecsClient()
        c._proxy = mock_proxy
        c.scope("Model/Scope", "ExportCSV", "C:/out.csv")
        mock_proxy.plecs.scope.assert_called_with("Model/Scope", "ExportCSV", "C:/out.csv")

    def test_rpc_fault_converted(self, mock_proxy):
        import xmlrpc.client
        c = PlecsClient()
        c._proxy = mock_proxy
        mock_proxy.plecs.get.side_effect = xmlrpc.client.Fault(-1, "bad param")
        with pytest.raises(PlecsError, match="bad param"):
            c.get("Model", "BadParam")

    def test_statistics(self, mock_proxy):
        c = PlecsClient()
        c._proxy = mock_proxy
        stats = c.statistics()
        assert stats["version"] == "4.7.4"

    def test_load(self, mock_proxy):
        c = PlecsClient()
        c._proxy = mock_proxy
        mock_proxy.plecs.load.return_value = "BuckConverter"
        assert c.load("C:/buck.plecs") == "BuckConverter"

    def test_load_fallback_name(self, mock_proxy):
        c = PlecsClient()
        c._proxy = mock_proxy
        mock_proxy.plecs.load.return_value = ""
        assert c.load("C:/boost_converter.plecs") == "boost_converter"

    def test_close(self, mock_proxy):
        c = PlecsClient()
        c._proxy = mock_proxy
        c.close("BuckConverter")
        mock_proxy.plecs.close.assert_called_with("BuckConverter")
