# PLECS MCP Server

> 让 AI Agent 直接驱动 PLECS 4.7 Standalone 进行电力电子仿真

参考 MathWorks 的 MATLAB MCP Server 方案，为 PLECS 4.7 提供等效的 MCP 接入层。
AI Agent（Claude Code、GitHub Copilot 等）可以直接操作 PLECS 模型、运行仿真、做频域分析，无需手动操作界面。

```
┌─────────────────┐        ┌──────────────────┐        ┌──────────────────┐
│    AI Agent     │◄─MCP──►│  PLECS MCP Server │◄──────►│  PLECS 4.7       │
│  (Claude Code,  │        │  (本项目, Python) │ XML-RPC│  Standalone      │
│   Copilot 等)   │        └──────────────────┘  :1080  └──────────────────┘
└─────────────────┘
```

---

## 快速开始

### 1. 前置条件

- Python 3.10+
- PLECS 4.7 Standalone（需有效许可证）
- 支持 MCP 的 AI Agent

### 2. 安装

```bash
git clone https://github.com/your-org/plecs-mcp.git
cd plecs-mcp
pip install -e .
```

### 3. 开启 PLECS XML-RPC 接口

在 PLECS 中：

**Preferences → Simulation → 勾选 "Start XML-RPC server" → 端口保持 1080 → OK**

每次启动 PLECS 后自动生效。

### 4. 配置 AI Agent

编辑 `config.yml`（可选，也可用环境变量覆盖）：

```yaml
plecs:
  host: "localhost"   # PLECS 所在主机
  port: 1080          # XML-RPC 端口
```

将 MCP Server 注册到你的 Agent：

**Claude Code** (`~/.claude/mcp.json`):
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

**VS Code / Copilot** (`.vscode/mcp.json`):
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

> **注意**：`server.py` 由 Agent 在需要时自动启动，**无需手动运行**。

### 5. 验证

重启 Agent 后，让它执行：
```
调用 plecs_connect，告诉我 PLECS 的版本号
```

返回版本号即表示配置成功。

---

## 工具列表

MCP tool 与 PLECS XML-RPC 接口**严格一一对应**，不做额外封装。

| MCP Tool | 对应 RPC | 说明 |
|---|---|---|
| `plecs_connect` | `plecs.statistics()` | 建立连接，返回版本和已打开模型 |
| `plecs_status` | `plecs.statistics()` | 查看当前连接状态 |
| `plecs_load` | `plecs.load()` | 打开 .plecs 模型文件 |
| `plecs_close` | `plecs.close()` | 关闭模型 |
| `plecs_get` | `plecs.get()` | 读取组件或模型参数 |
| `plecs_set` | `plecs.set()` | 修改组件或模型参数 |
| `plecs_simulate` | `plecs.simulate()` | 运行时域仿真 |
| `plecs_analyze` | `plecs.analyze()` | 运行频域/稳态分析（ACSweep、SteadyState 等） |
| `plecs_scope` | `plecs.scope()` | Scope 操作（清除、保留轨迹、导出 CSV/图片、游标数据） |
| `plecs_webserver` | `plecs.webserver()` | 控制 PLECS Web 仿真服务器 |
| `plecs_codegen` | `plecs.codegen()` | 触发代码生成 |

---

## 工具详细说明

### `plecs_connect`

每次 Agent 会话开始时**必须首先调用**。底层调用 `plecs.statistics()` 验证连接。

```
参数：
  host  (str, 可选)  PLECS 主机，默认读 config.yml
  port  (int, 可选)  端口，默认读 config.yml

返回：版本号、build 信息、当前已打开的模型列表
```

### `plecs_status`

无参数。随时可调用，用于确认连接是否仍然有效。

### `plecs_load` / `plecs_close`

```
plecs_load(path)          打开文件，返回模型名称
plecs_close(model_name)   关闭模型（不自动保存）
```

### `plecs_get` / `plecs_set`

```
plecs_get(path, param)              读取参数值
plecs_set(path, param, value)       修改参数值，自动显示修改前的旧值
```

**路径格式**（用 `/` 分隔层级）：

```
"BuckConv"           → 模型级参数（StopTime、Ts、AbsTol 等）
"BuckConv/L1"        → 顶层组件参数（L、R、C、V_init 等）
"BuckConv/Ctrl/PID"  → 子系统内组件参数
```

### `plecs_simulate`

```
plecs_simulate(model_name, opts='{}')
```

