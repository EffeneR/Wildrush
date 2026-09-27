"""Helpers shared by several logic modules."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import (
    Account,
    GameServer,
    Match,
    MatchParticipant,
    PartyMember,
    QueueEntry,
    QueueMember,
)

ACTIVE_MATCH_STATES = ("allocating", "ready", "running")
QUEUE_MODES = ("casual", "ranked")


def party_id_of(db: Session, account_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(select(PartyMember.party_id).where(PartyMember.account_id == account_id))


def queue_entry_of(db: Session, account_id: uuid.UUID) -> QueueEntry | None:
    return db.scalar(
        select(QueueEntry)
        .join(QueueMember, QueueMember.entry_id == QueueEntry.id)
        .where(QueueMember.account_id == account_id)
    )


def remove_queue_entries_for_party(db: Session, party_id: uuid.UUID) -> int:
    """Joining/leaving a party removes it from any queue (contract)."""
    result = db.execute(delete(QueueEntry).where(QueueEntry.party_id == party_id))
    return int(result.rowcount or 0)


def remove_queue_entry_for_account(db: Session, account_id: uuid.UUID) -> int:
    entry_ids = select(QueueMember.entry_id).where(QueueMember.account_id == account_id)
    result = db.execute(delete(QueueEntry).where(QueueEntry.id.in_(entry_ids)))
    return int(result.rowcount or 0)


def active_queue_match(db: Session, account_id: uuid.UUID) -> tuple[Match, MatchParticipant] | None:
    """The account's current casual/ranked match that is still allocating/ready/running."""
    row = db.execute(
        select(Match, MatchParticipant)
        .join(MatchParticipant, MatchParticipant.match_id == Match.id)
        .where(
            MatchParticipant.account_id == account_id,
            MatchParticipant.role == "player",
            Match.mode.in_(QUEUE_MODES),
            Match.state.in_(ACTIVE_MATCH_STATES),
        )
        .order_by(Match.created_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return row[0], row[1]


def queue_counts(db: Session) -> dict[str, int]:
    """Real numbers of queued players per mode (no invented players)."""
    counts = {mode: 0 for mode in QUEUE_MODES}
    rows = db.execute(
        select(QueueEntry.mode, func.count(QueueMember.account_id))
        .join(QueueMember, QueueMember.entry_id == QueueEntry.id)
        .group_by(QueueEntry.mode)
    ).all()
    for mode, count in rows:
        counts[mode] = int(count)
    return counts


def account_brief(account: Account) -> dict[str, str]:
    return {
        "account_id": str(account.id),
        "username": account.username,
        "display_name": account.display_name,
    }


def available_hosts(
    db: Session, *, now: datetime, stale_s: float, region: str | None = None
) -> list[tuple[GameServer, int]]:
    """Online, enabled, fresh allocator hosts with free match slots: ``[(server, free)]``."""
    from datetime import timedelta

    from ..models import Allocation

    busy = (
        select(Allocation.server_id, func.count().label("busy"))
        .where(Allocation.state.in_(("pending", "assigned", "started")))
        .group_by(Allocation.server_id)
        .subquery()
    )
    stmt = (
        select(GameServer, func.coalesce(busy.c.busy, 0))
        .outerjoin(busy, busy.c.server_id == GameServer.id)
        .where(
            GameServer.enabled.is_(True),
            GameServer.status == "online",
            GameServer.host.is_not(None),
            GameServer.last_heartbeat_at.is_not(None),
            GameServer.last_heartbeat_at >= now - timedelta(seconds=stale_s),
        )
        .order_by(GameServer.id)
    )
    if region is not None:
        stmt = stmt.where(GameServer.region == region)
    hosts = []
    for server, busy_count in db.execute(stmt).all():
        free = server.capacity - int(busy_count)
        if free > 0:
            hosts.append((server, free))
    return hosts
