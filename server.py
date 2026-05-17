"""
server.py
---------
PLECS 4.7 MCP Server 主入口。

启动方式：
    python server.py                          # 默认 stdio 传输（供 AI agent 调用）
    python server.py --transport sse          # SSE 传输（HTTP 服务模式）
    python server.py --host 127.0.0.1 --port 8765

环境变量（可选，优先级高于 config.yml）：
    PLECS_HOST    PLECS XML-RPC 主机（默认 localhost）
    PLECS_PORT    PLECS XML-RPC 端口（默认 1080）
    PLECS_TIMEOUT 仿真超时秒数（默认 300）
    LOG_LEVEL     日志级别（DEBUG / INFO / WARNING，默认 INFO）
"""

import os
import sys
import argparse
import logging
import yaml

from mcp.server.fastmcp import FastMCP
from plecs_client import PlecsClient, PlecsConnectionError
from tools import (
    register_model_tools,
    register_simulation_tools,
    register_data_tools,
)

# ── 日志配置 ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("plecs-mcp")


# ── 配置加载 ────────────────────────────────────────────────────────────

def load_config(config_path: str = None) -> dict:
    """加载 config/config.yml，环境变量覆盖文件设置。"""
    defaults = {
        "plecs": {
            "host":    "localhost",
            "port":    1080,
            "timeout": 300,
        }
    }

    cfg_file = config_path or os.path.join(
        os.path.dirname(__file__), "config", "config.yml"
    )

    if os.path.exists(cfg_file):
        with open(cfg_file, "r", encoding="utf-8") as f:
            file_cfg = yaml.safe_load(f) or {}
        # 深合并
        for section, values in file_cfg.items():
            if section in defaults and isinstance(values, dict):
                defaults[section].update(values)
            else:
                defaults[section] = values

    # 环境变量覆盖
    if os.getenv("PLECS_HOST"):
        defaults["plecs"]["host"] = os.getenv("PLECS_HOST")
    if os.getenv("PLECS_PORT"):
        defaults["plecs"]["port"] = int(os.getenv("PLECS_PORT"))
    if os.getenv("PLECS_TIMEOUT"):
        defaults["plecs"]["timeout"] = int(os.getenv("PLECS_TIMEOUT"))

    return defaults


# ── MCP Server 构建 ─────────────────────────────────────────────────────

