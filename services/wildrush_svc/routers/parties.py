"""/v1/parties/*, /v1/invites/*"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from ..auth import PLAYER, PLAYER_INVITES, Player
from ..context import get_ctx
from ..logic import parties
from ..schemas import AccountRefReq, InviteReq

router = APIRouter(prefix="/v1", tags=["parties"])


@router.post("/parties", status_code=201)
def create_party(request: Request, player: Player = Depends(PLAYER)) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return parties.create_party(db, player.account_id, ctx.clock.now())


@router.get("/parties/current")
def current_party(request: Request, player: Player = Depends(PLAYER)) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return parties.current_party(db, player.account_id, ctx.clock.now())


@router.post("/parties/current/invites", status_code=201)
def invite(body: InviteReq, request: Request, player: Player = Depends(PLAYER_INVITES)) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return parties.invite(
            db, player.account_id, body.username, ctx.clock.now(), timedelta(seconds=ctx.settings.invite_ttl_s)
        )


@router.get("/invites")
def my_invites(request: Request, player: Player = Depends(PLAYER)) -> list[dict[str, Any]]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return parties.my_invites(db, player.account_id, ctx.clock.now())


@router.post("/invites/{invite_id}/accept")
def accept(invite_id: uuid.UUID, request: Request, player: Player = Depends(PLAYER)) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return parties.accept_invite(db, player.account_id, invite_id, ctx.clock.now())


@router.post("/invites/{invite_id}/decline", status_code=204)
def decline(invite_id: uuid.UUID, request: Request, player: Player = Depends(PLAYER)) -> Response:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        parties.decline_invite(db, player.account_id, invite_id, ctx.clock.now())
    return Response(status_code=204)


@router.post("/parties/current/leave", status_code=204)
def leave(request: Request, player: Player = Depends(PLAYER)) -> Response:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        parties.leave(db, player.account_id)
    return Response(status_code=204)


@router.post("/parties/current/kick", status_code=204)
def kick(body: AccountRefReq, request: Request, player: Player = Depends(PLAYER)) -> Response:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        parties.kick(db, player.account_id, body.account_id)
    return Response(status_code=204)


@router.post("/parties/current/promote", status_code=204)
def promote(body: AccountRefReq, request: Request, player: Player = Depends(PLAYER)) -> Response:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        parties.promote(db, player.account_id, body.account_id)
    return Response(status_code=204)
