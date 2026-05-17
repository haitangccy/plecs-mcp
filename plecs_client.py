"""
plecs_client.py
---------------
PLECS 4.7 Standalone XML-RPC 客户端封装层。

PLECS Standalone 在 Preferences → Simulation 中开启 XML-RPC Server 后，
默认在 localhost:1080 监听，所有命令以 plecs.<cmd>(...) 形式调用。
"""

import xmlrpc.client
import socket
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PlecsConnectionError(RuntimeError):
    """无法连接到 PLECS 实例时抛出"""


class PlecsRPCError(RuntimeError):
    """PLECS XML-RPC 调用失败时抛出"""


class PlecsClient:
    """
    PLECS Standalone XML-RPC 客户端。

    用法::

        client = PlecsClient(host="localhost", port=1080)
        client.connect()
        model = client.load_model("C:/models/buck.plecs")
        result = client.simulate(model, model_vars={"Vin": 48})
        client.close_model(model)
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1080,
        timeout: int = 300,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.url = f"http://{host}:{port}/RPC2"
        self._proxy: Optional[xmlrpc.client.ServerProxy] = None

    # ── 连接管理 ────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """建立到 PLECS 的 XML-RPC 连接。返回 True 表示成功。"""
        try:
            self._proxy = xmlrpc.client.ServerProxy(
                self.url,
                allow_none=True,
            )
            self._proxy.plecs.get("", "Version")
            logger.info("已连接到 PLECS（%s）", self.url)
            return True
        except (ConnectionRefusedError, socket.gaierror, socket.timeout) as exc:
            logger.warning("连接 PLECS 失败：%s", exc)
            self._proxy = None
            return False
        except xmlrpc.client.Fault as exc:
            # PLECS 响应了说明服务在运行，"Version" 命令格式问题可忽略
            if self._proxy is not None:
                logger.info("PLECS 已响应，视为连接成功（%s）", exc)
                return True
            return False

    def disconnect(self) -> None:
        """断开连接并释放资源。"""
        self._proxy = None
        logger.info("已断开 PLECS 连接")

    def is_connected(self) -> bool:
        """检查当前是否有活跃连接。"""
        if self._proxy is None:
            return False
        try:
            self._proxy.plecs.get("", "Version")
            return True
        except Exception:
            return False

    def get_version(self) -> str:
        """返回 PLECS 版本字符串。"""
        return str(self._call("plecs.get", "", "Version"))

    @property
    def proxy(self) -> xmlrpc.client.ServerProxy:
        if self._proxy is None:
            raise PlecsConnectionError(
                "尚未连接到 PLECS。请先调用 plecs_connect 工具，"
                "并确认 PLECS Standalone 已启动且 XML-RPC 接口已开启。"
            )
        return self._proxy

    # ── 内部调用辅助 ────────────────────────────────────────────────────

    def _call(self, method: str, *args) -> Any:
        """执行 XML-RPC 调用，统一做错误转换。"""
        try:
            parts = method.split(".")
            obj = self.proxy
            for part in parts:
                obj = getattr(obj, part)
            return obj(*args)
        except xmlrpc.client.Fault as exc:
            raise PlecsRPCError(
                f"PLECS 命令 [{method}] 执行失败：{exc.faultString}"
            ) from exc
        except (ConnectionRefusedError, socket.gaierror) as exc:
            self._proxy = None
            raise PlecsConnectionError(
                f"与 PLECS 的连接已断开：{exc}"
            ) from exc

    # ── 模型操作 ────────────────────────────────────────────────────────

    def load_model(self, path: str) -> str:
        """
        打开 .plecs 文件，返回模型名称（后续命令用此名称引用模型）。
        """
        result = self._call("plecs.load", path)
        model_name = str(result) if result else _model_name_from_path(path)
        logger.info("已加载模型：%s", model_name)
        return model_name

    def save_model(self, model_name: str) -> None:
        """保存已打开的模型。"""
        self._call("plecs.save", model_name)
        logger.info("已保存模型：%s", model_name)

    def close_model(self, model_name: str) -> None:
        """关闭已打开的模型（不自动保存）。"""
        self._call("plecs.close", model_name)
        logger.info("已关闭模型：%s", model_name)

    # ── 参数读写 ────────────────────────────────────────────────────────

    def get_param(self, comp_path: str, param: str) -> Any:
        """
        读取组件参数。

        comp_path 示例::

            ""             → PLECS 全局属性（"Version" 等）
            "BuckConv"     → 模型级属性（"SimulationTime" 等）
            "BuckConv/L1"  → 组件参数（"L" 等）
        """
        return self._call("plecs.get", comp_path, param)

    def set_param(self, comp_path: str, param: str, value: Any) -> None:
        """
        修改组件参数。value 可以是数值、字符串或表达式字符串。
        """
        self._call("plecs.set", comp_path, param, value)
        logger.debug("设置 %s.%s = %s", comp_path, param, value)

    # ── 仿真控制 ────────────────────────────────────────────────────────

    def simulate(
        self,
        model_name: str,
        model_vars: Optional[dict] = None,
        solver_opts: Optional[dict] = None,
    ) -> dict:
        """
        运行时域仿真。

        Args:
            model_name:  已加载的模型名称。
            model_vars:  覆盖模型变量，例如 ``{"Vin": 48, "R_load": 10}``。
                         对应模型初始化命令中定义的变量名。
            solver_opts: 仿真选项，支持以下键：

                         - ``StopTime``      仿真结束时间（秒）
                         - ``MaxStep``       最大步长
                         - ``MinStep``       最小步长
                         - ``AbsTol``        绝对容差
                         - ``RelTol``        相对容差
                         - ``InitTimeStep``  初始步长
                         - ``SolverMethod``  求解器（"auto"/"ode45" 等）
                         - ``Refine``        输出加密倍数

        Returns:
            dict，包含 ``"Time"`` (list[float]) 和 ``"Values"`` (list[list[float]])。
        """
        opts: dict = {}
        if model_vars:
            opts["ModelVars"] = model_vars
        if solver_opts:
            opts.update(solver_opts)

        logger.info("开始仿真：%s，选项：%s", model_name, opts)
        result = self._call("plecs.simulate", model_name, opts)
        logger.info("仿真完成：%s", model_name)
        return result if isinstance(result, dict) else {}

    # ── 分析功能 ────────────────────────────────────────────────────────

    def analyze(
        self,
        model_name: str,
        analysis_type: str,
        opts: dict,
    ) -> dict:
        """
        运行频域分析。

        analysis_type 可选值：

        - ``"ACSweep"``        AC 小信号扫频（Bode 图）
        - ``"ImpedanceSweep"`` 阻抗扫频
        - ``"TrFunction"``     传递函数提取

        ACSweep opts 常用键::

            FreqRange   : [f_start, f_stop]   单位 Hz
            NumPoints   : int                 频率点数
            Amplitude   : float               扰动幅值
            SteadyState : bool                先跑到稳态再扫频
        """
        logger.info("运行分析：%s / %s，选项：%s", model_name, analysis_type, opts)
        result = self._call("plecs.analyze", model_name, analysis_type, opts)
        return result if isinstance(result, dict) else {}

    # ── Scope 操作 ──────────────────────────────────────────────────────

    def scope_clear(self, scope_path: str) -> None:
        """清除 Scope 中的所有波形轨迹。"""
        self._call("plecs.scope", scope_path, "ClearTraces")

    def scope_hold_trace(self, scope_path: str, label: str = "") -> None:
        """保留当前波形轨迹（叠加多次仿真结果时使用）。"""
        self._call("plecs.scope", scope_path, "HoldTrace", label)

    def scope_export_csv(self, scope_path: str, output_path: str) -> None:
        """将 Scope 波形数据导出为 CSV 文件。"""
        self._call("plecs.scope", scope_path, "ExportCSV", output_path)

    def scope_export_image(self, scope_path: str, output_path: str) -> None:
        """将 Scope 截图导出为图片（支持 PNG/SVG）。"""
        self._call("plecs.scope", scope_path, "ExportBitmap", output_path)

    # ── 便捷工具 ────────────────────────────────────────────────────────

    def list_components(self, model_name: str) -> list:
        """列举模型顶层的所有组件名称。"""
        try:
            result = self._call("plecs.get", model_name, "Components")
            return list(result) if result else []
        except PlecsRPCError:
            return []


# ── 辅助函数 ─────────────────────────────────────────────────────────────

def _model_name_from_path(path: str) -> str:
    """从文件路径提取不含扩展名的模型名。"""
    import os
    return os.path.splitext(os.path.basename(path))[0]
