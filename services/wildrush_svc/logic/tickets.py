"""Join tickets: issuance (HMAC, 60 s, server- and match-bound) and single-use redemption."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..clock import iso_utc
from ..errors import APIError, conflict, not_found
from ..models import Account, GameServer, JoinTicket, Match, MatchParticipant
from ..security import encode_ticket, ticket_payload
from .profile import palettes_by_fighter

UTC = timezone.utc


def issue_ticket(
    db: Session,
    *,
    match: Match,
    participant: MatchParticipant,
    server: GameServer,
    now: datetime,
    ttl_s: int,
) -> JoinTicket:
    tid = uuid.uuid4()
    exp_unix = int(now.timestamp()) + ttl_s
    payload = ticket_payload(
        tid=str(tid),
        mid=str(match.id),
        aid=str(participant.account_id),
        sid=server.id,
        team=participant.team,
        role=participant.role,
        exp=exp_unix,
    )
    ticket = JoinTicket(
        id=tid,
        match_id=match.id,
        account_id=participant.account_id,
        server_id=server.id,
        team=participant.team,
        role=participant.role,
        token=encode_ticket(server.secret, payload),
        issued_at=now,
        expires_at=datetime.fromtimestamp(exp_unix, UTC),
        redeemed_at=None,
    )
    db.add(ticket)
    db.flush()
    return ticket


def latest_ticket(db: Session, match_id: uuid.UUID, account_id: uuid.UUID) -> JoinTicket | None:
    return db.scalar(
        select(JoinTicket)
        .where(JoinTicket.match_id == match_id, JoinTicket.account_id == account_id)
        .order_by(JoinTicket.issued_at.desc(), JoinTicket.id)
        .limit(1)
    )


def ticket_view(ticket: JoinTicket) -> dict[str, Any]:
    return {"ticket": ticket.token, "expires_at": iso_utc(ticket.expires_at)}


def redeem(
    db: Session, *, server_id: str, ticket_id: uuid.UUID, match_id: uuid.UUID, now: datetime
) -> dict[str, Any]:
    match = db.get(Match, match_id)
    if match is None or match.server_id != server_id:
        raise not_found("ticket_not_found", "Ticket not found for this server/match")
    if match.state not in ("ready", "running"):
        raise conflict("match_closed", f"Match is {match.state}")
    # Single atomic redemption (contract): only one concurrent caller can win.
    row = db.execute(
        update(JoinTicket)
        .where(
            JoinTicket.id == ticket_id,
            JoinTicket.match_id == match_id,
            JoinTicket.server_id == server_id,
            JoinTicket.redeemed_at.is_(None),
            JoinTicket.expires_at > now,
        )
        .values(redeemed_at=now)
        .returning(JoinTicket.account_id, JoinTicket.team, JoinTicket.role)
    ).first()
    if row is None:
        ticket = db.get(JoinTicket, ticket_id)
        if ticket is None or ticket.match_id != match_id or ticket.server_id != server_id:
            raise not_found("ticket_not_found", "Ticket not found for this server/match")
        if ticket.redeemed_at is not None:
            raise conflict("ticket_used", "Ticket already redeemed")
        raise APIError(410, "ticket_expired", "Ticket expired")
    account = db.get(Account, row.account_id)
    participant = db.get(MatchParticipant, (match_id, row.account_id))
    if account is None:
        raise not_found("ticket_not_found", "Ticket account no longer exists")
    return {
        "account_id": str(account.id),
        "username": account.username,
        "display_name": account.display_name,
        "team": row.team,
        "role": row.role,
        "roster_prefs": list(participant.roster_prefs) if participant else [],
        "palettes": palettes_by_fighter(db, account.id),
        "selected_badge": account.selected_badge,
        "lobby_admin": bool(participant.lobby_admin) if participant else False,
        "mode": match.mode,
    }
