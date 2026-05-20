"""
server.py  —  PLECS 4.7 MCP Server

MCP tool 与 PLECS XML-RPC 接口一一对应：

    plecs_connect   → 建立连接 (plecs.statistics 做健康检查)
    plecs_status    → plecs.statistics
    plecs_load      → plecs.load
    plecs_close     → plecs.close
    plecs_get       → plecs.get
    plecs_set       → plecs.set
    plecs_simulate  → plecs.simulate
    plecs_analyze   → plecs.analyze
    plecs_scope     → plecs.scope
    plecs_webserver → plecs.webserver
    plecs_codegen   → plecs.codegen

启动方式（通常由 AI Agent 自动启动，无需手动运行）：
    python server.py                   # stdio 模式
    python server.py --transport sse   # SSE 模式（远程 Agent）
"""

import os
import sys
import json
import argparse
import logging

import yaml
from mcp.server.fastmcp import FastMCP
from plecs_client import PlecsClient, PlecsError

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("plecs-mcp")

# ── 配置加载 ──────────────────────────────────────────────────────────────

def load_config() -> dict:
    cfg = {"host": "localhost", "port": 1080}
    cfg_path = os.path.join(os.path.dirname(__file__), "config.yml")
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding="utf-8") as f:
            file_cfg = yaml.safe_load(f) or {}
        cfg.update(file_cfg.get("plecs", {}))
    cfg["host"] = os.getenv("PLECS_HOST", cfg["host"])
    cfg["port"] = int(os.getenv("PLECS_PORT", cfg["port"]))
    return cfg

# ── Server 构建 ───────────────────────────────────────────────────────────

