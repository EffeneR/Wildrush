"""Parties: max 5 members, one party per account, invites expire after 5 minutes."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..clock import iso_utc
from ..errors import conflict, forbidden, not_found
from ..models import Account, Party, PartyInvite, PartyMember, QueueEntry
from .common import (
    account_brief,
    active_queue_match,
    party_id_of,
    remove_queue_entries_for_party,
    remove_queue_entry_for_account,
)

MAX_PARTY_SIZE = 5
MAX_PENDING_INVITES = 10


def _lock_party(db: Session, party_id: uuid.UUID) -> Party | None:
    return db.scalar(select(Party).where(Party.id == party_id).with_for_update())


def _current_party_locked(db: Session, account_id: uuid.UUID) -> Party:
    party_id = party_id_of(db, account_id)
    if party_id is None:
        raise not_found("no_party", "You are not in a party")
    party = _lock_party(db, party_id)
    if party is None:  # deleted concurrently
        raise not_found("no_party", "You are not in a party")
    # Re-check membership under the lock.
    if party_id_of(db, account_id) != party.id:
        raise not_found("no_party", "You are not in a party")
    return party


def _member_count(db: Session, party_id: uuid.UUID) -> int:
    return int(
        db.scalar(select(func.count()).select_from(PartyMember).where(PartyMember.party_id == party_id))
        or 0
    )


def _members(db: Session, party_id: uuid.UUID) -> list[tuple[PartyMember, Account]]:
    return [
        (row[0], row[1])
        for row in db.execute(
            select(PartyMember, Account)
            .join(Account, Account.id == PartyMember.account_id)
            .where(PartyMember.party_id == party_id)
            .order_by(PartyMember.joined_at, PartyMember.account_id)
        ).all()
    ]


def _queue_view(db: Session, party: Party, now: datetime) -> dict[str, Any] | None:
    entry = db.scalar(select(QueueEntry).where(QueueEntry.party_id == party.id))
    if entry is not None:
        return {
            "state": "queued",
            "mode": entry.mode,
            "region": entry.region,
            "allow_bots": entry.allow_bots,
            "queued_seconds": max(0, int((now - entry.queued_at).total_seconds())),
            "match_id": None,
        }
    active = active_queue_match(db, party.leader_id)
    if active is not None:
        match, _ = active
        return {
            "state": "matched",
            "mode": match.mode,
            "region": match.region,
            "allow_bots": match.bot_slots > 0,
            "queued_seconds": None,
            "match_id": str(match.id),
        }
    return None


def party_view(db: Session, party: Party, now: datetime) -> dict[str, Any]:
    invites = db.execute(
        select(PartyInvite, Account.username)
        .join(Account, Account.id == PartyInvite.to_account_id)
        .where(
            PartyInvite.party_id == party.id,
            PartyInvite.status == "pending",
            PartyInvite.expires_at > now,
        )
        .order_by(PartyInvite.created_at)
    ).all()
    return {
        "party_id": str(party.id),
        "leader_id": str(party.leader_id),
        "members": [account_brief(account) for _, account in _members(db, party.id)],
        "invites": [
            {"invite_id": str(inv.id), "to_username": username, "expires_at": iso_utc(inv.expires_at)}
            for inv, username in invites
        ],
        "queue": _queue_view(db, party, now),
    }


def create_party(db: Session, account_id: uuid.UUID, now: datetime) -> dict[str, Any]:
    if party_id_of(db, account_id) is not None:
        raise conflict("already_in_party", "You are already in a party")
    if active_queue_match(db, account_id) is not None:
        raise conflict("already_in_match", "You are in an active match")
    party = Party(id=uuid.uuid4(), leader_id=account_id, created_at=now)
    db.add(party)
    db.flush()
    db.add(PartyMember(party_id=party.id, account_id=account_id, joined_at=now))
    try:
        db.flush()
    except IntegrityError as exc:
        raise conflict("already_in_party", "You are already in a party") from exc
    # Joining a party removes any solo queue entry.
    remove_queue_entry_for_account(db, account_id)
    return party_view(db, party, now)


def current_party(db: Session, account_id: uuid.UUID, now: datetime) -> dict[str, Any]:
    party_id = party_id_of(db, account_id)
    party = db.get(Party, party_id) if party_id else None
    if party is None:
        raise not_found("no_party", "You are not in a party")
    return party_view(db, party, now)


def invite(
    db: Session, account_id: uuid.UUID, username: str, now: datetime, ttl: timedelta
) -> dict[str, Any]:
    party = _current_party_locked(db, account_id)
    if party.leader_id != account_id:
        raise forbidden("not_leader", "Only the party leader can invite")
    target = db.scalar(select(Account).where(Account.username_lower == username.lower()))
    if target is None:
        raise not_found("no_such_user", "No such user")
    if party_id_of(db, target.id) is not None:
        raise conflict("already_in_party", "That player is already in a party")
    if _member_count(db, party.id) >= MAX_PARTY_SIZE:
        raise conflict("party_full", "The party is full (5 members)")
    pending = db.scalars(
        select(PartyInvite).where(
            PartyInvite.party_id == party.id,
            PartyInvite.status == "pending",
        )
    ).all()
    live_pending = 0
    for inv in pending:
        if inv.expires_at <= now:
            inv.status = "expired"
            continue
        live_pending += 1
        if inv.to_account_id == target.id:
            raise conflict("already_invited", "That player already has a pending invite")
    if live_pending >= MAX_PENDING_INVITES:
        raise conflict("too_many_invites", "Too many pending invites; wait for replies")
    db.flush()  # persist expirations before inserting (partial unique index)
    inv = PartyInvite(
        id=uuid.uuid4(),
        party_id=party.id,
        from_account_id=account_id,
        to_account_id=target.id,
        created_at=now,
        expires_at=now + ttl,
        status="pending",
    )
    db.add(inv)
    db.flush()
    leader = db.get(Account, account_id)
    return {
        "invite_id": str(inv.id),
        "party_id": str(party.id),
        "to_username": target.username,
        "from_username": leader.username if leader else "",
        "expires_at": iso_utc(inv.expires_at),
    }


def my_invites(db: Session, account_id: uuid.UUID, now: datetime) -> list[dict[str, Any]]:
    rows = db.execute(
        select(PartyInvite, Account.username)
        .join(Account, Account.id == PartyInvite.from_account_id)
        .where(
            PartyInvite.to_account_id == account_id,
            PartyInvite.status == "pending",
            PartyInvite.expires_at > now,
        )
        .order_by(PartyInvite.created_at)
    ).all()
    return [
        {
            "invite_id": str(inv.id),
            "party_id": str(inv.party_id),
            "from_username": from_username,
            "expires_at": iso_utc(inv.expires_at),
        }
        for inv, from_username in rows
    ]


def _my_pending_invite(db: Session, account_id: uuid.UUID, invite_id: uuid.UUID) -> PartyInvite:
    inv = db.scalar(select(PartyInvite).where(PartyInvite.id == invite_id).with_for_update())
    if inv is None or inv.to_account_id != account_id or inv.status not in ("pending", "expired"):
        raise not_found("invite_not_found", "Invite not found")
    return inv


def accept_invite(
    db: Session, account_id: uuid.UUID, invite_id: uuid.UUID, now: datetime
) -> dict[str, Any]:
    inv = _my_pending_invite(db, account_id, invite_id)
    if inv.status == "expired" or inv.expires_at <= now:
        inv.status = "expired"
        db.flush()
        raise conflict("expired", "The invite has expired")
    party = _lock_party(db, inv.party_id)
    if party is None:
        raise not_found("invite_not_found", "Invite not found")
    if party_id_of(db, account_id) is not None:
        raise conflict("already_in_party", "Leave your current party first")
    if active_queue_match(db, account_id) is not None:
        raise conflict("already_in_match", "You are in an active match")
    if _member_count(db, party.id) >= MAX_PARTY_SIZE:
        raise conflict("party_full", "The party is full (5 members)")
    db.add(PartyMember(party_id=party.id, account_id=account_id, joined_at=now))
    inv.status = "accepted"
    try:
        db.flush()
    except IntegrityError as exc:
        raise conflict("already_in_party", "Leave your current party first") from exc
    remove_queue_entries_for_party(db, party.id)
    remove_queue_entry_for_account(db, account_id)
    return party_view(db, party, now)


def decline_invite(db: Session, account_id: uuid.UUID, invite_id: uuid.UUID, now: datetime) -> None:
    inv = _my_pending_invite(db, account_id, invite_id)
    if inv.status == "pending":
        inv.status = "declined" if inv.expires_at > now else "expired"


def _remove_member(db: Session, party: Party, account_id: uuid.UUID) -> None:
    db.execute(
        delete(PartyMember).where(PartyMember.party_id == party.id, PartyMember.account_id == account_id)
    )
    remove_queue_entries_for_party(db, party.id)
    remaining = _members(db, party.id)
    if not remaining:
        db.delete(party)  # cascades invites
    elif party.leader_id == account_id:
        # Longest-standing member becomes leader.
        party.leader_id = remaining[0][0].account_id
    db.flush()


def leave(db: Session, account_id: uuid.UUID) -> None:
    party = _current_party_locked(db, account_id)
    _remove_member(db, party, account_id)


def kick(db: Session, account_id: uuid.UUID, target_id: uuid.UUID) -> None:
    party = _current_party_locked(db, account_id)
    if party.leader_id != account_id:
        raise forbidden("not_leader", "Only the party leader can kick")
    if target_id == account_id:
        raise conflict("cannot_kick_self", "Use leave to leave your own party")
    if party_id_of(db, target_id) != party.id:
        raise not_found("not_in_party", "That player is not in your party")
    _remove_member(db, party, target_id)


def promote(db: Session, account_id: uuid.UUID, target_id: uuid.UUID) -> None:
    party = _current_party_locked(db, account_id)
    if party.leader_id != account_id:
        raise forbidden("not_leader", "Only the party leader can promote")
    if party_id_of(db, target_id) != party.id:
        raise not_found("not_in_party", "That player is not in your party")
    party.leader_id = target_id
    # The queued entry (if any) keeps the party's settings; only the leader field moves.
    entry = db.scalar(select(QueueEntry).where(QueueEntry.party_id == party.id))
    if entry is not None:
        entry.leader_id = target_id
    db.flush()


def party_member_ids(db: Session, party_id: uuid.UUID) -> list[uuid.UUID]:
    return [m.account_id for m, _ in _members(db, party_id)]
