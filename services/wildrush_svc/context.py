"""Per-application shared state (settings, DB, clock, limiter)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from fastapi import Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from .clock import Clock
from .config import Settings
from .ratelimit import RateLimiter


@dataclass
class AppContext:
    settings: Settings
    engine: Engine
    sessionmaker: sessionmaker[Session]
    clock: Clock
    limiter: RateLimiter
    extras: dict[str, object] = field(default_factory=dict)

    @contextmanager
    def tx(self) -> Iterator[Session]:
        """One database transaction: commit on success, rollback on any exception."""
        with self.sessionmaker.begin() as db:
            yield db


def get_ctx(request: Request) -> AppContext:
    ctx: AppContext = request.app.state.ctx
    return ctx


def client_ip(request: Request) -> str:
    # uvicorn's ProxyHeadersMiddleware rewrites the client from X-Forwarded-For when the
    # direct peer is listed in WR_FORWARDED_ALLOW_IPS.
    return request.client.host if request.client else "unknown"
