"""
tools/simulation_tools.py
--------------------------
仿真控制与频域分析类 MCP 工具：时域仿真、参数扫描、AC Sweep。
"""

from __future__ import annotations
import json
import logging
import statistics
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plecs_client import PlecsClient

logger = logging.getLogger(__name__)


def register(mcp, get_client):
    """将本模块的所有工具注册到 FastMCP 实例上。"""

    # ── Tool: plecs_run_simulation ───────────────────────────────────────

    @mcp.tool()
    def plecs_run_simulation(
        model_name: str,
        model_vars: str = "{}",
        stop_time: float = None,
        max_step: float = None,
        abs_tol: float = None,
        rel_tol: float = None,
        solver: str = None,
    ) -> str:
        """
        运行 PLECS 时域仿真并返回结果统计摘要。

        Args:
            model_name:  已加载的模型名称（来自 plecs_load_model）。

            model_vars:  JSON 对象字符串，覆盖模型变量（初始化命令中的变量）。
                         例如：``'{"Vin": 48, "R_load": 10, "f_sw": 100e3}'``
                         默认为空对象 ``"{}"``，表示使用模型原有值。

            stop_time:   仿真结束时间（秒）。None 则使用模型设定值。
                         典型值：开关电源稳态分析用 5~20 个开关周期，
                         例如 100kHz 开关频率时用 0.0001（10 个周期）~0.001。

            max_step:    最大仿真步长（秒）。None 则使用模型设定值。
                         建议设为开关周期的 1/100~1/1000。

            abs_tol:     绝对容差（默认 1e-6）。

            rel_tol:     相对容差（默认 1e-3）。

            solver:      求解器名称，例如 "auto"、"ode45"、"ode23tb"。
                         对含开关的电力电子电路推荐使用默认 "auto"。

        Returns:
            仿真结果统计摘要，包含时间范围、时间点数、各输出通道的
            最小值/最大值/平均值/峰峰值/RMS 值。

        注意：
            - 模型中须有 Output 端口（Scope 连接不产生数值输出）；
            - 结果中各通道顺序与模型 Output 端口从上到下的顺序一致；
            - 若需原始数据请使用 plecs_export_scope 导出 CSV。
        """
        client: PlecsClient = get_client()

        try:
            vars_dict = json.loads(model_vars)
        except json.JSONDecodeError as exc:
            return f"错误：model_vars 格式不合法 → {exc}"

        solver_opts: dict = {}
        if stop_time is not None: solver_opts["StopTime"]  = stop_time
        if max_step  is not None: solver_opts["MaxStep"]   = max_step
        if abs_tol   is not None: solver_opts["AbsTol"]    = abs_tol
        if rel_tol   is not None: solver_opts["RelTol"]    = rel_tol
        if solver    is not None: solver_opts["SolverMethod"] = solver

        result = client.simulate(
            model_name,
            model_vars=vars_dict or None,
            solver_opts=solver_opts or None,
        )

        return _format_sim_result(result, model_vars=vars_dict)

    # ── Tool: plecs_parameter_sweep ──────────────────────────────────────

    @mcp.tool()
    def plecs_parameter_sweep(
        model_name: str,
        sweep_var: str,
        values: str,
        fixed_vars: str = "{}",
        stop_time: float = None,
        output_channel: int = 0,
    ) -> str:
        """
        对单个模型变量进行参数扫描，批量运行多次仿真。

        Args:
            model_name:     已加载的模型名称。

            sweep_var:      要扫描的模型变量名，例如 ``"R_load"``、``"Vin"``、``"L"``。
                            此变量必须在模型初始化命令中有定义。

            values:         JSON 数组，扫描值列表。例如 ``"[5, 10, 20, 50]"``。
                            支持浮点数：``"[1e-6, 2.2e-6, 4.7e-6, 10e-6]"``。

            fixed_vars:     JSON 对象，固定不变的其他模型变量。
                            例如 ``'{"Vin": 48, "f_sw": 100e3}'``。

            stop_time:      每次仿真的结束时间（秒）。None 使用模型设定值。

            output_channel: 用于统计的输出通道索引（从 0 开始）。
                            默认 0 表示第一个输出通道。

        Returns:
            每个扫描点的仿真统计汇总表格。
        """
        client: PlecsClient = get_client()

        try:
            vals = json.loads(values)
        except json.JSONDecodeError as exc:
            return f"错误：values 格式不合法 → {exc}"

        try:
            fixed = json.loads(fixed_vars)
        except json.JSONDecodeError as exc:
            return f"错误：fixed_vars 格式不合法 → {exc}"

        solver_opts = {}
        if stop_time is not None:
            solver_opts["StopTime"] = stop_time

        lines = [
            f"参数扫描：{sweep_var} × {len(vals)} 个点",
            f"固定变量：{fixed if fixed else '（无）'}",
            "",
            f"{'值':>12}  {'平均':>10}  {'最小':>10}  {'最大':>10}  {'峰峰':>10}  {'RMS':>10}",
            "─" * 72,
        ]

        errors = []
        for v in vals:
            model_vars_run = {**fixed, sweep_var: v}
            try:
                result = client.simulate(
                    model_name,
                    model_vars=model_vars_run,
                    solver_opts=solver_opts or None,
                )
                stats = _channel_stats(result, output_channel)
                if stats:
                    lines.append(
                        f"{v:>12.4g}  "
                        f"{stats['avg']:>10.4g}  "
                        f"{stats['min']:>10.4g}  "
                        f"{stats['max']:>10.4g}  "
                        f"{stats['pp']:>10.4g}  "
                        f"{stats['rms']:>10.4g}"
                    )
                else:
                    lines.append(f"{v:>12.4g}  （无输出数据）")
            except Exception as exc:
                errors.append(f"  {sweep_var}={v} → {exc}")

        if errors:
            lines.append("\n失败项：")
            lines += errors

        return "\n".join(lines)

    # ── Tool: plecs_ac_sweep ─────────────────────────────────────────────

    @mcp.tool()
    def plecs_ac_sweep(
        model_name: str,
        analysis_name: str,
        f_start: float,
        f_stop: float,
        num_points: int = 50,
        amplitude: float = 0.01,
        log_scale: bool = True,
        steady_state: bool = True,
    ) -> str:
        """
        运行 AC Sweep（小信号频率响应分析），获取 Bode 图数据。

        在运行前，模型中须已配置好 AC Sweep 分析对象（在 PLECS 的
        Analysis Tools → AC Sweep 中定义）。

        Args:
            model_name:    已加载的模型名称。

            analysis_name: 模型中定义的 AC Sweep 分析名称
                           （在 PLECS 的 Analysis Tools 对话框中设置）。

            f_start:       起始频率（Hz）。例如 ``10``（10Hz）。

            f_stop:        终止频率（Hz）。例如 ``1e6``（1MHz）。

            num_points:    频率点数，默认 50。
                           对数分布时每十倍频约 10~20 点为宜。

            amplitude:     扰动幅值（归一化，相对于直流工作点）。
                           默认 0.01（即 1%），过大会引起非线性失真。

            log_scale:     是否使用对数频率分布，默认 True。
                           True 适合宽频段 Bode 图，False 适合窄带线性分析。

            steady_state:  是否先运行到稳态再做扫频，默认 True。
                           对含储能元件的电力电子电路应保持 True。

        Returns:
            Bode 图数据摘要：频率点列表及对应幅频/相频值，
            以及穿越频率（gain crossover frequency）和相位裕度估算。
        """
        client: PlecsClient = get_client()

        opts = {
            "FreqRange":   [f_start, f_stop],
            "NumPoints":   num_points,
            "Amplitude":   amplitude,
            "LogScale":    log_scale,
            "SteadyState": steady_state,
        }

        result = client.analyze(model_name, "ACSweep", opts)

        return _format_ac_sweep(result, f_start, f_stop)

    # ── Tool: plecs_impedance_sweep ──────────────────────────────────────

    @mcp.tool()
    def plecs_impedance_sweep(
        model_name: str,
        analysis_name: str,
        f_start: float,
        f_stop: float,
        num_points: int = 50,
        amplitude: float = 0.01,
    ) -> str:
        """
        运行阻抗扫描，分析电路端口的输入/输出阻抗特性。

        Args:
            model_name:    已加载的模型名称。
            analysis_name: 模型中定义的阻抗扫描分析名称。
            f_start:       起始频率（Hz）。
            f_stop:        终止频率（Hz）。
            num_points:    频率点数，默认 50。
            amplitude:     扰动幅值，默认 0.01。

        Returns:
            阻抗幅频特性摘要：幅值（Ω）和相位（°）随频率的分布。
        """
        client: PlecsClient = get_client()

        opts = {
            "FreqRange": [f_start, f_stop],
            "NumPoints": num_points,
            "Amplitude": amplitude,
        }

        result = client.analyze(model_name, "ImpedanceSweep", opts)

        return _format_impedance(result, f_start, f_stop)


