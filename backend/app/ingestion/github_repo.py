"""GitHub-repo ingestion: build a ToolManifest from declared/documented capabilities.

Two paths, TEXT ONLY -- we never clone, execute, or statically parse source code:
  1. structured metadata: raw server.json (root + .well-known/mcp/), main|master
  2. fallback: README.md -> Claude forced-tool-use extracts the tool list

ponytail: declared/documented capabilities only, no source parsing -- honest
framing, and it sidesteps ever executing or trusting untrusted code.
"""
from __future__ import annotations

import json
import logging
import os
import re

import httpx

from app.core.manifest_schema import Tool, ToolManifest

log = logging.getLogger(__name__)

RAW_HOST = "https://raw.githubusercontent.com"
BRANCHES = ("main", "master")
FETCH_TIMEOUT_S = 8.0
MAX_BYTES = 2_000_000  # 2MB cap per fetch
# ponytail: cheap/bulk model for README extraction (structured, low-stakes).
README_MODEL = "claude-haiku-4-5-20251001"

_URL_RE = re.compile(r"github\.com[/:]+([^/]+)/([^/#?]+)", re.IGNORECASE)


class RepoError(Exception):
    """Repo could not be parsed, fetched, or extracted."""


def _parse_owner_repo(repo_url: str) -> tuple[str, str]:
    m = _URL_RE.search(repo_url or "")
    if not m:
        raise RepoError(f"not a github.com repo url: {repo_url!r}")
    owner, repo = m.group(1), m.group(2)
    repo = repo[:-4] if repo.endswith(".git") else repo
    if not owner or not repo:
        raise RepoError(f"could not parse owner/repo from {repo_url!r}")
    return owner, repo


async def _fetch(client: httpx.AsyncClient, url: str) -> str | None:
    """Fetch raw text with a byte cap. None on 404/missing; raises on transport error."""
    try:
        async with client.stream("GET", url) as resp:
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            chunks, total = [], 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > MAX_BYTES:
                    raise RepoError(f"{url} exceeded {MAX_BYTES} bytes")
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8", "replace")
    except httpx.HTTPStatusError:
        return None  # treat other 4xx/5xx as "not found here", try next path


async def _fetch_first(client: httpx.AsyncClient, paths: list[str]) -> str | None:
    for branch in BRANCHES:
        for path in paths:
            text = await _fetch(client, f"{RAW_HOST}/{path.format(branch=branch)}")
            if text is not None:
                return text
    return None


def _tools_from_server_json(text: str) -> list[Tool] | None:
    """Extract a tool list from a server.json body, or None if unusable."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    raw = data.get("tools") if isinstance(data, dict) else None
    if not isinstance(raw, list) or not raw:
        return None
    tools = []
    for t in raw:
        if not isinstance(t, dict):
            continue
        tools.append(Tool(
            name=t.get("name", ""),
            description=t.get("description", "") or "",
            inputSchema=t.get("inputSchema", {}) or t.get("input_schema", {}) or {},
        ))
    return tools or None


async def _tools_from_readme(readme: str, slug: str) -> list[Tool]:
    """Send README text to Claude with forced tool-use to extract {name, description}."""
    import anthropic  # guarded by caller

    client = anthropic.AsyncAnthropic(timeout=FETCH_TIMEOUT_S + 12.0, max_retries=1)
    tool = {
        "name": "report_tools",
        "description": "Report the MCP tools this server documents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tools": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["name", "description"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["tools"],
            "additionalProperties": False,
        },
    }
    resp = await client.messages.create(
        model=README_MODEL,
        max_tokens=2048,
        system=("Extract the MCP tools documented in this README. Only list tools the "
                "server actually exposes; ignore CLI commands, env vars, and install "
                "steps. If none are documented, return an empty list."),
        tools=[tool],
        tool_choice={"type": "tool", "name": "report_tools"},
        messages=[{"role": "user", "content": f"Repo {slug} README:\n\n{readme[:100_000]}"}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "report_tools":
            return [
                Tool(name=t.get("name", ""), description=t.get("description", "") or "")
                for t in block.input.get("tools", []) if t.get("name")
            ]
    return []


async def scan_repo(repo_url: str) -> ToolManifest:
    owner, repo = _parse_owner_repo(repo_url)
    slug = f"{owner}/{repo}"

    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_S, follow_redirects=False) as client:
        # STEP 1 -- structured metadata.
        server_json = await _fetch_first(client, [
            f"{owner}/{repo}/{{branch}}/server.json",
            f"{owner}/{repo}/{{branch}}/.well-known/mcp/server.json",
        ])
        if server_json is not None:
            tools = _tools_from_server_json(server_json)
            if tools:
                return ToolManifest(server_name=slug, tools=tools,
                                    transport="github", auth_type=None)

        # STEP 2 -- README fallback (needs the LLM).
        try:
            import anthropic  # noqa: F401
        except ImportError:
            anthropic = None
        if not os.getenv("ANTHROPIC_API_KEY") or anthropic is None:
            raise RepoError(
                "GitHub README extraction needs ANTHROPIC_API_KEY; no server.json found")

        readme = await _fetch_first(client, [f"{owner}/{repo}/{{branch}}/README.md"])
        if readme is None:
            raise RepoError(f"no server.json and no README.md found for {slug}")

    try:
        tools = await _tools_from_readme(readme, slug)
    except Exception as e:
        raise RepoError(f"README extraction failed for {slug}: {e}") from e

    return ToolManifest(server_name=slug, tools=tools, transport="github", auth_type=None)
