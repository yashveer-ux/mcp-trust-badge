# MCP Trust Badge as an MCP Server

The trust grader is exposed as its own MCP server, so an AI assistant can grade a
server *before* trusting it. Read-only by construction — it only inspects declared
capabilities and never executes a scanned server's tools.

## Tools

| Tool | Args | Returns |
|---|---|---|
| `grade_manifest` | `server_name?`, `tools[]` (name + description) | `{tier, score, flags, tool_count}` |
| `grade_server_url` | `url` | Connects to a live MCP server (initialize + tools/list only, SSRF-guarded), then grades it |

Both return an S–F tier, a 0–100 score, and the flags behind the grade.

## Run

```bash
cd backend
.venv/bin/python -m app.mcp_server        # stdio transport, JSON-RPC 2.0
```

Implementation: `app/mcp_server.py` — a ~130-line raw stdio JSON-RPC server (no SDK;
the `mcp` package needs Python 3.10+, this project runs on 3.9). Reuses the same
`checks/pipeline.analyze` and `ingestion/live_url.scan_live_url` as the web app.

## Add to an MCP client (Claude Desktop)

Merge `backend/mcp_client_config.json` into your `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/`), then restart the client. Ask it to
"grade the MCP server at <url>" and it will call `grade_server_url`.

## Note

This makes the scanner an MCP server that could scan itself — and because it only
reads and never executes anything, it grades clean.

## Upgrade path

On Python 3.10+, this can be swapped for the official `mcp` SDK's `FastMCP` for
richer transport support (HTTP/SSE) with less plumbing. The tool logic is unchanged.
