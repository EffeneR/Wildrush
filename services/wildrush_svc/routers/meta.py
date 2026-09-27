"""/healthz and /v1/version"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .. import API_VERSION, __version__
from ..auth import ANON
from ..context import get_ctx
from ..errors import error_body

router = APIRouter(tags=["meta"])


@router.get("/healthz", dependencies=[Depends(ANON)])
def healthz(request: Request) -> JSONResponse:
    ctx = get_ctx(request)
    try:
        with ctx.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        body = {"ok": False, "db": "unavailable", **error_body("db_unavailable", "Database unavailable")}
        return JSONResponse(status_code=503, content=body)
    return JSONResponse(status_code=200, content={"ok": True, "db": "ok"})


@router.get("/v1/version", dependencies=[Depends(ANON)])
def version(request: Request) -> dict[str, Any]:
    ctx = get_ctx(request)
    return {
        "api": API_VERSION,
        "protocol": ctx.settings.protocol_version,
        "service_build": f"{__version__}+{ctx.settings.service_build}",
    }
