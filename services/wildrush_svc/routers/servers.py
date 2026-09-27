"""Server-signed endpoints (game servers / allocator hosts) and the public server browser."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request

from ..auth import ANON, ServerIdentity, require_server
from ..context import get_ctx
from ..logic import allocation, results, servers, tickets
from ..schemas import (
    AllocationEndedReq,
    AllocationStartedReq,
    EmptyBody,
    HeartbeatReq,
    PollReq,
    RedeemReq,
    ResultReq,
)

router = APIRouter(prefix="/v1", tags=["servers"])


@router.post("/servers/heartbeat")
def heartbeat(
    body: HeartbeatReq, request: Request, server: ServerIdentity = Depends(require_server)
) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return servers.heartbeat(db, server.server_id, body, ctx.clock.now())


@router.get("/servers", dependencies=[Depends(ANON)])
def server_browser(request: Request) -> list[dict[str, Any]]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return servers.browser(db, ctx.clock.now(), ctx.settings.server_stale_s)


@router.post("/allocator/poll")
def allocator_poll(
    body: PollReq, request: Request, server: ServerIdentity = Depends(require_server)
) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return allocation.poll(db, ctx, server.server_id, body.free_ports)


@router.post("/allocator/started")
def allocator_started(
    body: AllocationStartedReq, request: Request, server: ServerIdentity = Depends(require_server)
) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return allocation.allocation_started(db, ctx, server.server_id, body)


@router.post("/allocator/ended")
def allocator_ended(
    body: AllocationEndedReq, request: Request, server: ServerIdentity = Depends(require_server)
) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return allocation.allocation_ended(db, ctx, server.server_id, body)


@router.post("/matches/{match_id}/started")
def match_started(
    match_id: uuid.UUID,
    request: Request,
    body: EmptyBody | None = None,
    server: ServerIdentity = Depends(require_server),
) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return allocation.match_started(db, ctx, server.server_id, match_id)


@router.post("/servers/tickets/redeem")
def redeem_ticket(
    body: RedeemReq, request: Request, server: ServerIdentity = Depends(require_server)
) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return tickets.redeem(
            db, server_id=server.server_id, ticket_id=body.ticket_id, match_id=body.match_id, now=ctx.clock.now()
        )


@router.post("/matches/{match_id}/result")
def submit_result(
    match_id: uuid.UUID, body: ResultReq, request: Request, server: ServerIdentity = Depends(require_server)
) -> dict[str, Any]:
    ctx = get_ctx(request)
    with ctx.tx() as db:
        return results.submit(db, ctx, server.server_id, match_id, body)