def build_server(cfg: dict) -> FastMCP:
    mcp = FastMCP(
        name="PLECS MCP Server",
        instructions="""
PLECS 4.7 仿真控制 MCP Server。

工具调用顺序：
  1. plecs_connect  — 每次会话开始时必须首先调用
  2. plecs_load     — 打开模型，拿到 model_name
  3. plecs_get / plecs_set — 读写参数（可选）
  4. plecs_simulate / plecs_analyze — 运行仿真或分析
  5. plecs_scope    — 读取/导出 Scope 数据（可选）
  6. plecs_close    — 完成后关闭模型

前置条件：PLECS Standalone 已启动，
Preferences → Simulation → "Start XML-RPC server" 已勾选（端口 1080）。
        """.strip(),
    )

    # 共享客户端单例
    _state: dict = {"client": None}

    def client() -> PlecsClient:
        c = _state["client"]
        if c is None:
            raise PlecsError("未连接到 PLECS，请先调用 plecs_connect")
        return c

    # ── plecs_connect ─────────────────────────────────────────────────────

    @mcp.tool()
    def plecs_connect(host: str = "", port: int = 0) -> str:
        """
        连接到正在运行的 PLECS 4.7 Standalone 实例。

        每次 Agent 会话开始时必须首先调用此工具。
        底层调用 plecs.statistics() 验证连接并获取版本信息。

        Args:
            host: PLECS 所在主机（留空则读 config.yml / 环境变量 PLECS_HOST）
            port: XML-RPC 端口（填 0 则读 config.yml / 环境变量 PLECS_PORT）

        Returns:
            连接成功：版本号、build 信息、当前已打开的模型列表。
            连接失败：错误原因和排查建议。
        """
        h = host or cfg["host"]
        p = port or cfg["port"]

        c = PlecsClient(host=h, port=p)
        try:
            stats = c.connect()
            _state["client"] = c
            models = stats.get("models") or []
            models_str = "、".join(models) if models else "（无）"
            return (
                f"✓ 已连接到 PLECS\n"
                f"  地址：{h}:{p}\n"
                f"  版本：{stats.get('version', '?')}  build：{stats.get('build', '?')}\n"
                f"  已打开模型：{models_str}"
            )
        except PlecsError as e:
            _state["client"] = None
            return (
                f"✗ 连接失败：{e}\n\n"
                f"排查步骤：\n"
                f"  1. 确认 PLECS Standalone 已启动\n"
                f"  2. PLECS → Preferences → Simulation → 勾选 \"Start XML-RPC server\"\n"
                f"  3. 确认端口为 {p}（PLECS 界面右下角会显示）\n"
                f"  4. 检查防火墙是否放行该端口"
            )

    # ── plecs_status ──────────────────────────────────────────────────────

    @mcp.tool()
    def plecs_status() -> str:
        """
        调用 plecs.statistics() 获取 PLECS 当前状态。

        无需参数。返回 PLECS 版本、build 信息、当前所有已打开的模型名称。
        可用于确认连接是否仍然有效，以及查看哪些模型处于打开状态。

        Returns:
            版本信息和已打开模型列表；若连接已断开则给出重连提示。
        """
        try:
            stats = client().statistics()
            models = stats.get("models") or []
            models_str = "\n".join(f"    • {m}" for m in models) if models else "    （无）"
            return (
                f"PLECS 状态\n"
                f"  版本：{stats.get('version', '?')}  build：{stats.get('build', '?')}\n"
                f"  已打开模型：\n{models_str}"
            )
        except PlecsError as e:
            return f"✗ {e}"

    # ── plecs_load ────────────────────────────────────────────────────────

    @mcp.tool()
    def plecs_load(path: str) -> str:
        """
        调用 plecs.load(path) 在 PLECS 中打开一个 .plecs 模型文件。

        Args:
            path: .plecs 文件的绝对路径。
                  Windows 示例："C:/models/buck_converter.plecs"
                  macOS 示例：  "/Users/me/models/buck_converter.plecs"

        Returns:
            成功：模型名称（后续所有工具调用中用此名称引用该模型）。
            失败：PLECS 返回的错误信息。
        """
        try:
            name = client().load(path)
            return (
                f"✓ 模型已打开\n"
                f"  名称：{name}\n"
                f"  路径：{path}\n"
                f"  后续请用 \"{name}\" 引用此模型"
            )
        except PlecsError as e:
            return f"✗ 打开模型失败：{e}"

    # ── plecs_close ───────────────────────────────────────────────────────

    @mcp.tool()
    def plecs_close(model_name: str) -> str:
        """
        调用 plecs.close(modelName) 关闭已打开的模型。

        注意：PLECS 不会自动保存未保存的修改。
        如需保留修改，请在调用此工具前先用 plecs_set 确认所有参数，
        或在 PLECS 界面中手动保存。

        Args:
            model_name: 要关闭的模型名称（来自 plecs_load 的返回值）

        Returns:
            操作结果确认。
        """
        try:
            client().close(model_name)
            return f"✓ 模型 \"{model_name}\" 已关闭"
        except PlecsError as e:
            return f"✗ 关闭失败：{e}"

    # ── plecs_get ─────────────────────────────────────────────────────────

    @mcp.tool()
    def plecs_get(path: str, param: str) -> str:
        """
        调用 plecs.get(path, param) 读取模型或组件的参数值。

        Args:
            path: 组件层级路径（用 "/" 分隔）。
                  "BuckConv"          → 读取模型级参数（如 "StopTime"）
                  "BuckConv/L1"       → 读取顶层组件参数（如 "L"）
                  "BuckConv/Ctrl/PID" → 读取子系统内组件参数

            param: 参数名称字符串。
                   模型级常用：StopTime、Ts、AbsTol、RelTol、Solver
                   组件常用：  L、C、R、V_init、I_init、f_sw、duty

        Returns:
            参数的当前值（字符串化输出）。
        """
        try:
            value = client().get(path, param)
            return f"{path}  →  {param} = {value}"
        except PlecsError as e:
            return f"✗ 读取失败：{e}"

    # ── plecs_set ─────────────────────────────────────────────────────────

    @mcp.tool()
    def plecs_set(path: str, param: str, value: str) -> str:
        """
        调用 plecs.set(path, param, value) 修改模型或组件的参数值。

        Args:
            path:  组件层级路径，格式同 plecs_get。
                   示例："BuckConv/L1"

            param: 参数名称。示例："L"、"R"、"StopTime"

            value: 新参数值（字符串）。
                   PLECS 会自动解析数值和表达式：
                   "47e-6"      → 47 μH
                   "220e-6"     → 220 μF
                   "Vin/2"      → 表达式（需模型中已定义 Vin）
                   "0.001"      → 1 ms

        Returns:
            修改确认，显示修改前后的值。
        """
        try:
            # 先读旧值做对比（可选，失败不影响主流程）
            try:
                old = client().get(path, param)
                old_str = f"（原值 {old}）"
            except Exception:
                old_str = ""

            client().set_param(path, param, value)
            return f"✓ 已修改\n  {path}  →  {param} = {value}  {old_str}"
        except PlecsError as e:
            return f"✗ 修改失败：{e}"

    # ── plecs_simulate ────────────────────────────────────────────────────

    @mcp.tool()
    def plecs_simulate(model_name: str, opts: str = "{}") -> str:
        """
        调用 plecs.simulate(modelName, opts) 运行时域仿真。

        Args:
            model_name: 已打开的模型名称（来自 plecs_load）。

            opts: JSON 字符串，仿真选项。支持以下键：

                ModelVars   (dict)   覆盖模型变量，对应模型初始化命令中的变量名。
                                     示例：{"Vin": 48, "R_load": 10, "f_sw": 100e3}

                StopTime    (float)  仿真结束时间（秒）
                MaxStep     (float)  最大步长（秒）
                MinStep     (float)  最小步长（秒）
                AbsTol      (float)  绝对容差（默认 1e-6）
                RelTol      (float)  相对容差（默认 1e-3）
                InitTimeStep(float)  初始步长
                Solver      (str)    求解器名称，如 "auto"、"ode45"、"ode23tb"
                Refine      (int)    输出点加密倍数

                示例：
                '{"ModelVars": {"Vin": 48, "R_load": 10}, "StopTime": 0.005}'

        Returns:
            仿真结果统计摘要：时间范围、时间点数、各输出通道的
            min / max / avg / pp（峰峰值）/ rms。
        """
        try:
            opts_dict = json.loads(opts)
        except json.JSONDecodeError as e:
            return f"✗ opts 格式错误（需合法 JSON）：{e}"

        try:
            result = client().simulate(model_name, opts_dict or None)
        except PlecsError as e:
            return f"✗ 仿真失败：{e}"

        return _fmt_sim(result, opts_dict.get("ModelVars"))

    # ── plecs_analyze ─────────────────────────────────────────────────────

    @mcp.tool()
    def plecs_analyze(model_name: str, analysis_type: str, opts: str = "{}") -> str:
        """
        调用 plecs.analyze(modelName, analysisType, opts) 运行频域/稳态分析。

        Args:
            model_name:    已打开的模型名称。

            analysis_type: 分析类型，必须与模型中 Analysis Tools 定义的名称完全一致：
                           "SteadyState"  稳态分析
                           "ACSweep"      AC 小信号扫频（Bode 图）
                           "FreqResp"     频率响应分析
                           "ImpulseResp"  脉冲响应分析
                           "Multitone"    多音分析

            opts: JSON 字符串，分析选项。ACSweep 常用键：
                  {
                    "SysName":      "loopgain",   分析对象名称（必填）
                    "FreqRange":    [10, 1e5],    频率范围（Hz）
                    "NumPoints":    50,           频率点数
                    "Amplitude":    0.01,         扰动幅值
                    "LogScale":     true,         对数频率分布
                    "SettlingTime": 0.001         稳定等待时间（秒）
                  }

        Returns:
            分析结果摘要。ACSweep 额外计算并显示穿越频率和相位裕度。
        """
        try:
            opts_dict = json.loads(opts)
        except json.JSONDecodeError as e:
            return f"✗ opts 格式错误：{e}"

        try:
            result = client().analyze(model_name, analysis_type, opts_dict)
        except PlecsError as e:
            return f"✗ 分析失败：{e}"

        return _fmt_analyze(result, analysis_type)

    # ── plecs_scope ───────────────────────────────────────────────────────

    @mcp.tool()
    def plecs_scope(scope_path: str, command: str, args: str = "[]") -> str:
        """
        调用 plecs.scope(scopePath, command, ...) 操作 Scope 组件。

        Args:
            scope_path: Scope 的完整层级路径。
                        示例："BuckConv/Scope"、"BuckConv/Control/VScope"

            command:    操作指令（大小写敏感）：
                        "ClearTraces"   清除所有波形轨迹（args 留空）
                        "HoldTrace"     保留当前波形（args 可传 ["标签名"]）
                        "SaveTrace"     保存当前波形（args 可传 ["标签名"]）
                        "ExportCSV"     导出 CSV（args 必须传 ["输出文件路径"]）
                        "ExportBitmap"  导出截图（args 必须传 ["输出文件路径"]）
                        "GetCursorData" 获取游标数据（args 传 [[t1, t2], "分析名"]）

            args: JSON 数组字符串，传给 command 的额外参数列表。
                  默认 "[]"（空列表，适用于 ClearTraces）。

                  ExportCSV 示例：   '["C:/results/wave.csv"]'
                  HoldTrace 示例：   '["R=10Ω"]'
                  GetCursorData 示例：'[[0.001, 0.002]]'

        Returns:
            操作结果。GetCursorData 返回游标区间内的数据统计。
        """
        try:
            extra = json.loads(args)
        except json.JSONDecodeError as e:
            return f"✗ args 格式错误（需合法 JSON 数组）：{e}"

        try:
            result = client().scope(scope_path, command, *extra)
        except PlecsError as e:
            return f"✗ scope {command} 失败：{e}"

        if result is None:
            return f"✓ scope {command} 完成：{scope_path}"

        return f"✓ scope {command} 完成：{scope_path}\n结果：{result}"

    # ── plecs_webserver ───────────────────────────────────────────────────

    @mcp.tool()
    def plecs_webserver(command: str, args: str = "[]") -> str:
        """
        调用 plecs.webserver(command, ...) 控制 PLECS Web 仿真服务器。

        PLECS Web Server 允许通过浏览器远程触发仿真，
        此工具用于在脚本中控制该服务器的启停。

        Args:
            command: "start" / "stop" / "status"
            args:    JSON 数组，命令相关参数（通常为空 "[]"）

        Returns:
            服务器操作结果或当前状态信息。
        """
        try:
            extra = json.loads(args)
        except json.JSONDecodeError as e:
            return f"✗ args 格式错误：{e}"

        try:
            result = client().webserver(command, *extra)
        except PlecsError as e:
            return f"✗ webserver {command} 失败：{e}"

        return f"✓ webserver {command}\n结果：{result}"

    # ── plecs_codegen ─────────────────────────────────────────────────────

    @mcp.tool()
    def plecs_codegen(model_name: str, opts: str = "{}") -> str:
        """
        调用 plecs.codegen(modelName, opts) 触发 PLECS 代码生成。

        在运行前，模型中须已配置好代码生成目标（Coder Options）。

        Args:
            model_name: 已打开的模型名称。

            opts: JSON 字符串，代码生成选项。常用键：
                  {
                    "GenerateCode": true,      是否生成代码（默认 true）
                    "BuildCode":    true,       是否编译代码
                    "RunCode":      false       是否运行生成的代码
                  }

        Returns:
            代码生成结果，包含输出目录和生成的文件列表（如 PLECS 返回此信息）。
        """
        try:
            opts_dict = json.loads(opts)
        except json.JSONDecodeError as e:
            return f"✗ opts 格式错误：{e}"

        try:
            result = client().codegen(model_name, opts_dict or None)
        except PlecsError as e:
            return f"✗ codegen 失败：{e}"

        if not result:
            return f"✓ codegen 完成：{model_name}"
        return f"✓ codegen 完成：{model_name}\n{json.dumps(result, ensure_ascii=False, indent=2)}"

    return mcp


