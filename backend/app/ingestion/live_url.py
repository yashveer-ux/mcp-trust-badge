"""Live-URL ingestion: fetch a running MCP server's tool list, read-only.

Pipeline: validate_url (SSRF) -> initialize -> list_tools -> ToolManifest.
"""
from __future__ import annotations

import httpx

from app.core.manifest_schema import Tool, ToolManifest
from app.core.mcp_client import ReadOnlyMCPClient
from app.core.ssrf_guard import SSRFError, validate_url  # re-exported

__all__ = ["scan_live_url", "SSRFError", "ScanTimeout", "Unreachable"]


class ScanTimeout(Exception):
    """Server did not respond within the scan timeout."""


class Unreachable(Exception):
    """Could not connect to / talk to the server."""


async def scan_live_url(url: str) -> ToolManifest:
    validate_url(url)  # raises SSRFError before any connection
    try:
        async with ReadOnlyMCPClient(url) as client:
            await client.initialize()
            raw_tools = await client.list_tools()
    except httpx.TimeoutException as e:
        raise ScanTimeout(f"timed out scanning {url}") from e
    except (httpx.ConnectError, httpx.RequestError) as e:
        raise Unreachable(f"could not reach {url}: {e}") from e

    tools = [
        Tool(
            name=t.get("name", ""),
            description=t.get("description", "") or "",
            inputSchema=t.get("inputSchema", {}) or {},
        )
        for t in raw_tools
    ]

    info = client.server_info or {}
    server_name = info.get("name") or url
    # auth_type: surface if the server advertised it under capabilities/auth.
    auth_type = (client.capabilities or {}).get("authType") or info.get("authType")

    return ToolManifest(
        server_name=server_name,
        tools=tools,
        auth_type=auth_type,
        transport="streamable-http",
    )
