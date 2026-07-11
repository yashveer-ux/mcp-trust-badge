"""Marketplace: browse completed scans."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core import store
from app.core.manifest_schema import ScanResult

router = APIRouter()


@router.get("/marketplace")
def marketplace() -> dict:
    return {"servers": [s for s in store.list_all() if s.status == "done"]}


@router.get("/marketplace/{server_id}", response_model=ScanResult)
def marketplace_server(server_id: str) -> ScanResult:
    result = store.get(server_id)
    if result is None:
        raise HTTPException(404, detail={"code": "server_not_found",
                                         "message": f"No server {server_id}"})
    return result


@router.delete("/marketplace/{server_id}")
def delete_server(server_id: str) -> dict:
    if not store.delete(server_id):
        raise HTTPException(404, detail={"code": "server_not_found",
                                         "message": f"No server {server_id}"})
    return {"deleted": server_id}
