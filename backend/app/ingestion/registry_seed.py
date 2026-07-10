"""Seed the marketplace so the grid is never empty.

Offline-safe hand-written manifests (guaranteed tier variety), then a
best-effort pull from the MCP Registry (skipped silently on any failure).
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request

from app.checks.pipeline import analyze
from app.core import store
from app.core.manifest_schema import (
    ScanMetadata,
    ScanResult,
    Tool,
    ToolManifest,
)

log = logging.getLogger(__name__)

_REGISTRY = "https://registry.modelcontextprotocol.io/v0/servers"

# Hand-written manifests covering S / B / D / F (verified against checks/rules.py).
_SEED_MANIFESTS = [
    # Clean S: pure compute, no caps.
    ToolManifest(server_name="calculator", transport="stdio", tools=[
        Tool(name="add", description="add two numbers", input_schema={"a": "number", "b": "number"}),
        Tool(name="echo", description="echo the input text", input_schema={"text": "string"}),
    ]),
    # Middling B: broad filesystem path + credential handling (no trifecta).
    ToolManifest(server_name="file-manager", transport="stdio", tools=[
        Tool(name="write_file", description="write content to a filesystem path",
             input_schema={"path": "string", "content": "string"}),
        Tool(name="get_api_key", description="return the stored api_key for a service",
             input_schema={"service": "string"}),
    ]),
    # Lethal-trifecta D: reads untrusted + net egress + sensitive data.
    ToolManifest(server_name="web-assistant", transport="http", tools=[
        Tool(name="fetch_url", description="fetch a web page via http request",
             input_schema={"url": "string"}),
        Tool(name="read_db_credentials", description="read a private db credential from the vault",
             input_schema={"name": "string"}),
    ]),
    # Blatant F: two arbitrary-exec tools + secrets.
    ToolManifest(server_name="root-shell", transport="stdio", tools=[
        Tool(name="run_shell", description="execute an arbitrary shell command",
             input_schema={"command": "string"}),
        Tool(name="eval_python", description="execute arbitrary python code via subprocess",
             input_schema={"code": "string"}),
        Tool(name="read_env_secrets", description="read a secret credential from env",
             input_schema={"name": "string"}),
    ]),
]


# Stable id per seeded server so re-seeding on every startup upserts in place
# instead of duplicating the grid across reboots.
def _seed_id(server_name: str) -> str:
    return "seed-" + re.sub(r"[^a-z0-9]+", "-", server_name.lower()).strip("-")


def _store_manifest(manifest: ToolManifest, source_type: str = "manifest") -> ScanResult:
    score, tier, flags, tools = analyze(manifest, scan_complete=True)
    result = ScanResult(
        scan_id=_seed_id(manifest.server_name),
        status="done",
        source_type=source_type,
        server_name=manifest.server_name,
        tier=tier,
        score=score,
        flags=flags,
        tools=tools,
        metadata=ScanMetadata(
            tool_count=len(manifest.tools),
            auth_type=manifest.auth_type,
            transport=manifest.transport,
        ),
    )
    store.put(result)
    return result


def _seed_registry(limit: int = 5) -> int:
    """Best-effort: pull a few registry entries. Registry has no tools/list,
    so these seed as tool-less (clean) entries. Never raises."""
    try:
        req = urllib.request.Request(_REGISTRY, headers={"User-Agent": "mcp-trust-badge"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.load(resp)
        servers = data.get("servers", data) if isinstance(data, dict) else data
        n = 0
        for s in list(servers)[:limit]:
            name = s.get("name") if isinstance(s, dict) else None
            if not name:
                continue
            _store_manifest(ToolManifest(server_name=name, transport="registry"), "manifest")
            n += 1
        return n
    except Exception as e:  # network/shape/anything — skip silently
        log.info("registry seed skipped: %s", e)
        return 0


def seed() -> int:
    for m in _SEED_MANIFESTS:
        _store_manifest(m)
    n = len(_SEED_MANIFESTS)
    n += _seed_registry()
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = seed()
    print(f"seeded {count} servers")
