"""Shared Pydantic models.

Both the paste path and the (later) live-URL / repo paths converge on the same
internal `ToolManifest`, and every path emits the same `ScanResult` (§11.3) so the
frontend never special-cases by source.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

Severity = Literal["info", "caution", "hard"]
Tier = Literal["S", "A", "B", "C", "D", "F", "U"]
Status = Literal["pending", "scanning", "done", "error"]
SourceType = Literal["live_url", "manifest", "github_repo"]


# ---- Input: mirrors the real MCP `tools/list` response shape (strict). ----

class Tool(BaseModel):
    name: str
    description: str = ""
    # `tools/list` calls this inputSchema; accept that alias too.
    input_schema: dict = Field(default_factory=dict, alias="inputSchema")

    model_config = {"populate_by_name": True}


class ToolManifest(BaseModel):
    """Normalized capability list. The one object the check engine consumes."""
    server_name: str = "unknown"
    tools: list[Tool] = Field(default_factory=list)
    auth_type: Optional[str] = None
    transport: Optional[str] = None


class ManifestPasteRequest(BaseModel):
    """Body for POST /scan/manifest. Strict: garbage in -> 422, not best-effort."""
    server_name: str = "pasted-server"
    tools: list[Tool]
    auth_type: Optional[str] = None
    transport: Optional[str] = "manifest"

    def to_manifest(self) -> ToolManifest:
        return ToolManifest(
            server_name=self.server_name,
            tools=self.tools,
            auth_type=self.auth_type,
            transport=self.transport,
        )


# ---- Output: the single shared result schema (§11.3). ----

class Flag(BaseModel):
    severity: Severity
    label: str
    explanation: str
    weight: int = 0  # points subtracted from the 100 baseline


class ToolNote(BaseModel):
    name: str
    description: str
    risk_note: str = ""


class ScanMetadata(BaseModel):
    tool_count: int = 0
    auth_type: Optional[str] = None
    transport: Optional[str] = None
    scanned_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ScanResult(BaseModel):
    scan_id: str
    status: Status
    source_type: SourceType
    server_name: str = ""
    tier: Tier = "U"
    score: int = 0
    flags: list[Flag] = Field(default_factory=list)
    tools: list[ToolNote] = Field(default_factory=list)
    metadata: ScanMetadata = Field(default_factory=ScanMetadata)
    error: Optional[dict] = None  # {"code": ..., "message": ...} on failure
