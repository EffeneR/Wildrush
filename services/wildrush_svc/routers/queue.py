"""/v1/queue"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from ..auth import PLAYER, PLAYER_QUEUE, Player
from ..context import get_ctx
from ..logic import queue
from ..schemas import QueueJoinReq

router = APIRouter(prefix="/v1", tags=["queue"])


@router.post("/queue", status_code=202)
def join_queue(body: QueueJoinReq, request: Request, player: Player = Depends(PLAYER_QUEUE)) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return queue.join(db, ctx, player.account_id, body)


@router.delete("/queue", status_code=204)
def leave_queue(request: Request, player: Player = Depends(PLAYER_QUEUE)) -> Response:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        queue.leave(db, ctx, player.account_id)
    return Response(status_code=204)


@router.get("/queue/status")
def queue_status(request: Request, player: Player = Depends(PLAYER)) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return queue.status(db, ctx, player.account_id)
