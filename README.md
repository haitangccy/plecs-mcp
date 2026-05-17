# PLECS MCP Server

> AI Agent 直接驱动 PLECS 4.7 Standalone 进行电力电子仿真的 MCP 服务

参考 MathWorks 的 MATLAB MCP Core Server + Simulink Agentic Toolkit 方案，
本项目为 PLECS 4.7 提供等效的 MCP 接入层，让 Claude Code、Copilot 等 AI Agent
可以直接操作 PLECS 模型、运行仿真、做频域分析，无需手动复制粘贴。

```
┌───────────────┐        ┌──────────────────┐        ┌──────────────────┐
│   AI Agent    │◄─MCP──►│  PLECS MCP Server │◄──────►│  PLECS 4.7       │
│ (Claude Code, │        │  (本项目, Python) │ XML-RPC│  Standalone      │
│  Copilot 等)  │        └──────────────────┘  :1080  └──────────────────┘
└───────────────┘                ▲
                                 │ reads
                          ┌──────┴──────┐
                          │   Skills    │
                          │ (电力电子   │
                          │ 最佳实践)   │
                          └─────────────┘
```

---

## 快速开始

### 1. 前置条件

- Python 3.10+
- PLECS 4.7 Standalone（需有效许可证）
- 支持 MCP 的 AI Agent（Claude Code、GitHub Copilot 等）

### 2. 安装

```bash
git clone https://github.com/your-org/plecs-mcp.git
cd plecs-mcp
pip install -e .
```

### 3. 开启 PLECS XML-RPC 接口

在 PLECS 中：
**Preferences → Simulation → 勾选 "Start XML-RPC server" → 端口保持 1080 → 点击 OK**

> 每次启动 PLECS 后此设置会自动生效，无需重复操作。

### 4. 配置 AI Agent

编辑 Agent 的 MCP 配置文件，加入 PLECS MCP Server：

**Claude Code** (`~/.claude/mcp.json` 或 `.claude/mcp.json`):
```json
{
  "mcpServers": {
    "plecs": {
      "command": "python",
      "args": ["/absolute/path/to/plecs-mcp/server.py"],
      "env": {
        "PLECS_HOST": "localhost",
        "PLECS_PORT": "1080"
      }
    }
  }
}
```

**VS Code / GitHub Copilot** (`.vscode/mcp.json`):
```json
{
  "servers": {
    "plecs": {
      "type": "stdio",
      "command": "python",
      "args": ["/absolute/path/to/plecs-mcp/server.py"]
    }
  }
}
```