# ── 结果格式化辅助函数 ──────────────────────────────────────────────────────

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
        "n":   len(data),
    }


def _format_sim_result(result: dict, model_vars: dict = None) -> str:
    """将仿真结果格式化为易读摘要。"""
    if not result:
        return (
            "仿真完成，但未收到数据。\n"
            "请确认模型顶层有 Output 端口（Scope 不产生数值输出）。"
        )

    time_vec = result.get("Time", [])
    if not time_vec:
        return "仿真完成，Time 向量为空（仿真可能被中断或步长设置有误）。"

    t_start = time_vec[0]
    t_end   = time_vec[-1]
    n_pts   = len(time_vec)

    lines = [
        "✓ 仿真完成",
        f"  时间范围：{t_start:.6g} s → {t_end:.6g} s",
        f"  时间点数：{n_pts}",
    ]

    if model_vars:
        vars_str = ", ".join(f"{k}={v}" for k, v in model_vars.items())
        lines.append(f"  模型变量：{vars_str}")

    channels = result.get("Values", [])
    if channels:
        lines.append(f"\n  输出通道统计（共 {len(channels)} 个通道）：")
        for i, ch_data in enumerate(channels):
            if not ch_data:
                lines.append(f"    通道 {i+1}：（无数据）")
                continue
            mean = sum(ch_data) / len(ch_data)
            rms  = (sum(x * x for x in ch_data) / len(ch_data)) ** 0.5
            lines.append(
                f"    通道 {i+1}：min={min(ch_data):.4g}  max={max(ch_data):.4g}"
                f"  avg={mean:.4g}  pp={max(ch_data)-min(ch_data):.4g}  rms={rms:.4g}"
            )
    else:
        lines.append("\n  （无数值输出通道，请检查模型是否连接了 Output 端口）")

    return "\n".join(lines)


