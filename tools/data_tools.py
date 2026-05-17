"""
tools/data_tools.py
--------------------
数据导出类 MCP 工具：Scope 波形导出、CSV/图片输出、
仿真结果读取，以及多次仿真叠加对比。
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

    # ── Tool: plecs_export_scope_csv ─────────────────────────────────────

    @mcp.tool()
    def plecs_export_scope_csv(
        scope_path: str,
        output_path: str,
    ) -> str:
        """
        将 PLECS Scope 中的波形数据导出为 CSV 文件。

        导出的 CSV 第一列为时间（秒），后续列为各信号通道数据，
        第一行为列标题（由 PLECS 自动生成）。

        Args:
            scope_path: Scope 组件的完整层级路径。
                        格式：``"ModelName/ScopeName"``。
                        例如：``"BuckConv/Scope"``、``"Inverter/Output/VoltageScope"``

            output_path: CSV 文件的保存路径（绝对路径）。
                         例如：``"C:/results/buck_waveform.csv"``

        Returns:
            导出结果确认，包含文件路径和大小信息。
        """
        client: PlecsClient = get_client()

        # 确保目标目录存在
        out_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(out_dir, exist_ok=True)

        client.scope_export_csv(scope_path, output_path)

        # 检查文件是否生成
        if os.path.exists(output_path):
            size_kb = os.path.getsize(output_path) / 1024
            return (
                f"✓ Scope 数据已导出为 CSV\n"
                f"  Scope：{scope_path}\n"
                f"  路径：{output_path}\n"
                f"  大小：{size_kb:.1f} KB"
            )
        return (
            f"✓ 导出命令已执行（文件路径：{output_path}）\n"
            f"  注：文件由 PLECS 生成，请在 PLECS 中确认文件是否存在。"
        )

    # ── Tool: plecs_export_scope_image ───────────────────────────────────

    @mcp.tool()
    def plecs_export_scope_image(
        scope_path: str,
        output_path: str,
    ) -> str:
        """
        将 PLECS Scope 的当前波形截图导出为图片文件。

        支持 PNG 和 SVG 格式（由输出文件扩展名决定）。
        图片内容与 PLECS 界面中 Scope 显示的内容完全一致。

        Args:
            scope_path:  Scope 组件路径，例如 ``"BuckConv/Scope"``。
            output_path: 图片保存路径，后缀 ``.png`` 或 ``.svg``。
                         例如：``"C:/results/bode_plot.png"``

        Returns:
            导出结果确认。
        """
        client: PlecsClient = get_client()

        out_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(out_dir, exist_ok=True)

        client.scope_export_image(scope_path, output_path)

        return (
            f"✓ Scope 截图已导出\n"
            f"  Scope：{scope_path}\n"
            f"  路径：{output_path}"
        )

    # ── Tool: plecs_scope_clear ───────────────────────────────────────────

    @mcp.tool()
    def plecs_scope_clear(scope_path: str) -> str:
        """
        清除 Scope 中的所有波形轨迹（不影响仿真设置）。

        在进行参数对比仿真前，先清除旧波形以保持 Scope 整洁。

        Args:
            scope_path: Scope 组件路径，例如 ``"BuckConv/Scope"``。

        Returns:
            操作确认信息。
        """
        client: PlecsClient = get_client()
        client.scope_clear(scope_path)
        return f"✓ 已清除 Scope 波形：{scope_path}"

    # ── Tool: plecs_scope_hold_trace ─────────────────────────────────────

    @mcp.tool()
    def plecs_scope_hold_trace(
        scope_path: str,
        trace_label: str = "",
    ) -> str:
        """
        保留 Scope 中的当前波形轨迹，用于多次仿真叠加对比显示。

        工作流示例（对比不同负载电阻的波形）：
          1. 设置 R=5Ω，运行仿真，然后调用此工具保留波形（label="R=5"）；
          2. 设置 R=10Ω，运行仿真，再次调用此工具保留波形（label="R=10"）；
          3. 所有波形将在 Scope 中叠加显示。

        Args:
            scope_path:  Scope 组件路径，例如 ``"BuckConv/Scope"``。
            trace_label: 波形标签，显示在 Scope 图例中。可留空。

        Returns:
            操作确认信息。
        """
        client: PlecsClient = get_client()
        client.scope_hold_trace(scope_path, trace_label)
        label_note = f"（标签：\"{trace_label}\"）" if trace_label else ""
        return f"✓ 已保留 Scope 波形轨迹 {label_note}：{scope_path}"

    # ── Tool: plecs_compare_simulations ──────────────────────────────────

    @mcp.tool()
    def plecs_compare_simulations(
        model_name: str,
        scenarios: str,
        stop_time: float = None,
        output_channel: int = 0,
    ) -> str:
        """
        运行多个仿真场景并对比输出结果（文字摘要形式）。

        Args:
            model_name: 已加载的模型名称。

            scenarios:  JSON 数组，每个元素是一个场景的变量字典加标签。
                        格式示例::

                            [
                              {"label": "轻载",  "vars": {"R_load": 50, "Vin": 48}},
                              {"label": "满载",  "vars": {"R_load": 10, "Vin": 48}},
                              {"label": "过载",  "vars": {"R_load": 5,  "Vin": 48}}
                            ]

            stop_time:      每次仿真结束时间（秒）。None 使用模型设定值。
            output_channel: 用于对比的输出通道索引（从 0 开始）。

        Returns:
            各场景的统计对比表，包含平均值、最大值、最小值、
            峰峰值和 RMS 值。
        """
        client: PlecsClient = get_client()

        try:
            scenario_list = json.loads(scenarios)
        except json.JSONDecodeError as exc:
            return f"错误：scenarios 格式不合法 → {exc}"

        solver_opts = {}
        if stop_time is not None:
            solver_opts["StopTime"] = stop_time

        lines = [
            f"多场景仿真对比（通道 {output_channel+1}）：",
            "",
            f"{'场景':^12}  {'平均':>10}  {'最小':>10}  {'最大':>10}  {'峰峰':>10}  {'RMS':>10}",
            "─" * 72,
        ]

        errors = []
        for sc in scenario_list:
            label = sc.get("label", "未命名")
            vars_ = sc.get("vars", {})

            try:
                result = client.simulate(
                    model_name,
                    model_vars=vars_,
                    solver_opts=solver_opts or None,
                )
                stats = _channel_stats(result, output_channel)
                if stats:
                    lines.append(
                        f"{label:^12}  "
                        f"{stats['avg']:>10.4g}  "
                        f"{stats['min']:>10.4g}  "
                        f"{stats['max']:>10.4g}  "
                        f"{stats['pp']:>10.4g}  "
                        f"{stats['rms']:>10.4g}"
                    )
                else:
                    lines.append(f"{label:^12}  （无输出数据）")
            except Exception as exc:
                errors.append(f"  场景 \"{label}\" → {exc}")

        if errors:
            lines.append("\n失败项：")
            lines += errors

        return "\n".join(lines)


# ── 辅助函数 ─────────────────────────────────────────────────────────────

def _channel_stats(result: dict, ch_idx: int = 0) -> dict | None:
    """计算指定输出通道的统计量。"""
    if not result or "Values" not in result:
        return None

    channels = result.get("Values", [])
    if ch_idx >= len(channels):
        return None

    data = channels[ch_idx]
    if not data:
        return None

    mean = sum(data) / len(data)
    rms  = (sum(x * x for x in data) / len(data)) ** 0.5

    return {
        "min": min(data),
        "max": max(data),
        "avg": mean,
        "pp":  max(data) - min(data),
        "rms": rms,
    }
