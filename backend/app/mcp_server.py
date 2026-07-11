"""MCP Trust Badge as an MCP server (stdio, raw JSON-RPC 2.0 — no SDK, runs on 3.9).

Exposes the trust grader itself as MCP tools so an AI assistant can grade a server
before trusting it. Read-only by construction: `grade_server_url` connects with the
same initialize + tools/list-only client (never executes a scanned server's tools).

Run:  .venv/bin/python -m app.mcp_server
Add to an MCP client (e.g. Claude Desktop) — see mcp_client_config.json.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys

from app.checks.pipeline import analyze
from app.core.manifest_schema import Tool, ToolManifest
from app.ingestion.live_url import ScanTimeout, SSRFError, Unreachable, scan_live_url

log = logging.getLogger("mcp-trust-badge")
PROTOCOL_VERSION = "2025-06-18"

TOOLS = [
    {
        "name": "grade_manifest",
        "description": ("Grade an MCP server's declared tool list for trust/safety. "
                        "Returns an S-F letter tier, a 0-100 score, and the flags behind it. "
                        "Read-only: only inspects declared capabilities, never executes anything."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "Name of the server being graded"},
                "tools": {
                    "type": "array",
                    "description": "The server's tools/list (name + description each)",
                    "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}, "description": {"type": "string"}},
                        "required": ["name"],
                    },
                },
            },
            "required": ["tools"],
        },
    },
    {
        "name": "grade_server_url",
        "description": ("Connect to a live MCP server over Streamable HTTP (read-only: initialize "
                        "+ tools/list only, never calls its tools), then grade it. SSRF-guarded. "
                        "Returns tier, score, and flags."),
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "The MCP server URL to scan"}},
            "required": ["url"],
        },
    },
]


def _result(manifest: ToolManifest, score: int, tier: str, flags) -> dict:
    return {
        "server_name": manifest.server_name,
        "tier": tier,
        "score": score,
        "tool_count": len(manifest.tools),
        "flags": [{"severity": f.severity, "label": f.label, "explanation": f.explanation}
                  for f in flags if f.label != "rwx-ratio"],
    }


def grade_manifest(args: dict) -> dict:
    raw = args.get("tools", [])
    tools = [Tool(name=t.get("name", ""), description=t.get("description", "") or "",
                  inputSchema=t.get("inputSchema") or t.get("input_schema") or {}) for t in raw]
    m = ToolManifest(server_name=args.get("server_name", "pasted-server"), tools=tools)
    score, tier, flags, _ = analyze(m)
    return _result(m, score, tier, flags)


async def _grade_url(url: str) -> dict:
    try:
        m = await scan_live_url(url)
    except SSRFError as e:
        return {"tier": "U", "error": f"blocked by SSRF guard: {e}"}
    except ScanTimeout:
        return {"tier": "U", "error": "server did not respond in time"}
    except Unreachable as e:
        return {"tier": "U", "error": f"unreachable: {e}"}
    score, tier, flags, _ = analyze(m)
    return _result(m, score, tier, flags)


def grade_server_url(args: dict) -> dict:
    return asyncio.run(_grade_url(args.get("url", "")))


_DISPATCH = {"grade_manifest": grade_manifest, "grade_server_url": grade_server_url}


def _handle(msg: dict) -> dict | None:
    mid = msg.get("id")
    method = msg.get("method")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mcp-trust-badge", "version": "0.1.0"},
        }}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        p = msg.get("params", {})
        fn = _DISPATCH.get(p.get("name"))
        if fn is None:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32602, "message": f"unknown tool {p.get('name')!r}"}}
        try:
            out = fn(p.get("arguments", {}))
        except Exception as e:  # never crash the server on a bad call
            log.exception("tool %s failed", p.get("name"))
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}}
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": json.dumps(out, indent=2)}]}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if mid is None:
        return None  # a notification (e.g. notifications/initialized) — no reply
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def main() -> None:
    # logs to stderr ONLY — stdout is the JSON-RPC channel.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    log.info("mcp-trust-badge stdio server ready")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = _handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
