"""Match history and stored results."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import iso_utc
from ..errors import not_found
from ..models import Match, MatchParticipant, MatchPlayerResult, MatchResult


def history(
    db: Session, account_id: uuid.UUID, *, limit: int, before: datetime | None
) -> list[dict[str, Any]]:
    stmt = (
        select(MatchPlayerResult, MatchResult.body)
        .join(MatchResult, MatchResult.match_id == MatchPlayerResult.match_id)
        .where(MatchPlayerResult.account_id == account_id)
    )
    if before is not None:
        stmt = stmt.where(MatchPlayerResult.ended_at < before)
    stmt = stmt.order_by(MatchPlayerResult.ended_at.desc(), MatchPlayerResult.match_id).limit(limit)
    out = []
    for row, body in db.execute(stmt).all():
        delta = None
        if row.rating_before is not None and row.rating_after is not None:
            delta = round(row.rating_after - row.rating_before, 2)
        out.append(
            {
                "match_id": str(row.match_id),
                "mode": row.mode,
                "ended_at": iso_utc(row.ended_at),
                "team": row.team,
                "fighter": row.fighter,
                "won": row.won,
                "score": body.get("score"),
                "rating_delta": delta,
                "xp_gained": row.xp_gained,
            }
        )
    return out


def match_detail(db: Session, account_id: uuid.UUID, match_id: uuid.UUID) -> dict[str, Any]:
    match = db.get(Match, match_id)
    if match is None:
        raise not_found("match_not_found", "Match not found")
    participant = db.get(MatchParticipant, (match_id, account_id))
    played = db.get(MatchPlayerResult, (match_id, account_id))
    if participant is None and played is None:
        raise not_found("match_not_found", "Match not found")  # do not reveal other matches
    result = db.get(MatchResult, match_id)
    return {
        "match_id": str(match.id),
        "mode": match.mode,
        "state": match.state,
        "region": match.region,
        "created_at": iso_utc(match.created_at),
        "started_at": iso_utc(match.started_at),
        "ended_at": iso_utc(match.ended_at),
        "result": result.body if result else None,
        "rating_changes": result.response.get("rating_changes", {}) if result else {},
        "mastery_changes": result.response.get("mastery_changes", {}) if result else {},
    }