def _format_ac_sweep(result: dict, f_start: float, f_stop: float) -> str:
    """格式化 AC Sweep 结果，计算穿越频率和相位裕度。"""
    if not result:
        return "AC Sweep 完成，但未收到数据。请确认模型中已配置 ACSweep 分析对象。"

    freq  = result.get("Frequency", [])
    mag   = result.get("Magnitude", [])   # dB
    phase = result.get("Phase", [])       # deg

    if not freq:
        return "AC Sweep 数据为空。"

    lines = [
        "✓ AC Sweep 完成",
        f"  频率范围：{f_start:.4g} Hz → {f_stop:.4g} Hz",
        f"  频率点数：{len(freq)}",
    ]

    if mag:
        lines.append(f"  幅值范围：{min(mag):.2f} dB → {max(mag):.2f} dB")

    if phase:
        lines.append(f"  相位范围：{min(phase):.1f}° → {max(phase):.1f}°")

    # 估算穿越频率（增益过 0dB 的点）和相位裕度
    if mag and phase and len(mag) == len(freq):
        crossover_f = None
        phase_margin = None
        for i in range(len(mag) - 1):
            if mag[i] >= 0 and mag[i + 1] < 0:
                # 线性插值
                ratio = -mag[i] / (mag[i + 1] - mag[i])
                crossover_f = freq[i] + ratio * (freq[i + 1] - freq[i])
                # 对应相位插值
                ph_at_cross = phase[i] + ratio * (phase[i + 1] - phase[i])
                phase_margin = 180 + ph_at_cross
                break

        if crossover_f is not None:
            lines.append(f"\n  穿越频率（0dB）：{crossover_f:.2f} Hz")
            lines.append(f"  相位裕度估算：{phase_margin:.1f}°")
            if phase_margin < 30:
                lines.append("  ⚠ 相位裕度偏低（<30°），系统接近不稳定")
            elif phase_margin < 45:
                lines.append("  ⚠ 相位裕度一般（30°~45°），建议优化补偿器")
            else:
                lines.append("  ✓ 相位裕度良好（≥45°）")
        else:
            lines.append("\n  （在扫描范围内未发现 0dB 穿越点）")

    # 输出前 8 个频率点的数据
    lines.append(f"\n  Bode 数据（前 {min(8, len(freq))} 点）：")
    lines.append(f"  {'频率 (Hz)':>12}  {'幅值 (dB)':>10}  {'相位 (°)':>10}")
    lines.append("  " + "─" * 38)
    for i in range(min(8, len(freq))):
        ph_str = f"{phase[i]:>10.2f}" if i < len(phase) else "    N/A"
        mg_str = f"{mag[i]:>10.2f}"   if i < len(mag)   else "    N/A"
        lines.append(f"  {freq[i]:>12.4g}  {mg_str}  {ph_str}")

    if len(freq) > 8:
        lines.append(f"  ... （共 {len(freq)} 点，已截断显示）")

    return "\n".join(lines)


def _format_impedance(result: dict, f_start: float, f_stop: float) -> str:
    """格式化阻抗扫描结果。"""
    if not result:
        return "阻抗扫描完成，但未收到数据。"

    freq = result.get("Frequency", [])
    mag  = result.get("Magnitude", [])   # Ω
    phase = result.get("Phase", [])      # deg

    lines = [
        "✓ 阻抗扫描完成",
        f"  频率范围：{f_start:.4g} Hz → {f_stop:.4g} Hz，{len(freq)} 个频率点",
    ]

    if mag:
        lines.append(f"  阻抗范围：{min(mag):.4g} Ω → {max(mag):.4g} Ω")

    lines.append(f"\n  {'频率 (Hz)':>12}  {'|Z| (Ω)':>10}  {'相位 (°)':>10}")
    lines.append("  " + "─" * 38)
    for i in range(min(8, len(freq))):
        ph_str = f"{phase[i]:>10.2f}" if i < len(phase) else "    N/A"
        mg_str = f"{mag[i]:>10.4g}"   if i < len(mag)   else "    N/A"
        lines.append(f"  {freq[i]:>12.4g}  {mg_str}  {ph_str}")

    if len(freq) > 8:
        lines.append(f"  ... （共 {len(freq)} 点）")

    return "\n".join(lines)