**Cursor** (`~/.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "plecs": {
      "command": "python",
      "args": ["/absolute/path/to/plecs-mcp/server.py"]
    }
  }
}
```

### 5. 验证安装

重启 Agent 会话后，让 Agent 执行：

```
调用 plecs_connect，然后告诉我 PLECS 的版本号
```

若返回版本号（如 `4.7.0`），说明配置成功。

---

## MCP 工具列表

| 工具名 | 功能 | 何时使用 |
|--------|------|----------|
| `plecs_connect` | 连接到 PLECS XML-RPC 接口 | 每次 Agent 会话开始时 |
| `plecs_status` | 检查连接状态 | 排查连接问题时 |
| `plecs_load_model` | 打开 .plecs 模型文件 | 开始操作模型前 |
| `plecs_save_model` | 保存模型 | 修改参数后 |
| `plecs_close_model` | 关闭模型 | 完成工作后 |
| `plecs_get_param` | 读取组件参数 | 查询当前参数值 |
| `plecs_set_param` | 修改单个参数 | 修改单个组件参数 |
| `plecs_batch_set_params` | 批量修改参数 | 同时修改多个参数（效率更高）|
| `plecs_list_components` | 列举模型组件 | 了解模型结构 |
| `plecs_run_simulation` | 运行时域仿真 | 时域波形分析 |
| `plecs_parameter_sweep` | 参数扫描仿真 | 设计空间探索 |
| `plecs_ac_sweep` | AC 小信号扫频 | Bode 图、相位裕度分析 |
| `plecs_impedance_sweep` | 阻抗扫描 | 输入/输出阻抗特性 |
| `plecs_export_scope_csv` | 导出 Scope 波形 CSV | 获取原始仿真数据 |
| `plecs_export_scope_image` | 导出 Scope 截图 | 保存波形图片 |
| `plecs_scope_clear` | 清除 Scope 波形 | 叠加对比前清空 |
| `plecs_scope_hold_trace` | 保留 Scope 波形 | 多次仿真叠加显示 |
| `plecs_compare_simulations` | 多场景仿真对比 | 不同工况对比分析 |

---

## 使用示例

### 示例 1：Buck 变换器参数分析

向 Agent 发送：

```
帮我分析一下 BuckConverter 模型：
1. 加载 C:/models/buck_converter.plecs
2. 读取电感 L1 和电容 C1 的参数值
3. 运行仿真，输入电压 Vin=48V，负载 R_load=10Ω
4. 告诉我输出电压的平均值和纹波
```

### 示例 2：环路增益 Bode 图

```
对 BuckConverter 做 AC Sweep 分析：
- 频率范围 10Hz ~ 500kHz
- 50 个频率点
- 分析名称 "loopgain"
- 告诉我穿越频率和相位裕度
```

### 示例 3：负载步进仿真

```
对 BuckConverter 做负载步进测试：
先清空 Scope，然后分别在 R_load = 5Ω、10Ω、20Ω、50Ω 下仿真，
每次仿真后保留波形（用负载值作标签），最后导出叠加波形图片。
```

---

## 组件路径格式说明

PLECS 的组件路径使用正斜杠层级格式：

```
模型名/子系统名/组件名

示例：
  BuckConverter                     → 模型本身（读写模型级属性）
  BuckConverter/L1                  → 顶层电感 L1
  BuckConverter/Control             → 控制子系统
  BuckConverter/Control/PIDBlock    → 控制子系统内的 PID 块
  BuckConverter/Scope               → 顶层 Scope
```

---

## 仿真变量 vs 参数的区别

| 类型 | 设置方式 | 说明 |
|------|----------|------|
| **模型变量** | `plecs_run_simulation` 的 `model_vars` 参数 | 在模型"初始化命令"中定义的 MATLAB 变量，如 `Vin=48` |
| **组件参数** | `plecs_set_param` 工具 | 直接设置在组件属性对话框中，如电感值 `L=47e-6` |

建议：设计阶段用**模型变量**（仿真不保存到文件），确定设计后用 `plecs_set_param` + `plecs_save_model` 固化到文件。

---

## 配置说明

编辑 `config/config.yml`：

```yaml
plecs:
  host: "localhost"   # PLECS 所在主机
  port: 1080          # XML-RPC 端口
  timeout: 300        # 仿真超时（秒）
  executable: ""      # PLECS 可执行文件路径（可选）

server:
  log_level: "INFO"   # 日志级别
```

所有配置均可被环境变量覆盖：`PLECS_HOST`、`PLECS_PORT`、`PLECS_TIMEOUT`。

---

## 运行测试

```bash
# 安装测试依赖
pip install -e ".[dev]"

# 运行所有测试（无需 PLECS，使用 Mock）
pytest tests/ -v

# 运行指定测试文件
pytest tests/test_plecs_client.py -v
pytest tests/test_mcp_tools.py -v
```

---

## 下一步：PLECS Simulation Toolkit

本仓库仅包含 MCP Server（对应 MATLAB MCP Core Server）。
配套的 **PLECS Simulation Toolkit**（对应 Simulink Agentic Toolkit）正在开发中，将提供：

- `skills/` — 电力电子设计最佳实践（Buck/Boost/Flyback/Inverter 拓扑指导）
- **模型生成工具** — AI 直接生成 `.plecs` XML 文件，从自然语言到仿真模型

---

## 许可证

MIT License — 仅限配合合法的 PLECS 许可证使用。
PLECS® 是 Plexim GmbH 的注册商标。
