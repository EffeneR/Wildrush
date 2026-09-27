"""/v1/auth/*, /v1/me, /v1/profile"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from .. import ratelimit as rl
from ..auth import PLAYER, Player, limit_ip
from ..clock import iso_utc
from ..context import get_ctx
from ..errors import rate_limited
from ..logic import accounts, profile
from ..schemas import LoginReq, ProfilePatchReq, RegisterReq

router = APIRouter(prefix="/v1", tags=["accounts"])


@router.post("/auth/register", status_code=201, dependencies=[Depends(limit_ip(rl.REGISTER_PER_IP))])
def register(body: RegisterReq, request: Request) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        account = accounts.register(
            db,
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            now=ctx.clock.now(),
        )
        return {
            "account_id": str(account.id),
            "username": account.username,
            "display_name": account.display_name,
        }


@router.post("/auth/login", dependencies=[Depends(limit_ip(rl.LOGIN_PER_IP))])
def login(body: LoginReq, request: Request) -> dict[str, Any]:
    ctx = get_ctx(request)
    retry = ctx.limiter.hit(rl.LOGIN_PER_USERNAME, body.username.lower())
    if retry is not None:
        raise rate_limited(retry)
    with ctx.tx() as db:
        token, expires_at, account = accounts.login(
            db,
            username=body.username,
            password=body.password,
            now=ctx.clock.now(),
            ttl=timedelta(hours=ctx.settings.session_ttl_h),
        )
        return {
            "token": token,
            "expires_at": iso_utc(expires_at),
            "account": accounts.me_view(db, account.id),
        }


@router.post("/auth/logout", status_code=204)
def logout(request: Request, player: Player = Depends(PLAYER)) -> Response:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        accounts.logout(db, player.session_id, now=ctx.clock.now())
    return Response(status_code=204)


@router.get("/me")
def me(request: Request, player: Player = Depends(PLAYER)) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return accounts.me_view(db, player.account_id)


@router.get("/profile")
def get_profile(request: Request, player: Player = Depends(PLAYER)) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return profile.profile_view(db, player.account_id)


@router.patch("/profile")
def patch_profile(body: ProfilePatchReq, request: Request, player: Player = Depends(PLAYER)) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return profile.patch_profile(db, player.account_id, body)
