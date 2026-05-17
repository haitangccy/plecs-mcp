"""
tests/test_mcp_tools.py
------------------------
MCP 工具逻辑集成测试：直接测试工具函数的输入解析、输出格式和错误处理。
使用轻量 stub 替代 mcp 包，Mock 模拟 PlecsClient，无需真实 PLECS 实例。
"""

import pytest
import json
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── FastMCP stub（避免依赖未安装的 mcp 包）───────────────────────────────
import types

class _FakeFastMCP:
    """最小化 FastMCP stub，仅收集 @mcp.tool() 注册的函数。"""
    def __init__(self, name="test", **kwargs):
        self._tools = {}

    def tool(self):
        def decorator(fn):
            self._tools[fn.__name__] = fn
            return fn
        return decorator

_mcp_pkg = types.ModuleType("mcp")
_mcp_server = types.ModuleType("mcp.server")
_mcp_fastmcp = types.ModuleType("mcp.server.fastmcp")
_mcp_fastmcp.FastMCP = _FakeFastMCP
_mcp_pkg.server = _mcp_server
_mcp_server.fastmcp = _mcp_fastmcp

sys.modules.setdefault("mcp", _mcp_pkg)
sys.modules.setdefault("mcp.server", _mcp_server)
sys.modules.setdefault("mcp.server.fastmcp", _mcp_fastmcp)


# ── Mock Client Fixture ─────────────────────────────────────────────────

@pytest.fixture
def mock_client():
    client = MagicMock()
    client.is_connected.return_value = True
    client.get_version.return_value = "4.7.0"
    client.load_model.return_value = "BuckConverter"
    client.get_param.return_value = "47e-6"
    client.simulate.return_value = {
        "Time":   list(range(100)),
        "Values": [
            [48.0 + i * 0.01 for i in range(100)],
            [5.0  - i * 0.001 for i in range(100)],
        ],
    }
    return client


def make_tools(mock_client):
    """注册工具并返回 {name: fn} 字典。"""
    from tools.model_tools      import register as reg_model
    from tools.simulation_tools import register as reg_sim
    from tools.data_tools       import register as reg_data

    mcp = _FakeFastMCP()
    get_client = lambda: mock_client

    reg_model(mcp, get_client)
    reg_sim(mcp, get_client)
    reg_data(mcp, get_client)

    return mcp._tools


# ── 模型工具测试 ────────────────────────────────────────────────────────

class TestModelTools:

    def test_load_model_success(self, mock_client, tmp_path):
        tools = make_tools(mock_client)
        model_file = tmp_path / "buck.plecs"
        model_file.write_text("<plecs/>")
        result = tools["plecs_load_model"](model_path=str(model_file))
        assert "✓" in result
        assert "BuckConverter" in result

    def test_load_model_file_not_found(self, mock_client):
        tools = make_tools(mock_client)
        result = tools["plecs_load_model"](model_path="/nonexistent/model.plecs")
        assert "错误" in result or "不存在" in result

    def test_save_model(self, mock_client):
        tools = make_tools(mock_client)
        result = tools["plecs_save_model"](model_name="BuckConverter")
        mock_client.save_model.assert_called_once_with("BuckConverter")
        assert "✓" in result

    def test_close_model_no_save(self, mock_client):
        tools = make_tools(mock_client)
        result = tools["plecs_close_model"](model_name="BuckConverter", save_first=False)
        mock_client.close_model.assert_called_once_with("BuckConverter")
        mock_client.save_model.assert_not_called()
        assert "✓" in result

    def test_close_model_with_save(self, mock_client):
        tools = make_tools(mock_client)
        result = tools["plecs_close_model"](model_name="BuckConverter", save_first=True)
        mock_client.save_model.assert_called_once_with("BuckConverter")
        mock_client.close_model.assert_called_once_with("BuckConverter")
        assert "已先保存" in result

    def test_get_param(self, mock_client):
        tools = make_tools(mock_client)
        result = tools["plecs_get_param"](
            component_path="BuckConverter/L1", parameter="L"
        )
        assert "47e-6" in result
        assert "BuckConverter/L1" in result

    def test_set_param(self, mock_client):
        tools = make_tools(mock_client)
        result = tools["plecs_set_param"](
            component_path="BuckConverter/L1", parameter="L", value="100e-6"
        )
        mock_client.set_param.assert_called_once_with("BuckConverter/L1", "L", "100e-6")
        assert "✓" in result

    def test_batch_set_params_valid(self, mock_client):
        tools = make_tools(mock_client)
        params = json.dumps([
            {"path": "BuckConverter/L1", "param": "L",  "value": "47e-6"},
            {"path": "BuckConverter/C1", "param": "C",  "value": "220e-6"},
        ])
        result = tools["plecs_batch_set_params"](params_json=params)
        assert mock_client.set_param.call_count == 2
        assert "2/2" in result

    def test_batch_set_params_invalid_json(self, mock_client):
        tools = make_tools(mock_client)
        result = tools["plecs_batch_set_params"](params_json="not json {{")
        assert "错误" in result
        mock_client.set_param.assert_not_called()

    def test_batch_set_params_missing_path(self, mock_client):
        tools = make_tools(mock_client)
        params = json.dumps([{"param": "L", "value": "47e-6"}])  # 缺 path
        result = tools["plecs_batch_set_params"](params_json=params)
        assert mock_client.set_param.call_count == 0


