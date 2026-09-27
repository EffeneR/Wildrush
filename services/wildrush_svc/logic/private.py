"""Private (online) matches: allocation + join codes + observer role. Never rated."""

from __future__ import annotations

import secrets
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..context import AppContext
from ..errors import APIError, conflict, not_found
from ..models import Allocation, GameServer, Match, MatchParticipant
from .common import ACTIVE_MATCH_STATES, available_hosts, queue_entry_of
from .tickets import issue_ticket, latest_ticket, ticket_view

JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L ambiguity
JOIN_CODE_LEN = 8
ALLOCATION_LOCK_KEY = 0x5752_4D4D  # shared with the matchmaker (serializes capacity use)


def new_join_code() -> str:
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LEN))


def create(db: Session, ctx: AppContext, account_id: uuid.UUID, region: str) -> uuid.UUID:
    now = ctx.clock.now()
    if queue_entry_of(db, account_id) is not None:
        raise conflict("already_queued", "Leave the queue before creating a private match")
    hosting = db.scalar(
        select(Match.id).where(
            Match.created_by == account_id,
            Match.mode == "private",
            Match.state.in_(ACTIVE_MATCH_STATES),
        )
    )
    if hosting is not None:
        raise conflict("already_hosting", f"You already host active private match {hosting}")
    # Serialize with the matchmaker so both do not hand out the same last slot.
    db.execute(select(func.pg_advisory_xact_lock(ALLOCATION_LOCK_KEY)))
    hosts = available_hosts(db, now=now, stale_s=ctx.settings.server_stale_s, region=region)
    if not hosts:
        raise APIError(503, "no_server_available", f"No game server with free capacity in region {region!r}")
    server, _free = max(hosts, key=lambda h: (h[1], h[0].id))
    match_id = uuid.uuid4()
    for _attempt in range(8):
        code = new_join_code()
        try:
            with db.begin_nested():
                db.add(
                    Match(
                        id=match_id,
                        mode="private",
                        state="allocating",
                        region=region,
                        server_id=server.id,
                        host=None,
                        port=None,
                        join_code=code,
                        created_by=account_id,
                        expected_players=1,
                        bot_slots=0,
                        created_at=now,
                    )
                )
                db.flush()
            break
        except IntegrityError:
            continue
    else:  # pragma: no cover - 31^8 code space
        raise APIError(503, "join_code_exhausted", "Could not allocate a join code; retry")
    db.add(
        MatchParticipant(
            match_id=match_id,
            account_id=account_id,
            team=-1,
            role="player",
            lobby_admin=True,
            party_id=None,
            roster_prefs=[],
            joined_at=now,
        )
    )
    db.add(
        Allocation(
            id=uuid.uuid4(),
            match_id=match_id,
            server_id=server.id,
            state="pending",
            created_at=now,
        )
    )
    db.flush()
    return match_id


def creator_join_info(db: Session, ctx: AppContext, match_id: uuid.UUID, account_id: uuid.UUID) -> dict[str, Any] | None:
    """``None`` while allocating; the create response once ready; raises if it failed."""
    match = db.get(Match, match_id)
    if match is None:
        raise not_found("match_not_found", "Match not found")
    if match.state == "allocating":
        return None
    if match.state not in ("ready", "running"):
        raise APIError(503, "allocation_failed", f"Private match could not be started ({match.cancel_reason})")
    participant = db.get(MatchParticipant, (match_id, account_id))
    server = db.get(GameServer, match.server_id) if match.server_id else None
    if participant is None or server is None:
        raise not_found("match_not_found", "Match not found")
    now = ctx.clock.now()
    ticket = latest_ticket(db, match_id, account_id)
    if ticket is None or ticket.redeemed_at is not None or ticket.expires_at <= now:
        ticket = issue_ticket(
            db, match=match, participant=participant, server=server, now=now,
            ttl_s=ctx.settings.ticket_ttl_s,
        )
    return {
        "match_id": str(match.id),
        "join_code": match.join_code,
        "host": match.host,
        "port": match.port,
        "role": participant.role,
        **ticket_view(ticket),
    }


def cancel_if_allocating(db: Session, ctx: AppContext, match_id: uuid.UUID, reason: str) -> None:
    from .allocation import cancel_match, lock_match

    match = lock_match(db, match_id)
    if match is not None and match.state == "allocating":
        cancel_match(db, match, reason, ctx.clock.now())


def join(
    db: Session, ctx: AppContext, account_id: uuid.UUID, join_code: str, role: str
) -> dict[str, Any]:
    now = ctx.clock.now()
    code = join_code.upper()
    match = db.scalar(select(Match).where(Match.join_code == code).with_for_update())
    if match is None or match.mode != "private" or match.state in ("finished", "cancelled"):
        raise not_found("invalid_join_code", "No open private match with that code")
    if match.state == "allocating":
        raise conflict("match_not_ready", "The private match is still starting; retry shortly")
    if queue_entry_of(db, account_id) is not None:
        raise conflict("already_queued", "Leave the queue before joining a private match")
    counts = dict(
        db.execute(
            select(MatchParticipant.role, func.count())
            .where(MatchParticipant.match_id == match.id, MatchParticipant.account_id != account_id)
            .group_by(MatchParticipant.role)
        ).all()
    )
    limit = ctx.settings.private_max_players if role == "player" else ctx.settings.private_max_observers
    if int(counts.get(role, 0)) >= limit:
        raise conflict("match_full", f"No free {role} slots in this private match")
    participant = db.get(MatchParticipant, (match.id, account_id))
    if participant is None:
        participant = MatchParticipant(
            match_id=match.id,
            account_id=account_id,
            team=-1,
            role=role,
            lobby_admin=False,
            party_id=None,
            roster_prefs=[],
            joined_at=now,
        )
        db.add(participant)
    else:
        participant.role = role
    db.flush()
    server = db.get(GameServer, match.server_id) if match.server_id else None
    if server is None:
        raise conflict("match_not_ready", "Private match server unavailable")
    ticket = issue_ticket(
        db, match=match, participant=participant, server=server, now=now, ttl_s=ctx.settings.ticket_ttl_s
    )
    return {
        "match_id": str(match.id),
        "host": match.host,
        "port": match.port,
        "role": role,
        **ticket_view(ticket),
    }