# ── 结果格式化 ────────────────────────────────────────────────────────────

def _fmt_sim(result: dict, model_vars: dict | None = None) -> str:
    if not result:
        return "仿真完成，但无数据返回（模型中可能没有 Output 端口）"

    t = result.get("Time", [])
    if not t:
        return "仿真完成，Time 向量为空（仿真可能被中断）"

    lines = [
        "✓ 仿真完成",
        f"  时间：{t[0]:.6g} s → {t[-1]:.6g} s（{len(t)} 个点）",
    ]
    if model_vars:
        lines.append(f"  变量：{', '.join(f'{k}={v}' for k, v in model_vars.items())}")

    channels = result.get("Values", [])
    if not channels:
        lines.append("  （无数值输出通道，请确认模型有 Output 端口）")
        return "\n".join(lines)

    lines.append(f"\n  输出通道（共 {len(channels)} 个）：")
    header = f"  {'#':>3}  {'min':>10}  {'max':>10}  {'avg':>10}  {'pp':>10}  {'rms':>10}"
    lines.append(header)
    lines.append("  " + "─" * 58)

    for i, ch in enumerate(channels):
        if not ch:
            lines.append(f"  {i+1:>3}  （空）")
            continue
        mn, mx = min(ch), max(ch)
        avg = sum(ch) / len(ch)
        rms = (sum(x*x for x in ch) / len(ch)) ** 0.5
        lines.append(
            f"  {i+1:>3}  {mn:>10.4g}  {mx:>10.4g}  {avg:>10.4g}  {mx-mn:>10.4g}  {rms:>10.4g}"
        )
    return "\n".join(lines)