# ── 仿真工具测试 ────────────────────────────────────────────────────────

class TestSimulationTools:

    def test_run_simulation_basic(self, mock_client):
        tools = make_tools(mock_client)
        result = tools["plecs_run_simulation"](model_name="BuckConverter")
        assert "✓" in result
        assert "通道" in result
        mock_client.simulate.assert_called_once()

    def test_run_simulation_with_vars(self, mock_client):
        tools = make_tools(mock_client)
        result = tools["plecs_run_simulation"](
            model_name="BuckConverter",
            model_vars='{"Vin": 48, "R_load": 10}',
        )
        assert "✓" in result
        call = mock_client.simulate.call_args
        assert call[1]["model_vars"]["Vin"] == 48

    def test_run_simulation_with_stop_time(self, mock_client):
        tools = make_tools(mock_client)
        tools["plecs_run_simulation"](model_name="BuckConverter", stop_time=0.01)
        call = mock_client.simulate.call_args
        assert call[1]["solver_opts"]["StopTime"] == 0.01

    def test_run_simulation_with_solver(self, mock_client):
        tools = make_tools(mock_client)
        tools["plecs_run_simulation"](model_name="BuckConverter", solver="ode45")
        call = mock_client.simulate.call_args
        assert call[1]["solver_opts"]["SolverMethod"] == "ode45"

    def test_run_simulation_invalid_json(self, mock_client):
        tools = make_tools(mock_client)
        result = tools["plecs_run_simulation"](
            model_name="BuckConverter", model_vars="{bad}"
        )
        assert "错误" in result
        mock_client.simulate.assert_not_called()

    def test_run_simulation_no_output(self, mock_client):
        mock_client.simulate.return_value = {"Time": [0, 1e-3], "Values": []}
        tools = make_tools(mock_client)
        result = tools["plecs_run_simulation"](model_name="BuckConverter")
        assert "Output" in result or "输出" in result

    def test_parameter_sweep_count(self, mock_client):
        tools = make_tools(mock_client)
        tools["plecs_parameter_sweep"](
            model_name="BuckConverter",
            sweep_var="R_load",
            values="[5, 10, 20, 50]",
        )
        assert mock_client.simulate.call_count == 4

    def test_parameter_sweep_fixed_vars(self, mock_client):
        tools = make_tools(mock_client)
        tools["plecs_parameter_sweep"](
            model_name="BuckConverter",
            sweep_var="R_load",
            values="[10]",
            fixed_vars='{"Vin": 48}',
        )
        call = mock_client.simulate.call_args
        passed = call[1]["model_vars"]
        assert passed["Vin"] == 48
        assert passed["R_load"] == 10

    def test_parameter_sweep_invalid_values(self, mock_client):
        tools = make_tools(mock_client)
        result = tools["plecs_parameter_sweep"](
            model_name="BuckConverter", sweep_var="R", values="bad"
        )
        assert "错误" in result
        mock_client.simulate.assert_not_called()

    def test_ac_sweep_basic(self, mock_client):
        mock_client.analyze.return_value = {
            "Frequency": [10, 100, 1000, 10000, 100000],
            "Magnitude": [20.0, 15.0, 5.0, -3.0, -20.0],
            "Phase":     [-10.0, -30.0, -90.0, -150.0, -175.0],
        }
        tools = make_tools(mock_client)
        result = tools["plecs_ac_sweep"](
            model_name="BuckConverter",
            analysis_name="loopgain",
            f_start=10.0,
            f_stop=100e3,
        )
        assert "✓" in result
        assert "Hz" in result

    def test_ac_sweep_phase_margin_detected(self, mock_client):
        mock_client.analyze.return_value = {
            "Frequency": [100, 1000, 10000],
            "Magnitude": [10.0, 0.5, -10.0],
            "Phase":     [-90.0, -120.0, -150.0],
        }
        tools = make_tools(mock_client)
        result = tools["plecs_ac_sweep"](
            model_name="BuckConverter", analysis_name="lg", f_start=100.0, f_stop=1e5
        )
        assert "相位裕度" in result

    def test_ac_sweep_low_phase_margin_warning(self, mock_client):
        mock_client.analyze.return_value = {
            "Frequency": [100, 1000, 10000],
            "Magnitude": [10.0, 0.5, -10.0],
            "Phase":     [-90.0, -158.0, -175.0],
        }
        tools = make_tools(mock_client)
        result = tools["plecs_ac_sweep"](
            model_name="BuckConverter", analysis_name="lg", f_start=100.0, f_stop=1e5
        )
        assert "⚠" in result

    def test_ac_sweep_no_crossover(self, mock_client):
        mock_client.analyze.return_value = {
            "Frequency": [100, 1000],
            "Magnitude": [-5.0, -15.0],
            "Phase":     [-90.0, -120.0],
        }
        tools = make_tools(mock_client)
        result = tools["plecs_ac_sweep"](
            model_name="BuckConverter", analysis_name="lg", f_start=100.0, f_stop=1e5
        )
        assert "未发现" in result or "0dB" in result


