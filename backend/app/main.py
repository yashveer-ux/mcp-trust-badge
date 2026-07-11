"""FastAPI app entrypoint (§11.4 structured errors)."""
from __future__ import annotations

import logging
import os
import pathlib


def _load_env() -> None:
    """Load KEY=VALUE lines from a gitignored .env (backend/ or cwd) into the
    process environment. No dependency; existing env vars win over the file."""
    here = pathlib.Path(__file__).resolve()
    for env in (here.parents[1] / ".env", pathlib.Path.cwd() / ".env"):
        if not env.exists():
            continue
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        break


_load_env()

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes_badge import router as badge_router
from app.api.routes_marketplace import router as marketplace_router
from app.api.routes_mcp import router as mcp_router
from app.api.routes_scan import router as scan_router
from app.ingestion import registry_seed

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="MCP Trust Badge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scan_router)
app.include_router(marketplace_router)
app.include_router(badge_router)
app.include_router(mcp_router)


@app.on_event("startup")
def _seed() -> None:
    try:
        registry_seed.seed()
    except Exception:
        logging.exception("marketplace seed failed (non-fatal)")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.exception_handler(HTTPException)
def http_exc(_: Request, exc: HTTPException) -> JSONResponse:
    # detail may already be {"code","message"}; else wrap the string.
    d = exc.detail
    err = d if isinstance(d, dict) else {"code": f"http_{exc.status_code}", "message": str(d)}
    return JSONResponse(status_code=exc.status_code, content={"error": err})


@app.exception_handler(RequestValidationError)
def validation_exc(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "validation_error", "message": str(exc.errors())}},
    )
