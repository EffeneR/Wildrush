"""Authentication dependencies: player bearer sessions and server HMAC request signing."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from . import ratelimit as rl
from .context import AppContext, client_ip, get_ctx
from .errors import APIError, rate_limited
from .models import Account, AuthSession, GameServer
from .security import (
    SERVER_ID_RE,
    SIGNATURE_RE,
    TIMESTAMP_RE,
    hash_token,
    is_token_shaped,
    verify_request_signature,
)

TIMESTAMP_WINDOW_S = 60


@dataclass(frozen=True)
class Player:
    account_id: uuid.UUID
    session_id: uuid.UUID
    username: str


@dataclass(frozen=True)
class ServerIdentity:
    server_id: str
    region: str


def _unauthorized(message: str = "Missing, invalid or expired session token") -> APIError:
    return APIError(401, "unauthorized", message, headers={"WWW-Authenticate": "Bearer"})


def resolve_session(ctx: AppContext, authorization: str | None) -> Player | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not is_token_shaped(token):
        return None
    now = ctx.clock.now()
    with ctx.tx() as db:
        row = db.execute(
            select(AuthSession.id, AuthSession.account_id, Account.username)
            .join(Account, Account.id == AuthSession.account_id)
            .where(
                AuthSession.token_hash == hash_token(token),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        ).first()
    if row is None:
        return None
    return Player(account_id=row.account_id, session_id=row.id, username=row.username)


def require_player(limit: rl.Limit = rl.GENERAL_PER_ACCOUNT) -> Callable[[Request], Player]:
    """Dependency factory: authenticated player + per-account rate limit bucket."""

    def dependency(request: Request) -> Player:
        ctx = get_ctx(request)
        player = resolve_session(ctx, request.headers.get("authorization"))
        if player is None:
            retry = ctx.limiter.hit(rl.ANON_PER_IP, client_ip(request))
            if retry is not None:
                raise rate_limited(retry)
            raise _unauthorized()
        retry = ctx.limiter.hit(limit, str(player.account_id))
        if retry is not None:
            raise rate_limited(retry)
        return player

    return dependency


def limit_ip(limit: rl.Limit) -> Callable[[Request], None]:
    """Dependency factory: per-client-IP rate limit (unauthenticated endpoints)."""

    def dependency(request: Request) -> None:
        ctx = get_ctx(request)
        retry = ctx.limiter.hit(limit, client_ip(request))
        if retry is not None:
            raise rate_limited(retry)

    return dependency


PLAYER = require_player(rl.GENERAL_PER_ACCOUNT)
PLAYER_INVITES = require_player(rl.INVITES_PER_ACCOUNT)
PLAYER_QUEUE = require_player(rl.QUEUE_PER_ACCOUNT)
ANON = limit_ip(rl.ANON_PER_IP)


def request_path_for_signing(request: Request) -> str:
    """PATH exactly as sent on the request line (raw path + "?" + raw query string)."""
    raw_path = request.scope.get("raw_path")
    path = raw_path.decode("latin-1") if raw_path else request.url.path
    query = request.scope.get("query_string", b"")
    if query:
        path = path + "?" + query.decode("latin-1")
    return path


def _verify_server(
    ctx: AppContext, server_id: str, method: str, path: str, timestamp: str, body: bytes, signature: str
) -> ServerIdentity | None:
    with ctx.tx() as db:
        row = db.execute(
            select(GameServer.id, GameServer.secret, GameServer.region, GameServer.enabled).where(
                GameServer.id == server_id
            )
        ).first()
    if row is None or not row.enabled:
        return None
    if not verify_request_signature(row.secret, method, path, timestamp, body, signature):
        return None
    return ServerIdentity(server_id=row.id, region=row.region)


async def require_server(request: Request) -> ServerIdentity:
    """Server/allocator request signing (``X-WR-Server``, ``X-WR-Timestamp``, ``X-WR-Signature``)."""
    ctx = get_ctx(request)
    server_id = request.headers.get("x-wr-server", "")
    timestamp = request.headers.get("x-wr-timestamp", "")
    signature = request.headers.get("x-wr-signature", "")
    if not (
        SERVER_ID_RE.fullmatch(server_id)
        and TIMESTAMP_RE.fullmatch(timestamp)
        and SIGNATURE_RE.fullmatch(signature.lower())
    ):
        retry = ctx.limiter.hit(rl.ANON_PER_IP, client_ip(request))
        if retry is not None:
            raise rate_limited(retry)
        raise APIError(401, "server_auth_required", "Missing or malformed server signature headers")
    now_unix = int(ctx.clock.now().timestamp())
    if abs(now_unix - int(timestamp)) > TIMESTAMP_WINDOW_S:
        raise APIError(401, "timestamp_skew", "X-WR-Timestamp outside the +/-60 s window; check the clock")
    body = await request.body()
    path = request_path_for_signing(request)
    identity = await run_in_threadpool(
        _verify_server, ctx, server_id, request.method, path, timestamp, body, signature
    )
    if identity is None:
        retry = ctx.limiter.hit(rl.ANON_PER_IP, client_ip(request))
        if retry is not None:
            raise rate_limited(retry)
        raise APIError(401, "invalid_signature", "Unknown server, disabled server or bad signature")
    server_limit = rl.Limit("server", ctx.settings.server_rate_limit_per_min)
    retry = ctx.limiter.hit(server_limit, identity.server_id)
    if retry is not None:
        raise rate_limited(retry)
    return identity