`opts` 是 JSON 字符串，支持：

```json
{
  "ModelVars":    {"Vin": 48, "R_load": 10},
  "StopTime":     0.005,
  "MaxStep":      1e-6,
  "AbsTol":       1e-6,
  "RelTol":       1e-3,
  "Solver":       "auto"
}
```

返回各输出通道的 min / max / avg / 峰峰值 / RMS 统计。

### `plecs_analyze`

```
plecs_analyze(model_name, analysis_type, opts='{}')
```

`analysis_type` 必须与模型中 Analysis Tools 定义的名称完全一致：

| analysis_type | 说明 |
|---|---|
| `"ACSweep"` | AC 小信号扫频，自动计算穿越频率和相位裕度 |
| `"SteadyState"` | 稳态分析 |
| `"FreqResp"` | 频率响应分析 |
| `"ImpulseResp"` | 脉冲响应分析 |
| `"Multitone"` | 多音分析 |

ACSweep `opts` 示例：
```json
{
  "SysName":      "loopgain",
  "FreqRange":    [10, 100000],
  "NumPoints":    50,
  "Amplitude":    0.01,
  "LogScale":     true
}
```

### `plecs_scope`

```
plecs_scope(scope_path, command, args='[]')
```

| command | args 说明 |
|---|---|
| `"ClearTraces"` | 无（`"[]"`） |
| `"HoldTrace"` | 可选标签：`'["R=10Ω"]'` |
| `"SaveTrace"` | 可选标签：`'["轻载"]'` |
| `"ExportCSV"` | 必填文件路径：`'["C:/out/wave.csv"]'` |
| `"ExportBitmap"` | 必填文件路径：`'["C:/out/scope.png"]'` |
| `"GetCursorData"` | 时间范围：`'[[0.001, 0.002]]'` |

### `plecs_webserver`

```
plecs_webserver(command, args='[]')
command: "start" / "stop" / "status"
```

### `plecs_codegen`

```
plecs_codegen(model_name, opts='{}')
```

`opts` 示例：`'{"GenerateCode": true, "BuildCode": true}'`

---

## 典型工作流

### 参数研究

```
1. plecs_connect
2. plecs_load("C:/models/buck.plecs")       → 得到 model_name="BuckConverter"
3. plecs_get("BuckConverter/L1", "L")        → 查看当前电感值
4. plecs_set("BuckConverter", "StopTime", "0.005")
5. plecs_simulate("BuckConverter", '{"ModelVars": {"Vin": 48, "R_load": 10}}')
6. plecs_close("BuckConverter")
```

### 环路增益分析

```
1. plecs_connect
2. plecs_load("C:/models/buck_closed_loop.plecs")
3. plecs_analyze("BuckConverter", "ACSweep",
     '{"SysName": "loopgain", "FreqRange": [10, 500000], "NumPoints": 60}')
   → 自动输出穿越频率和相位裕度
```

### 波形对比

```
1. plecs_scope("BuckConverter/Scope", "ClearTraces")
2. plecs_simulate("BuckConverter", '{"ModelVars": {"R_load": 50}}')
3. plecs_scope("BuckConverter/Scope", "HoldTrace", '["轻载 50Ω"]')
4. plecs_simulate("BuckConverter", '{"ModelVars": {"R_load": 10}}')
5. plecs_scope("BuckConverter/Scope", "HoldTrace", '["满载 10Ω"]')
6. plecs_scope("BuckConverter/Scope", "ExportBitmap", '["C:/compare.png"]')
```

---

## 项目结构

```
plecs-mcp/
├── server.py          # MCP Server 主入口，所有 tool 定义在此
├── plecs_client.py    # PLECS XML-RPC 客户端封装（一方法对应一 RPC）
├── config.yml         # 连接配置（host/port）
├── pyproject.toml     # 依赖和安装配置
└── tests/
    └── test_server.py # 49 个单元测试（无需真实 PLECS）
```

---

## 环境变量

所有配置均可被环境变量覆盖（优先级高于 config.yml）：

| 变量 | 说明 | 默认值 |
|---|---|---|
| `PLECS_HOST` | PLECS 主机地址 | `localhost` |
| `PLECS_PORT` | XML-RPC 端口 | `1080` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

---

## 运行测试

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

49 个测试全部使用 Mock，无需启动 PLECS。

---

## 许可证

MIT License — 仅限配合合法的 PLECS 许可证使用。  
PLECS® 是 Plexim GmbH 的注册商标。
