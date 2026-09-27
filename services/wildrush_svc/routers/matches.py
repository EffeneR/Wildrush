"""Player-facing match endpoints: history, match detail, rejoin, private matches."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from starlette.concurrency import run_in_threadpool

from ..auth import PLAYER, Player
from ..context import AppContext, get_ctx
from ..errors import APIError
from ..logic import allocation, history, private
from ..schemas import PrivateCreateReq, PrivateJoinReq

router = APIRouter(prefix="/v1", tags=["matches"])

PRIVATE_POLL_INTERVAL_S = 0.2


# NOTE: /matches/history must be registered before /matches/{match_id}.
@router.get("/matches/history")
def match_history(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before: Annotated[datetime | None, Query()] = None,
    player: Player = Depends(PLAYER),
) -> list[dict[str, Any]]:
    ctx = get_ctx(request)
    if before is not None and before.tzinfo is None:
        before = before.replace(tzinfo=timezone.utc)
    with ctx.tx() as db:
        return history.history(db, player.account_id, limit=limit, before=before)


@router.get("/matches/{match_id}")
def match_detail(match_id: uuid.UUID, request: Request, player: Player = Depends(PLAYER)) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return history.match_detail(db, player.account_id, match_id)


@router.post("/matches/{match_id}/rejoin")
def rejoin(match_id: uuid.UUID, request: Request, player: Player = Depends(PLAYER)) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return allocation.rejoin(db, ctx, player.account_id, match_id)


def _create_private(ctx: AppContext, account_id: uuid.UUID, region: str) -> uuid.UUID:
    with ctx.tx() as db:
        return private.create(db, ctx, account_id, region)


def _private_info(ctx: AppContext, match_id: uuid.UUID, account_id: uuid.UUID) -> dict[str, Any] | None:
    with ctx.tx() as db:
        return private.creator_join_info(db, ctx, match_id, account_id)


def _cancel_private(ctx: AppContext, match_id: uuid.UUID) -> None:
    with ctx.tx() as db:
        private.cancel_if_allocating(db, ctx, match_id, "private_allocation_timeout")


@router.post("/private")
async def create_private(
    body: PrivateCreateReq, request: Request, player: Player = Depends(PLAYER)
) -> dict[str, Any]:
    """Allocates a server and waits (up to WR_PRIVATE_ALLOC_WAIT_S) until it is ready."""
    ctx = get_ctx(request)
    match_id = await run_in_threadpool(_create_private, ctx, player.account_id, body.region)
    deadline = time.monotonic() + ctx.settings.private_alloc_wait_s
    while True:
        info = await run_in_threadpool(_private_info, ctx, match_id, player.account_id)
        if info is not None:
            return info
        if time.monotonic() >= deadline:
            break
        await asyncio.sleep(PRIVATE_POLL_INTERVAL_S)
    await run_in_threadpool(_cancel_private, ctx, match_id)
    # The allocation may have completed just before the cancel; prefer success.
    try:
        info = await run_in_threadpool(_private_info, ctx, match_id, player.account_id)
    except APIError:
        info = None
    if info is not None:
        return info
    raise APIError(503, "allocation_timeout", "No game server started the private match in time")


@router.post("/private/join")
def join_private(body: PrivateJoinReq, request: Request, player: Player = Depends(PLAYER)) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return private.join(db, ctx, player.account_id, body.join_code, body.role)
