"""Read-only MCP client over Streamable HTTP (raw JSON-RPC via httpx).

Read-only BY CONSTRUCTION: this class exposes only initialize() and
list_tools(). There is deliberately NO tools/call method and no code path that
can invoke one -- a trust scanner must never execute a scanned server's tools.
Do not add one.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from app.core.ssrf_guard import MAX_RESPONSE_BYTES, SCAN_TIMEOUT_S

# ponytail: protocol version hardcoded, negotiation skipped. If a server 4xxs on
# this, read its error (it usually names a supported version) and bump/negotiate.
DEFAULT_PROTOCOL_VERSION = "2025-06-18"


class ReadOnlyMCPClient:
    """Initialize + list tools only. Cannot call tools by design."""

    def __init__(self, url: str, protocol_version: str = DEFAULT_PROTOCOL_VERSION):
        self.url = url
        self.protocol_version = protocol_version
        self.session_id: Optional[str] = None
        self.server_info: dict = {}
        self.capabilities: dict = {}
        self._id = 0
        self._client = httpx.AsyncClient(
            timeout=SCAN_TIMEOUT_S,
            follow_redirects=False,  # redirects re-open SSRF; block them
        )

    async def __aenter__(self) -> "ReadOnlyMCPClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._client.aclose()

    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    async def _post(self, payload: dict) -> httpx.Response:
        """POST, streaming the body with a hard byte cap."""
        async with self._client.stream(
            "POST", self.url, json=payload, headers=self._headers()
        ) as resp:
            resp.raise_for_status()
            chunks, total = [], 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise ValueError(f"response exceeded {MAX_RESPONSE_BYTES} bytes")
                chunks.append(chunk)
            resp._decoded = b"".join(chunks)  # stash for the caller
            resp._session_hdr = resp.headers.get("Mcp-Session-Id")
            resp._ctype = resp.headers.get("Content-Type", "")
            return resp

    @staticmethod
    def _parse_body(body: bytes, ctype: str) -> dict:
        """Parse a JSON body or an SSE-framed `data: {...}` body."""
        text = body.decode("utf-8", "replace").strip()
        if "text/event-stream" in ctype or text.startswith("event:") or text.startswith("data:"):
            # Take the last non-empty `data:` line (final SSE frame).
            data = None
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    data = line[len("data:"):].strip()
            if data is None:
                raise ValueError("SSE response had no data: frame")
            return json.loads(data)
        return json.loads(text)

    async def _rpc(self, method: str, params: Optional[dict] = None) -> dict:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            payload["params"] = params
        resp = await self._post(payload)
        if resp._session_hdr:  # capture/refresh session id
            self.session_id = resp._session_hdr
        msg = self._parse_body(resp._decoded, resp._ctype)
        if "error" in msg:
            raise ValueError(f"JSON-RPC error on {method}: {msg['error']}")
        return msg.get("result", {})

    async def _notify(self, method: str) -> None:
        """Fire-and-forget notification (no id, no result expected)."""
        payload = {"jsonrpc": "2.0", "method": method}
        resp = await self._post(payload)
        if resp._session_hdr:
            self.session_id = resp._session_hdr

    async def initialize(self) -> dict:
        result = await self._rpc("initialize", {
            "protocolVersion": self.protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "trust-badge-scanner", "version": "0.1"},
        })
        self.server_info = result.get("serverInfo", {})
        self.capabilities = result.get("capabilities", {})
        await self._notify("notifications/initialized")
        return result

    async def list_tools(self) -> list[dict]:
        result = await self._rpc("tools/list")
        return result.get("tools", [])
