# PLECS MCP Server

MCP server for controlling PLECS Standalone 4.7 through its XML-RPC interface.

## PLECS Setup

In PLECS Standalone, enable the XML-RPC server:

`Preferences -> Simulation -> Start XML-RPC server`

Use port `1080` unless you pass a different port to `plecs_connect`.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

## Run

```powershell
python server.py
```

MCP clients should run it over stdio. Example config:

```json
{
  "mcpServers": {
    "plecs": {
      "command": "python",
      "args": ["C:/Users/XingTong/Desktop/plecs-mcp/server.py"],
      "env": {
        "PLECS_HOST": "localhost",
        "PLECS_PORT": "1080"
      }
    }
  }
}
```

## Tools

- `plecs_connect`: connect to PLECS XML-RPC.
- `plecs_status`: check connection health.
- `plecs_load_model`: open a `.plecs` file.
- `plecs_get_param`: read a component or model parameter.
- `plecs_set_param`: set a component or model parameter.
- `plecs_run_simulation`: run time-domain simulation.
- `plecs_ac_sweep`: run AC sweep analysis.
- `plecs_analyze`: run a generic analysis.
- `plecs_export_scope`: export a Scope to CSV.
- `plecs_parameter_sweep`: run repeated simulations over one variable.
- `plecs_save_model`: save an open model.
- `plecs_close_model`: close an open model.
