"""
tools/model_tools.py
--------------------
模型操作类 MCP 工具：加载、保存、关闭模型，以及读写组件参数。
"""

from __future__ import annotations
import os
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plecs_client import PlecsClient

logger = logging.getLogger(__name__)


def register(mcp, get_client):
    """将本模块的所有工具注册到 FastMCP 实例上。"""

    # ── Tool: plecs_load_model ───────────────────────────────────────────

    @mcp.tool()
    def plecs_load_model(model_path: str) -> str:
        """
        在 PLECS 中打开一个 .plecs 模型文件。

        Args:
            model_path: .plecs 文件的绝对路径（Windows 用正斜杠或双反斜杠均可），
                        例如 "C:/models/buck_converter.plecs"

        Returns:
            加载成功的模型名称（字符串）。后续所有工具的 model_name 参数均使用此值。

        注意:
            - 模型必须存在于本地文件系统；
            - PLECS 需已启动且 XML-RPC 已开启；
            - 同一模型不能重复加载，关闭后方可再次加载。
        """
        client: PlecsClient = get_client()
        path = os.path.abspath(model_path.replace("\\", "/"))

        if not os.path.exists(path):
            return f"错误：文件不存在 → {path}"

        model_name = client.load_model(path)
        return (
            f"✓ 模型已加载\n"
            f"  名称：{model_name}\n"
            f"  路径：{path}\n"
            f"  提示：后续工具调用请使用模型名称 \"{model_name}\""
        )

    # ── Tool: plecs_save_model ───────────────────────────────────────────

    @mcp.tool()
    def plecs_save_model(model_name: str) -> str:
        """
        将已打开的 PLECS 模型保存到磁盘（覆盖原文件）。

        Args:
            model_name: 已加载的模型名称（来自 plecs_load_model 的返回值）。

        Returns:
            保存结果确认信息。
        """
        client: PlecsClient = get_client()
        client.save_model(model_name)
        return f"✓ 模型 \"{model_name}\" 已保存"

    # ── Tool: plecs_close_model ──────────────────────────────────────────

    @mcp.tool()
    def plecs_close_model(model_name: str, save_first: bool = False) -> str:
        """
        关闭 PLECS 中已打开的模型。

        Args:
            model_name: 已加载的模型名称。
            save_first: 关闭前是否先保存，默认 False。
                        如果模型有未保存的修改且此参数为 False，修改将丢失。

        Returns:
            关闭结果确认信息。
        """
        client: PlecsClient = get_client()

        if save_first:
            client.save_model(model_name)

        client.close_model(model_name)
        saved_note = "（已先保存）" if save_first else "（未保存修改）"
        return f"✓ 模型 \"{model_name}\" 已关闭 {saved_note}"

    # ── Tool: plecs_get_param ────────────────────────────────────────────

    @mcp.tool()
    def plecs_get_param(component_path: str, parameter: str) -> str:
        """
        读取模型或组件的参数值。

        Args:
            component_path: 组件的层级路径，格式为 "ModelName/SubSys/CompName"。

                路径示例：
                  ""                    → PLECS 全局属性（如 "Version"）
                  "BuckConv"            → 模型级属性（如 "SimulationTime"）
                  "BuckConv/L1"         → 顶层组件 L1 的参数
                  "BuckConv/Control/R1" → 子系统 Control 内组件 R1 的参数

            parameter: 参数名称。常用参数名：

                模型级：SimulationTime、MaxStep、AbsTol、RelTol、SolverMethod
                电感：  L（感值 H）、I_init（初始电流 A）
                电容：  C（容值 F）、V_init（初始电压 V）
                电阻：  R（阻值 Ω）
                MOSFET：R_on（导通电阻）、V_f（体二极管正向电压）
                开关：  f_sw（开关频率）、duty（占空比）

        Returns:
            参数的当前值（字符串格式）。
        """
        client: PlecsClient = get_client()
        value = client.get_param(component_path, parameter)
        return f"{component_path}.{parameter} = {value}"

    # ── Tool: plecs_set_param ────────────────────────────────────────────

    @mcp.tool()
    def plecs_set_param(
        component_path: str,
        parameter: str,
        value: str,
    ) -> str:
        """
        修改模型或组件的参数值。

        Args:
            component_path: 组件路径，格式同 plecs_get_param。
                            例如 "BuckConv/L1"

            parameter: 参数名称，例如 "L"、"R"、"V_init"。

            value: 新参数值（字符串）。PLECS 会自动解析数值和表达式。
                   支持科学计数法：例如 "47e-6"、"220e-6"、"1e3"。
                   支持变量引用（需模型中已定义该变量）：例如 "L_val"。

        Returns:
            修改确认信息。建议修改完成后调用 plecs_save_model 保存。
        """
        client: PlecsClient = get_client()
        client.set_param(component_path, parameter, value)
        return (
            f"✓ 参数已修改\n"
            f"  路径：{component_path}\n"
            f"  参数：{parameter}\n"
            f"  新值：{value}\n"
            f"  提示：调用 plecs_save_model 以持久化此修改"
        )

    # ── Tool: plecs_batch_set_params ─────────────────────────────────────

    @mcp.tool()
    def plecs_batch_set_params(params_json: str) -> str:
        """
        批量修改多个组件参数（一次调用完成多项修改，减少往返延迟）。

        Args:
            params_json: JSON 数组字符串，每个元素包含三个字段：
                         ``path``（组件路径）、``param``（参数名）、``value``（新值）。

                格式示例::

                    [
                      {"path": "BuckConv/L1", "param": "L",    "value": "47e-6"},
                      {"path": "BuckConv/C1", "param": "C",    "value": "220e-6"},
                      {"path": "BuckConv/R1", "param": "R",    "value": "10"},
                      {"path": "BuckConv",    "param": "StopTime", "value": "0.005"}
                    ]

        Returns:
            每项修改的结果汇总。
        """
        client: PlecsClient = get_client()

        try:
            items = json.loads(params_json)
        except json.JSONDecodeError as exc:
            return f"错误：params_json 格式不合法 → {exc}"

        if not isinstance(items, list):
            return "错误：params_json 必须是 JSON 数组"

        results = []
        errors  = []

        for i, item in enumerate(items):
            path  = item.get("path", "")
            param = item.get("param", "")
            val   = item.get("value", "")

            if not path or not param:
                errors.append(f"  第 {i+1} 项缺少 path 或 param 字段")
                continue

            try:
                client.set_param(path, param, val)
                results.append(f"  ✓ {path}.{param} = {val}")
            except Exception as exc:
                errors.append(f"  ✗ {path}.{param} → {exc}")

        lines = [f"批量参数修改完成（{len(results)}/{len(items)} 成功）："]
        lines += results
        if errors:
            lines.append("\n失败项：")
            lines += errors

        return "\n".join(lines)

    # ── Tool: plecs_list_components ──────────────────────────────────────

    @mcp.tool()
    def plecs_list_components(model_name: str) -> str:
        """
        列举模型顶层的所有组件名称，帮助 Agent 了解模型结构。

        Args:
            model_name: 已加载的模型名称。

        Returns:
            组件名称列表（字符串）。
        """
        client: PlecsClient = get_client()
        components = client.list_components(model_name)

        if not components:
            return (
                f"模型 \"{model_name}\" 顶层无可枚举组件，"
                f"或该版本 PLECS 不支持 Components 属性查询。\n"
                f"建议直接通过 plecs_get_param 读取已知组件的参数。"
            )

        lines = [f"模型 \"{model_name}\" 顶层组件（共 {len(components)} 个）："]
        for comp in components:
            lines.append(f"  • {comp}")
        return "\n".join(lines)
