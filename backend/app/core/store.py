"""sqlite3-backed scan store. One file, no ORM.

# ponytail: JSON-blob column, add real columns (tier/scanned_at) only if the
# marketplace needs to filter server-side.
"""
from __future__ import annotations

import os
import sqlite3
import uuid

from app.core.manifest_schema import ScanResult

_DB = os.getenv("TRUST_DB_PATH") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scans.db"
)


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _init() -> None:
    with _conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS scans (scan_id TEXT PRIMARY KEY, data TEXT)")


_init()


def new_scan_id() -> str:
    return uuid.uuid4().hex


def put(result: ScanResult) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO scans (scan_id, data) VALUES (?, ?) "
            "ON CONFLICT(scan_id) DO UPDATE SET data=excluded.data",
            (result.scan_id, result.model_dump_json()),
        )


def get(scan_id: str) -> ScanResult | None:
    with _conn() as c:
        row = c.execute("SELECT data FROM scans WHERE scan_id=?", (scan_id,)).fetchone()
    return ScanResult.model_validate_json(row[0]) if row else None


def list_all() -> list[ScanResult]:
    with _conn() as c:
        rows = c.execute("SELECT data FROM scans").fetchall()
    return [ScanResult.model_validate_json(r[0]) for r in rows]


def delete(scan_id: str) -> bool:
    """Remove a scan. Returns True if a row was deleted.
    Note: seeded servers reappear on next startup (seed is idempotent)."""
    with _conn() as c:
        cur = c.execute("DELETE FROM scans WHERE scan_id=?", (scan_id,))
        return cur.rowcount > 0
