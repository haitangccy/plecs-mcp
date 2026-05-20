"""
plecs_client.py  —  PLECS 4.7 XML-RPC 客户端

严格按照 PLECS 暴露的 10 个 RPC 接口封装，不做额外抽象：
    system.listMethods   → list_methods()
    system.methodHelp    → method_help()
    plecs.statistics     → statistics()
    plecs.load           → load()
    plecs.close          → close()
    plecs.get            → get()
    plecs.set            → set_param()
    plecs.simulate       → simulate()
    plecs.analyze        → analyze()
    plecs.scope          → scope()
    plecs.webserver      → webserver()
    plecs.codegen        → codegen()
"""

import xmlrpc.client
import socket
import logging
from typing import Any

logger = logging.getLogger(__name__)


class PlecsError(RuntimeError):
    """PLECS XML-RPC 调用失败"""


class PlecsClient:
    def __init__(self, host: str = "localhost", port: int = 1080):
        self.host = host
        self.port = port
        self._proxy: xmlrpc.client.ServerProxy | None = None

    # ── 连接 ─────────────────────────────────────────────────────────────

    def connect(self) -> dict:
        """
        建立连接并返回 plecs.statistics() 结果。
        成功时返回含 'version'、'build' 等字段的 dict；失败抛 PlecsError。
        """
        try:
            self._proxy = xmlrpc.client.ServerProxy(
                f"http://{self.host}:{self.port}/RPC2",
                allow_none=True,
            )
            stats = self._proxy.plecs.statistics()
            logger.info("已连接 PLECS %s @ %s:%d", stats.get("version"), self.host, self.port)
            return dict(stats)
        except (ConnectionRefusedError, socket.gaierror, OSError) as e:
            self._proxy = None
            raise PlecsError(f"无法连接到 {self.host}:{self.port} — {e}") from e
        except xmlrpc.client.Fault as e:
            self._proxy = None
            raise PlecsError(f"plecs.statistics() 调用失败 — {e.faultString}") from e

    def is_connected(self) -> bool:
        if self._proxy is None:
            return False
        try:
            self._proxy.plecs.statistics()
            return True
        except Exception:
            return False

    def _call(self, method: str, *args) -> Any:
        """执行任意 RPC 调用，统一转换错误类型。"""
        if self._proxy is None:
            raise PlecsError("未连接到 PLECS，请先调用 plecs_connect")
        try:
            parts = method.split(".")
            obj = self._proxy
            for p in parts:
                obj = getattr(obj, p)
            return obj(*args)
        except xmlrpc.client.Fault as e:
            raise PlecsError(f"[{method}] 失败：{e.faultString}") from e
        except (ConnectionRefusedError, socket.gaierror, OSError) as e:
            self._proxy = None
            raise PlecsError(f"连接已断开：{e}") from e

    # ── system.* ─────────────────────────────────────────────────────────

    def list_methods(self) -> list[str]:
        """system.listMethods — 返回 PLECS 暴露的所有 RPC 方法名列表。"""
        return list(self._call("system.listMethods"))

    def method_help(self, method_name: str) -> str:
        """system.methodHelp — 返回指定方法的帮助文本。"""
        return str(self._call("system.methodHelp", method_name))

    # ── plecs.statistics ─────────────────────────────────────────────────

    def statistics(self) -> dict:
        """
        plecs.statistics() — 返回 PLECS 实例的全局统计信息。

        返回字段（实测 4.7.4）：
            version   : str   如 "4.7.4"
            build     : str   如 "4f3b445a 15.06.2023 16:17"
            models    : list  当前已打开的模型名称列表
        """
        result = self._call("plecs.statistics")
        return dict(result) if result else {}

    # ── plecs.load / plecs.close ─────────────────────────────────────────

    def load(self, path: str) -> str:
        """
        plecs.load(path) — 打开 .plecs 文件。

        Args:
            path: 文件绝对路径，如 "C:/models/buck.plecs"

        Returns:
            模型名称字符串（不含路径和扩展名）
        """
        result = self._call("plecs.load", path)
        return str(result) if result else _name_from_path(path)

    def close(self, model_name: str) -> None:
        """
        plecs.close(modelName) — 关闭已打开的模型（不自动保存）。

        Args:
            model_name: 模型名称，来自 load() 的返回值
        """
        self._call("plecs.close", model_name)

    # ── plecs.get / plecs.set ────────────────────────────────────────────

    def get(self, path: str, param: str) -> Any:
        """
        plecs.get(path, param) — 读取组件或模型参数。

        Args:
            path:  组件层级路径。
                   ""              → 不支持（用 statistics() 读全局信息）
                   "ModelName"     → 模型级参数，如 "StopTime"、"Ts"
                   "ModelName/C1"  → 组件参数，如 "C"、"V_init"

            param: 参数名称字符串

        Returns:
            参数值，类型取决于 PLECS 返回内容（str / float / list / dict）
        """
        return self._call("plecs.get", path, param)

    def set_param(self, path: str, param: str, value: Any) -> None:
        """
        plecs.set(path, param, value) — 修改组件或模型参数。

        Args:
            path:  同 get()
            param: 参数名称
            value: 新值（str / float / int，PLECS 会自动解析表达式字符串）
        """
        self._call("plecs.set", path, param, value)

    # ── plecs.simulate ───────────────────────────────────────────────────

    def simulate(self, model_name: str, opts: dict | None = None) -> dict:
        """
        plecs.simulate(modelName, opts) — 运行时域仿真。

        Args:
            model_name: 已加载的模型名称
            opts: 可选仿真选项 dict，支持以下键：

                ModelVars    : dict  覆盖模型变量，如 {"Vin": 48, "R": 10}
                StopTime     : float 仿真结束时间（秒）
                MaxStep      : float 最大步长
                MinStep      : float 最小步长
                AbsTol       : float 绝对容差
                RelTol       : float 相对容差
                InitTimeStep : float 初始步长
                Solver       : str   求解器，如 "auto"、"ode45"
                Refine       : int   输出加密倍数

        Returns:
            dict，包含：
                "Time"   : list[float]        时间向量
                "Values" : list[list[float]]  各 Output 端口的数据
        """
        args = [model_name, opts or {}]
        result = self._call("plecs.simulate", *args)
        return dict(result) if result else {}

    # ── plecs.analyze ────────────────────────────────────────────────────

    def analyze(self, model_name: str, analysis_type: str, opts: dict) -> dict:
        """
        plecs.analyze(modelName, analysisType, opts) — 运行频域/稳态分析。

        Args:
            model_name:    已加载的模型名称
            analysis_type: 分析类型字符串，必须与模型中定义的分析名称一致：
                           "SteadyState"  稳态分析
                           "ACSweep"      AC 小信号扫频
                           "FreqResp"     频率响应
                           "Multitone"    多音分析
                           "ImpulseResp"  脉冲响应

            opts: 分析选项 dict，不同分析类型支持不同键。
                  ACSweep 常用键：
                      SysName    : str           分析对象名称（必填）
                      FreqRange  : [f_min, f_max] 频率范围（Hz）
                      NumPoints  : int            频率点数
                      Amplitude  : float          扰动幅值
                      LogScale   : bool           对数分布
                      SettlingTime: float         稳定等待时间

        Returns:
            dict，ACSweep 返回：
                "Frequencies" : list[float]  频率点（Hz）
                "Magnitude"   : list[float]  幅频（dB）
                "Phase"       : list[float]  相频（°）
        """
        result = self._call("plecs.analyze", model_name, analysis_type, opts)
        return dict(result) if result else {}

    # ── plecs.scope ──────────────────────────────────────────────────────

    def scope(self, scope_path: str, command: str, *args) -> Any:
        """
        plecs.scope(scopePath, command, ...) — Scope 操作。

        Args:
            scope_path: Scope 组件路径，如 "ModelName/Scope"
            command:    操作指令字符串（大小写敏感）：
                        "ClearTraces"   清除所有波形轨迹
                        "HoldTrace"     保留当前波形（可选 label 参数）
                        "SaveTrace"     保存当前波形（可选 label 参数）
                        "ExportCSV"     导出 CSV（需传 filename 参数）
                        "ExportBitmap"  导出位图截图（需传 filename 参数）
                        "GetCursorData" 获取游标数据（需传时间范围参数）
            *args:      命令所需的额外参数（见 command 说明）

        Returns:
            依命令不同返回 None 或数据 dict
        """
        return self._call("plecs.scope", scope_path, command, *args)

    # ── plecs.webserver ──────────────────────────────────────────────────

    def webserver(self, command: str, *args) -> Any:
        """
        plecs.webserver(command, ...) — 控制 PLECS Web 仿真服务器。

        Args:
            command: "start" / "stop" / "status"
            *args:   命令相关参数

        Returns:
            依命令返回状态信息
        """
        return self._call("plecs.webserver", command, *args)

    # ── plecs.codegen ────────────────────────────────────────────────────

    def codegen(self, model_name: str, opts: dict | None = None) -> dict:
        """
        plecs.codegen(modelName, opts) — 触发代码生成。

        Args:
            model_name: 已加载的模型名称
            opts:       代码生成选项 dict（参见 PLECS 手册 Code Generation 章节）

        Returns:
            代码生成结果信息 dict
        """
        result = self._call("plecs.codegen", model_name, opts or {})
        return dict(result) if result else {}


# ── 工具函数 ──────────────────────────────────────────────────────────────

def _name_from_path(path: str) -> str:
    import os
    return os.path.splitext(os.path.basename(path.replace("\\", "/")))[0]