def _fmt_analyze(result: dict, analysis_type: str) -> str:
    if not result:
        return f"{analysis_type} 完成，但无数据返回"

    if analysis_type == "ACSweep":
        freq  = result.get("Frequencies", result.get("Frequency", []))
        mag   = result.get("Magnitude", [])
        phase = result.get("Phase", [])

        if not freq:
            return f"ACSweep 完成，无频率数据（检查模型中分析对象配置）"

        lines = [
            f"✓ ACSweep 完成",
            f"  频率范围：{freq[0]:.4g} Hz → {freq[-1]:.4g} Hz（{len(freq)} 点）",
        ]
        if mag:
            lines.append(f"  幅值范围：{min(mag):.2f} dB → {max(mag):.2f} dB")
        if phase:
            lines.append(f"  相位范围：{min(phase):.1f}° → {max(phase):.1f}°")

        # 穿越频率和相位裕度
        if mag and phase and len(mag) == len(freq):
            for i in range(len(mag) - 1):
                if mag[i] >= 0 > mag[i+1]:
                    r = -mag[i] / (mag[i+1] - mag[i])
                    fc = freq[i] + r * (freq[i+1] - freq[i])
                    pm = 180 + (phase[i] + r * (phase[i+1] - phase[i]))
                    lines.append(f"\n  穿越频率（0dB）：{fc:.2f} Hz")
                    lines.append(f"  相位裕度：{pm:.1f}°  {'✓ 良好(≥45°)' if pm>=45 else '⚠ 偏低(<45°)' if pm>=30 else '✗ 不足(<30°，系统接近不稳定)'}")
                    break
            else:
                lines.append("\n  （扫频范围内未发现 0dB 穿越点）")

        # Bode 数据表头
        lines.append(f"\n  {'频率(Hz)':>12}  {'幅值(dB)':>10}  {'相位(°)':>10}")
        lines.append("  " + "─" * 38)
        for i in range(min(10, len(freq))):
            mg_s = f"{mag[i]:>10.2f}" if i < len(mag) else "       N/A"
            ph_s = f"{phase[i]:>10.1f}" if i < len(phase) else "       N/A"
            lines.append(f"  {freq[i]:>12.4g}  {mg_s}  {ph_s}")
        if len(freq) > 10:
            lines.append(f"  ...（共 {len(freq)} 点）")

        return "\n".join(lines)

    # 其他分析类型：直接 JSON 输出
    return f"✓ {analysis_type} 完成\n{json.dumps(result, ensure_ascii=False, indent=2)}"


# ── CLI 入口 ──────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="PLECS 4.7 MCP Server")
    p.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    p.add_argument("--host", default="127.0.0.1", help="SSE 监听地址")
    p.add_argument("--port", type=int, default=8765, help="SSE 监听端口")
    return p.parse_args()


def main():
    args = parse_args()
    cfg  = load_config()
    mcp  = build_server(cfg)
    logger.info("PLECS MCP Server 启动（%s）", args.transport)
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="sse", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