def build_server(config: dict) -> FastMCP:
    """初始化 FastMCP 实例并注册所有工具。"""

    mcp = FastMCP(
        name="PLECS MCP Server",
        instructions="""
你正在通过 MCP 工具与 PLECS 4.7 Standalone 交互，用于电力电子仿真。

工作流程（必须按顺序执行）：
1. 调用 plecs_connect    → 建立与 PLECS 的连接（每次会话开始时执行一次）
2. 调用 plecs_load_model → 打开 .plecs 模型文件，获取模型名称
3. 根据需要调用参数读写工具（plecs_get_param / plecs_set_param / plecs_batch_set_params）
4. 调用仿真工具（plecs_run_simulation / plecs_parameter_sweep / plecs_ac_sweep）
5. 调用数据导出工具（plecs_export_scope_csv / plecs_export_scope_image）
6. 完成后调用 plecs_close_model 关闭模型

关键约定：
- 所有组件路径使用正斜杠分隔，格式：ModelName/SubSystem/ComponentName
- model_vars 必须是合法 JSON 字符串，例如 '{"Vin": 48, "R": 10}'
- 修改参数后记得调用 plecs_save_model 保存
- PLECS 须已启动并在 Preferences→Simulation 中开启 XML-RPC Server（端口 1080）
        """.strip(),
    )

    # 共享的 PlecsClient 单例
    _client: dict = {"instance": None}

    def get_client() -> PlecsClient:
        """获取当前 PlecsClient，未连接时抛出清晰错误。"""
        client = _client["instance"]
        if client is None or not client.is_connected():
            raise PlecsConnectionError(
                "未连接到 PLECS。请先调用 plecs_connect 工具建立连接。"
            )
        return client

    # ── 内置工具：连接管理 ────────────────────────────────────────────────

    @mcp.tool()
    def plecs_connect(
        host: str = None,
        port: int = None,
    ) -> str:
        """
        连接到正在运行的 PLECS 4.7 Standalone 实例。

        每次 Agent 会话开始时必须首先调用此工具。
        连接成功后 PLECS 的状态（已打开的模型、工作区）保持不变。

        前置条件：
          - PLECS Standalone 已启动；
          - PLECS → Preferences → Simulation → 勾选 "Start XML-RPC server"；
          - 端口默认为 1080（可在 Preferences 中修改）。

        Args:
            host: PLECS 所在主机地址，默认读取 config.yml 或环境变量 PLECS_HOST，
                  通常为 "localhost"。
            port: XML-RPC 端口，默认读取 config.yml 或环境变量 PLECS_PORT，
                  通常为 1080。

        Returns:
            连接状态信息，包含 PLECS 版本号。
        """
        plecs_cfg = config["plecs"]
        h = host or plecs_cfg["host"]
        p = port or plecs_cfg["port"]
        t = plecs_cfg["timeout"]

        client = PlecsClient(host=h, port=p, timeout=t)
        ok = client.connect()

        if ok:
            _client["instance"] = client
            try:
                version = client.get_version()
            except Exception:
                version = "（版本号读取失败）"
            logger.info("PLECS 连接成功：%s:%d，版本 %s", h, p, version)
            return (
                f"✓ 已连接到 PLECS\n"
                f"  地址：{h}:{p}\n"
                f"  版本：{version}\n"
                f"  超时：{t}s\n"
                f"  下一步：调用 plecs_load_model 打开模型文件"
            )
        else:
            _client["instance"] = None
            return (
                f"✗ 连接失败（{h}:{p}）\n\n"
                f"请检查：\n"
                f"  1. PLECS Standalone 是否已启动\n"
                f"  2. PLECS → Preferences → Simulation → "
                f"\"Start XML-RPC server\" 是否已勾选\n"
                f"  3. 端口是否为 {p}（可在 Preferences 中确认）\n"
                f"  4. 防火墙是否阻止了 {p} 端口"
            )

    @mcp.tool()
    def plecs_status() -> str:
        """
        检查当前 PLECS 连接状态和版本信息。

        无需参数，随时可调用。若连接已断开会给出重连提示。

        Returns:
            连接状态、PLECS 版本和地址信息。
        """
        client = _client.get("instance")
        if client is None:
            return "未连接。请调用 plecs_connect 建立连接。"

        if client.is_connected():
            try:
                version = client.get_version()
            except Exception:
                version = "（读取失败）"
            return (
                f"✓ 连接正常\n"
                f"  地址：{client.host}:{client.port}\n"
                f"  版本：{version}"
            )
        else:
            _client["instance"] = None
            return (
                f"✗ 连接已断开（{client.host}:{client.port}）\n"
                f"请重新调用 plecs_connect 建立连接。"
            )

    # ── 注册各功能模块的工具 ─────────────────────────────────────────────

    register_model_tools(mcp, get_client)
    register_simulation_tools(mcp, get_client)
    register_data_tools(mcp, get_client)

    logger.info(
        "MCP Server 初始化完成，已注册 %d 个工具",
        len([t for t in dir(mcp) if not t.startswith("_")]),
    )

    return mcp


# ── CLI 入口 ────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="PLECS 4.7 MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python server.py                           # stdio 模式（供 Claude Code 等直接调用）
  python server.py --transport sse           # SSE 模式（HTTP 服务，供远程 Agent 连接）
  python server.py --transport sse --port 8765
  PLECS_HOST=192.168.1.100 python server.py  # 连接远程 PLECS 实例
        """,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP 传输方式：stdio（默认，供本地 Agent 调用）或 sse（HTTP 服务模式）",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="SSE 模式下的监听地址（默认 127.0.0.1）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="SSE 模式下的监听端口（默认 8765）",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="config.yml 路径（默认 ./config/config.yml）",
    )
    return parser.parse_args()


def main():
    args   = parse_args()
    config = load_config(args.config)
    mcp    = build_server(config)

    logger.info(
        "启动 PLECS MCP Server（传输：%s）",
        args.transport,
    )

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="sse", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
