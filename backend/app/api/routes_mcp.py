"""Streamable-HTTP MCP endpoint — the same server as app/mcp_server.py, over HTTP.

Gives the MCP server a URL (POST /mcp) so it can be added to remote MCP clients or
scanned like any other hosted server. Reuses the stdio server's JSON-RPC handler.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from app.mcp_server import _handle

router = APIRouter()


@router.get("/mcp")
def mcp_info() -> dict:
    """Friendly response for a browser GET (the protocol itself is POST-only)."""
    return {
        "server": "mcp-trust-badge",
        "transport": "streamable-http",
        "note": "This is an MCP endpoint. Send JSON-RPC 2.0 over POST, not GET.",
        "tools": ["grade_manifest", "grade_server_url"],
        "example": "POST /mcp {\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}",
    }


@router.post("/mcp")
async def mcp_endpoint(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={
            "jsonrpc": "2.0", "id": None,
            "error": {"code": -32700, "message": "parse error"}})

    # _handle is sync and may call asyncio.run (grade_server_url); run it off the
    # event loop so that nested asyncio.run has no running loop to collide with.
    resp = await run_in_threadpool(_handle, body)
    if resp is None:
        return Response(status_code=202)  # a notification — accepted, no body

    headers = {}
    if isinstance(body, dict) and body.get("method") == "initialize":
        headers["Mcp-Session-Id"] = uuid.uuid4().hex  # stateless, but present for clients
    return JSONResponse(resp, headers=headers)
