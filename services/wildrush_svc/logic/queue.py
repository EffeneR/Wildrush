"""Queue join / leave / status."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..context import AppContext
from ..errors import conflict, forbidden, unprocessable
from ..models import GameServer, Match, MatchParticipant, Party, QueueEntry, QueueMember
from ..schemas import QueueJoinReq
from .common import active_queue_match, party_id_of, queue_counts, queue_entry_of
from .parties import party_member_ids
from .tickets import issue_ticket, latest_ticket, ticket_view


def join(db: Session, ctx: AppContext, account_id: uuid.UUID, body: QueueJoinReq) -> dict[str, Any]:
    now = ctx.clock.now()
    if body.mode == "ranked" and body.allow_bots:
        raise unprocessable("bots_in_ranked", "Ranked matches never use bots (allow_bots must be false)")
    party_id = party_id_of(db, account_id)
    if party_id is not None:
        party = db.scalar(select(Party).where(Party.id == party_id).with_for_update())
        if party is None:
            party_id = None
            members = [account_id]
        else:
            if party.leader_id != account_id:
                raise forbidden("not_leader", "Only the party leader can queue the party")
            members = party_member_ids(db, party.id)
    else:
        members = [account_id]
    for member in members:
        if queue_entry_of(db, member) is not None:
            raise conflict("already_queued", "Already in a queue")
        if active_queue_match(db, member) is not None:
            raise conflict("already_in_match", "A party member is already in an active match")
    entry = QueueEntry(
        id=uuid.uuid4(),
        mode=body.mode,
        leader_id=account_id,
        party_id=party_id,
        region=body.region,
        latency_ms=dict(body.latency_ms),
        allow_bots=bool(body.allow_bots),
        roster_prefs=list(body.roster_prefs),
        queued_at=now,
    )
    db.add(entry)
    db.flush()
    for member in members:
        db.add(QueueMember(entry_id=entry.id, account_id=member))
    try:
        db.flush()
    except IntegrityError as exc:
        raise conflict("already_queued", "Already in a queue") from exc
    return status(db, ctx, account_id)


def leave(db: Session, ctx: AppContext, account_id: uuid.UUID) -> None:
    entry = queue_entry_of(db, account_id)
    if entry is not None:
        # Blocks while a matchmaker tick holds the row; afterwards the row is either still
        # queued (delete it) or gone because it was matched.
        locked = db.scalar(select(QueueEntry).where(QueueEntry.id == entry.id).with_for_update())
        if locked is not None:
            db.delete(locked)
            db.flush()
            return
    if active_queue_match(db, account_id) is not None:
        raise conflict("already_matched", "A match was already found")
    # Not queued: idempotent no-op.


def _match_view(
    db: Session, ctx: AppContext, match: Match, participant: MatchParticipant, now: datetime
) -> dict[str, Any]:
    view: dict[str, Any] = {
        "match_id": str(match.id),
        "mode": match.mode,
        "state": match.state,
        "team": participant.team,
        "host": None,
        "port": None,
        "ticket": None,
        "expires_at": None,
    }
    if match.state not in ("ready", "running") or match.server_id is None:
        return view
    view["host"] = match.host
    view["port"] = match.port
    ticket = latest_ticket(db, match.id, participant.account_id)
    if ticket is not None and ticket.redeemed_at is not None:
        # Already connected once; reconnects use POST /v1/matches/{id}/rejoin.
        return view
    if ticket is None or ticket.expires_at <= now:
        server = db.get(GameServer, match.server_id)
        if server is None:
            return view
        ticket = issue_ticket(
            db, match=match, participant=participant, server=server, now=now,
            ttl_s=ctx.settings.ticket_ttl_s,
        )
    view.update(ticket_view(ticket))
    return view


def status(db: Session, ctx: AppContext, account_id: uuid.UUID) -> dict[str, Any]:
    now = ctx.clock.now()
    counts = queue_counts(db)
    entry = queue_entry_of(db, account_id)
    if entry is not None:
        return {
            "state": "queued",
            "mode": entry.mode,
            "queued_seconds": max(0, int((now - entry.queued_at).total_seconds())),
            "counts": counts,
            "match": None,
        }
    active = active_queue_match(db, account_id)
    if active is not None:
        match, participant = active
        return {
            "state": "matched",
            "mode": match.mode,
            "queued_seconds": None,
            "counts": counts,
            "match": _match_view(db, ctx, match, participant, now),
        }
    return {"state": "idle", "mode": None, "queued_seconds": None, "counts": counts, "match": None}
