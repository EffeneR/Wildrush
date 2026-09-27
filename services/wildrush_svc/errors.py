"""Error envelope ``{"error": {"code", "message"}}`` and exception handlers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("wildrush_svc.errors")


class APIError(Exception):
    """An error that maps directly onto the contract's error envelope."""

    def __init__(
        self, status_code: int, code: str, message: str, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(f"{status_code} {code}: {message}")
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


def error_body(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def error_response(
    status_code: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error_body(code, message), headers=headers)


# Common constructors ---------------------------------------------------------------------

def not_found(code: str = "not_found", message: str = "Not found") -> APIError:
    return APIError(404, code, message)


def conflict(code: str, message: str) -> APIError:
    return APIError(409, code, message)


def forbidden(code: str, message: str) -> APIError:
    return APIError(403, code, message)


def unprocessable(code: str, message: str) -> APIError:
    return APIError(422, code, message)


def rate_limited(retry_after_s: float) -> APIError:
    secs = max(1, int(retry_after_s + 0.999))
    return APIError(
        429, "rate_limited", f"Too many requests; retry in {secs} s", headers={"Retry-After": str(secs)}
    )


_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    415: "unsupported_media_type",
}


def _describe_validation(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors()[:3]:
        loc = ".".join(str(p) for p in err.get("loc", ()) if p != "body")
        msg = err.get("msg", "invalid")
        parts.append(f"{loc}: {msg}" if loc else str(msg))
    return "; ".join(parts) or "Invalid request"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(_: Request, exc: APIError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, "validation_error", _describe_validation(exc))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        detail = exc.detail if isinstance(exc.detail, str) else code
        return error_response(exc.status_code, code, detail, getattr(exc, "headers", None))

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        # Concurrent requests racing on a unique constraint (e.g. double accept).
        log.info("integrity conflict: %s", type(exc.orig).__name__ if exc.orig else "unknown")
        return error_response(409, "conflict", "Request conflicts with the current state; retry")

    @app.exception_handler(OperationalError)
    async def _operational(_: Request, exc: OperationalError) -> JSONResponse:
        log.error("database unavailable: %s", type(exc.orig).__name__ if exc.orig else "unknown")
        return error_response(503, "db_unavailable", "Database unavailable")

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return error_response(500, "internal_error", "Internal server error")