# ── 数据工具测试 ────────────────────────────────────────────────────────

class TestDataTools:

    def test_scope_clear(self, mock_client):
        tools = make_tools(mock_client)
        result = tools["plecs_scope_clear"](scope_path="BuckConverter/Scope")
        mock_client.scope_clear.assert_called_once_with("BuckConverter/Scope")
        assert "✓" in result

    def test_scope_hold_trace_with_label(self, mock_client):
        tools = make_tools(mock_client)
        result = tools["plecs_scope_hold_trace"](
            scope_path="BuckConverter/Scope", trace_label="R=10Ω"
        )
        mock_client.scope_hold_trace.assert_called_once_with("BuckConverter/Scope", "R=10Ω")
        assert "R=10Ω" in result

    def test_export_scope_csv_creates_dir(self, mock_client, tmp_path):
        tools = make_tools(mock_client)
        out_file = str(tmp_path / "subdir" / "nested" / "waveform.csv")
        result = tools["plecs_export_scope_csv"](
            scope_path="BuckConverter/Scope", output_path=out_file
        )
        assert os.path.exists(os.path.dirname(out_file))
        mock_client.scope_export_csv.assert_called_once()
        assert "✓" in result or "已导出" in result

    def test_export_scope_image(self, mock_client, tmp_path):
        tools = make_tools(mock_client)
        out_file = str(tmp_path / "scope.png")
        result = tools["plecs_export_scope_image"](
            scope_path="BuckConverter/Scope", output_path=out_file
        )
        mock_client.scope_export_image.assert_called_once()
        assert "✓" in result

    def test_compare_simulations(self, mock_client):
        scenarios = json.dumps([
            {"label": "轻载", "vars": {"R_load": 50}},
            {"label": "满载", "vars": {"R_load": 10}},
        ])
        tools = make_tools(mock_client)
        result = tools["plecs_compare_simulations"](
            model_name="BuckConverter", scenarios=scenarios
        )
        assert mock_client.simulate.call_count == 2
        assert "轻载" in result
        assert "满载" in result

    def test_compare_simulations_invalid_json(self, mock_client):
        tools = make_tools(mock_client)
        result = tools["plecs_compare_simulations"](
            model_name="BuckConverter", scenarios="bad"
        )
        assert "错误" in result
        mock_client.simulate.assert_not_called()

    def test_compare_uses_correct_channel(self, mock_client):
        mock_client.simulate.return_value = {
            "Time": list(range(10)),
            "Values": [[48.0] * 10, [5.0] * 10],
        }
        scenarios = json.dumps([{"label": "test", "vars": {}}])
        tools = make_tools(mock_client)
        result = tools["plecs_compare_simulations"](
            model_name="BuckConverter", scenarios=scenarios, output_channel=1
        )
        assert "5" in result
