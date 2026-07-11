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
