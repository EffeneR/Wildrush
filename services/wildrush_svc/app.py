"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from sqlalchemy import Engine
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import __version__
from .clock import Clock, SystemClock
from .config import Settings
from .context import AppContext
from .db import create_db_engine, create_sessionmaker
from .errors import error_body, install_error_handlers
from .matchmaker import Matchmaker
from .ratelimit import RateLimiter
from .routers import accounts, matches, meta, parties, queue, servers

log = logging.getLogger("wildrush_svc")


class BodyLimitMiddleware:
    """Buffers the request body (all API bodies are small) and rejects anything larger
    than ``max_bytes`` with 413 before the application sees it."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = -1
                if declared < 0 or declared > self.max_bytes:
                    await self._reject(send)
                    return
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":  # client went away
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_bytes:
                await self._reject(send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    async def _reject(self, send: Send) -> None:
        body = json.dumps(error_body("payload_too_large", "Request body too large")).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})


class NoStoreMiddleware:
    """API responses carry tokens/tickets: never cache them."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"cache-control", b"no-store"))
                headers.append((b"x-content-type-options", b"nosniff"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    clock: Clock | None = None,
    limiter: RateLimiter | None = None,
) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]
    engine = engine or create_db_engine(settings)
    ctx = AppContext(
        settings=settings,
        engine=engine,
        sessionmaker=create_sessionmaker(engine),
        clock=clock or SystemClock(),
        limiter=limiter or RateLimiter(enabled=settings.rate_limit_enabled),
    )
    matchmaker = Matchmaker(ctx)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, Any]]:
        task: asyncio.Task[None] | None = None
        if settings.matchmaker_enabled:
            task = asyncio.create_task(matchmaker.run_forever(), name="wildrush-matchmaker")
            log.info("matchmaker started (interval %.2fs)", settings.matchmaker_interval_s)
        try:
            yield {}
        finally:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                log.info("matchmaker stopped")

    app = FastAPI(
        title="WILDRUSH control service",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.api_docs else None,
        redoc_url=None,
        openapi_url="/v1/openapi.json" if settings.api_docs else None,
    )
    app.state.ctx = ctx
    app.state.matchmaker = matchmaker
    install_error_handlers(app)
    for module in (meta, accounts, parties, queue, matches, servers):
        app.include_router(module.router)
    app.add_middleware(NoStoreMiddleware)
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_body_bytes)
    return app
