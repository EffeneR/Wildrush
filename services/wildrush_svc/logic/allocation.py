"""Match allocation lifecycle: allocator poll / started / ended, server match start, rejoin."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import iso_utc
from ..context import AppContext
from ..errors import conflict, forbidden, not_found
from ..models import Allocation, GameServer, Match, MatchParticipant
from ..schemas import AllocationEndedReq, AllocationStartedReq
from .common import ACTIVE_MATCH_STATES
from .tickets import issue_ticket

log = logging.getLogger("wildrush_svc.allocation")


def lock_match(db: Session, match_id: uuid.UUID) -> Match | None:
    return db.scalar(select(Match).where(Match.id == match_id).with_for_update())


def cancel_match(db: Session, match: Match, reason: str, now: datetime) -> bool:
    """Cancel an unfinished match (caller holds the row lock). Returns True if changed."""
    if match.state not in ACTIVE_MATCH_STATES:
        return False
    match.state = "cancelled"
    match.ended_at = now
    match.cancel_reason = reason[:200]
    alloc = db.scalar(select(Allocation).where(Allocation.match_id == match.id).with_for_update())
    if alloc is not None and alloc.state in ("pending", "assigned"):
        alloc.state = "cancelled"
        alloc.ended_at = now
        alloc.end_reason = reason[:200]
    log.info("match %s cancelled: %s", match.id, reason)
    return True


def poll(db: Session, ctx: AppContext, server_id: str, free_ports: list[int]) -> dict[str, Any]:
    now = ctx.clock.now()
    server = db.scalar(select(GameServer).where(GameServer.id == server_id).with_for_update())
    if server is None:
        raise not_found("unknown_server", "Unknown server")
    server.last_poll_at = now
    out: list[dict[str, Any]] = []
    if server.port_min is None or server.port_max is None:
        return {"allocations": out}  # no heartbeat yet: port range unknown
    allocations = db.scalars(
        select(Allocation)
        .where(Allocation.server_id == server_id, Allocation.state.in_(("pending", "assigned", "started")))
        .order_by(Allocation.created_at, Allocation.id)
        .with_for_update()
    ).all()
    in_use = {a.port for a in allocations if a.state in ("assigned", "started") and a.port is not None}
    available = sorted(
        {p for p in free_ports if server.port_min <= p <= server.port_max and p not in in_use}
    )
    matches = {
        m.id: m
        for m in db.scalars(select(Match).where(Match.id.in_([a.match_id for a in allocations]))).all()
    }
    for alloc in allocations:
        match = matches.get(alloc.match_id)
        if match is None or match.state != "allocating":
            continue
        if alloc.state == "assigned":
            # Not yet confirmed as started: hand it out again (the previous response may
            # have been lost). The agent de-duplicates by allocation_id.
            out.append(_allocation_view(alloc, match))
        elif alloc.state == "pending" and available:
            alloc.port = available.pop(0)
            alloc.state = "assigned"
            alloc.assigned_at = now
            out.append(_allocation_view(alloc, match))
    db.flush()
    return {"allocations": out}


def _allocation_view(alloc: Allocation, match: Match) -> dict[str, Any]:
    return {
        "allocation_id": str(alloc.id),
        "match_id": str(match.id),
        "mode": match.mode,
        "port": alloc.port,
        "expected_players": match.expected_players,
    }


def _server_allocation(
    db: Session, server_id: str, allocation_id: uuid.UUID, match_id: uuid.UUID
) -> tuple[Allocation, Match]:
    # Lock order everywhere: match row first, then its allocation (no deadlock cycles).
    match = lock_match(db, match_id)
    alloc = (
        db.scalar(select(Allocation).where(Allocation.id == allocation_id).with_for_update())
        if match is not None
        else None
    )
    if match is None or alloc is None or alloc.server_id != server_id or alloc.match_id != match_id:
        raise not_found("allocation_not_found", "Allocation not found for this server")
    return alloc, match


def allocation_started(
    db: Session, ctx: AppContext, server_id: str, body: AllocationStartedReq
) -> dict[str, Any]:
    now = ctx.clock.now()
    alloc, match = _server_allocation(db, server_id, body.allocation_id, body.match_id)
    if alloc.state == "started":
        if alloc.port != body.port:
            raise conflict("port_mismatch", "Allocation already started on another port")
        alloc.pid = body.pid
        return {"ok": True}
    if alloc.state in ("cancelled", "ended") or match.state not in ("allocating",):
        raise conflict("allocation_cancelled", "The match was cancelled; stop the process")
    if alloc.state != "assigned":
        raise conflict("not_assigned", "Allocation has no port assigned yet")
    if alloc.port != body.port:
        raise conflict("port_mismatch", "Reported port differs from the assigned port")
    server = db.get(GameServer, server_id)
    if server is None or not server.host:
        raise conflict("no_host", "Heartbeat with a public host before starting matches")
    alloc.state = "started"
    alloc.pid = body.pid
    alloc.started_at = now
    match.state = "ready"
    match.host = server.host
    match.port = alloc.port
    match.ready_at = now
    # One join ticket per player (queue matches) / for the lobby admin (private).
    participants = db.scalars(
        select(MatchParticipant).where(MatchParticipant.match_id == match.id)
    ).all()
    for participant in participants:
        if match.mode == "private" and not participant.lobby_admin:
            continue
        issue_ticket(
            db, match=match, participant=participant, server=server, now=now,
            ttl_s=ctx.settings.ticket_ttl_s,
        )
    log.info("match %s ready on %s:%s (%s)", match.id, server.id, alloc.port, match.mode)
    return {"ok": True}


def allocation_ended(
    db: Session, ctx: AppContext, server_id: str, body: AllocationEndedReq
) -> dict[str, Any]:
    now = ctx.clock.now()
    alloc, match = _server_allocation(db, server_id, body.allocation_id, body.match_id)
    if alloc.state != "ended":
        alloc.state = "ended"
        alloc.ended_at = now
        alloc.exit_code = body.exit_code
        alloc.end_reason = body.reason[:200]
    # Cancels the match if no result was submitted.
    cancel_match(db, match, f"server_ended: {body.reason}"[:200], now)
    return {"ok": True}


def match_started(db: Session, ctx: AppContext, server_id: str, match_id: uuid.UUID) -> dict[str, Any]:
    now = ctx.clock.now()
    match = lock_match(db, match_id)
    if match is None:
        raise not_found("match_not_found", "Match not found")
    if match.server_id != server_id:
        raise forbidden("wrong_server", "This match is allocated to another server")
    if match.state == "running":
        return {"ok": True, "state": "running"}
    if match.state != "ready":
        raise conflict("invalid_state", f"Match is {match.state}")
    match.state = "running"
    match.started_at = now
    return {"ok": True, "state": "running"}


def rejoin(db: Session, ctx: AppContext, account_id: uuid.UUID, match_id: uuid.UUID) -> dict[str, Any]:
    now = ctx.clock.now()
    match = db.get(Match, match_id)
    participant = db.get(MatchParticipant, (match_id, account_id)) if match else None
    if match is None or participant is None:
        raise not_found("match_not_found", "Match not found")
    if match.state != "running" or match.server_id is None:
        raise conflict("match_not_running", f"Match is {match.state}")
    server = db.get(GameServer, match.server_id)
    if server is None:
        raise conflict("match_not_running", "Match server unavailable")
    ticket = issue_ticket(
        db, match=match, participant=participant, server=server, now=now, ttl_s=ctx.settings.ticket_ttl_s
    )
    return {
        "match_id": str(match.id),
        "host": match.host,
        "port": match.port,
        "ticket": ticket.token,
        "expires_at": iso_utc(ticket.expires_at),
        "team": participant.team,
        "role": participant.role,
    }
