"""Periodic cleanup (runs inside each matchmaker tick)."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..context import AppContext
from ..models import Allocation, AuthSession, GameServer, Match, PartyInvite
from .allocation import cancel_match

log = logging.getLogger("wildrush_svc.janitor")


def run(db: Session, ctx: AppContext) -> None:
    now = ctx.clock.now()
    s = ctx.settings

    # 1. Allocations never confirmed as started -> cancel the match.
    alloc_cutoff = now - timedelta(seconds=s.allocation_timeout_s)
    stale_match_ids = db.scalars(
        select(Allocation.match_id).where(
            Allocation.state.in_(("pending", "assigned")), Allocation.created_at < alloc_cutoff
        )
    ).all()
    for match_id in stale_match_ids:
        match = db.scalar(select(Match).where(Match.id == match_id).with_for_update(skip_locked=True))
        if match is not None and match.state == "allocating":
            cancel_match(db, match, "allocation_timeout", now)

    # 2. Ready/running matches whose host stopped heartbeating, or that are far too old.
    lost_cutoff = now - timedelta(seconds=s.host_lost_s)
    age_cutoff = now - timedelta(seconds=s.match_max_age_s)
    rows = db.execute(
        select(Match.id, Match.created_at, GameServer.last_heartbeat_at)
        .join(GameServer, GameServer.id == Match.server_id)
        .where(Match.state.in_(("ready", "running")))
    ).all()
    for match_id, created_at, last_hb in rows:
        reason = None
        if last_hb is None or last_hb < lost_cutoff:
            reason = "server_lost"
        elif created_at < age_cutoff:
            reason = "max_age_exceeded"
        if reason is None:
            continue
        match = db.scalar(select(Match).where(Match.id == match_id).with_for_update(skip_locked=True))
        if match is not None and cancel_match(db, match, reason, now):
            alloc = db.scalar(select(Allocation).where(Allocation.match_id == match_id))
            if alloc is not None and alloc.state == "started":
                alloc.state = "cancelled"
                alloc.ended_at = now
                alloc.end_reason = reason

    # 3. Expired invites and long-expired sessions.
    db.execute(
        update(PartyInvite)
        .where(PartyInvite.status == "pending", PartyInvite.expires_at <= now)
        .values(status="expired")
    )
    db.execute(delete(AuthSession).where(AuthSession.expires_at < now - timedelta(days=7)))
