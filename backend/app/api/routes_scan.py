"""Scan endpoints: paste a manifest, live-URL / repo scan (backgrounded), fetch."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.checks.pipeline import analyze
from app.core import store
from app.core.manifest_schema import (
    ManifestPasteRequest,
    ScanMetadata,
    ScanResult,
    ToolManifest,
)
from app.ingestion.live_url import ScanTimeout, SSRFError, Unreachable, scan_live_url
from app.ingestion.github_repo import RepoError, scan_repo

log = logging.getLogger(__name__)
router = APIRouter()


class UrlScanRequest(BaseModel):
    url: str


class RepoScanRequest(BaseModel):
    repo_url: str


def _done_result(scan_id: str, source_type: str, manifest: ToolManifest) -> ScanResult:
    score, tier, flags, tools = analyze(manifest, scan_complete=True)
    return ScanResult(
        scan_id=scan_id,
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


def _error_result(scan_id: str, source_type: str, name: str, code: str, message: str) -> ScanResult:
    return ScanResult(scan_id=scan_id, status="error", source_type=source_type,
                      server_name=name, tier="U", score=0,
                      error={"code": code, "message": message})


@router.post("/scan/manifest", response_model=ScanResult)
def scan_manifest(req: ManifestPasteRequest) -> ScanResult:
    result = _done_result(store.new_scan_id(), "manifest", req.to_manifest())
    store.put(result)
    return result


@router.post("/scan/url", response_model=ScanResult)
async def scan_url(req: UrlScanRequest) -> ScanResult:
    scan_id = store.new_scan_id()
    result = ScanResult(scan_id=scan_id, status="scanning", source_type="live_url",
                        server_name=req.url, tier="U", score=0)
    store.put(result)
    asyncio.create_task(_run_url_scan(scan_id, req.url))
    return result


@router.post("/scan/repo", response_model=ScanResult)
async def scan_repo_endpoint(req: RepoScanRequest) -> ScanResult:
    scan_id = store.new_scan_id()
    result = ScanResult(scan_id=scan_id, status="scanning", source_type="github_repo",
                        server_name=req.repo_url, tier="U", score=0)
    store.put(result)
    asyncio.create_task(_run_repo_scan(scan_id, req.repo_url))
    return result


async def _run_url_scan(scan_id: str, url: str) -> None:
    try:
        manifest = await scan_live_url(url)
        # analyze is sync (LLM+CPU) — offload so we don't block the loop.
        result = await asyncio.to_thread(_done_result, scan_id, "live_url", manifest)
        store.put(result)
    except ScanTimeout:
        store.put(_error_result(scan_id, "live_url", url, "scan_timeout",
                                "Scan incomplete — server did not respond in time"))
    except SSRFError:
        store.put(_error_result(scan_id, "live_url", url, "ssrf_blocked", "URL blocked by SSRF guard"))
    except Unreachable:
        store.put(_error_result(scan_id, "live_url", url, "unreachable", "Server unreachable"))
    except Exception:
        log.exception("url scan failed: %s", url)
        store.put(_error_result(scan_id, "live_url", url, "scan_failed", "Scan failed"))


async def _run_repo_scan(scan_id: str, repo_url: str) -> None:
    try:
        manifest = await scan_repo(repo_url)
        result = await asyncio.to_thread(_done_result, scan_id, "github_repo", manifest)
        store.put(result)
    except RepoError:
        store.put(_error_result(scan_id, "github_repo", repo_url, "repo_scan_failed",
                                "Repository scan failed"))
    except Exception:
        log.exception("repo scan failed: %s", repo_url)
        store.put(_error_result(scan_id, "github_repo", repo_url, "scan_failed", "Scan failed"))


@router.get("/scan/{scan_id}", response_model=ScanResult)
def get_scan(scan_id: str) -> ScanResult:
    result = store.get(scan_id)
    if result is None:
        raise HTTPException(404, detail={"code": "scan_not_found", "message": f"No scan {scan_id}"})
    return result
