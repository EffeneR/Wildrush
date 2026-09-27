"""Authoritative match results: idempotent, all-or-nothing (rating + mastery + history).

Idempotency: the match row is locked (``SELECT ... FOR UPDATE``); the first valid result
moves the match to ``finished`` and inserts ``match_results`` (primary key = match id, so a
second row is impossible). A retransmission of the same (canonical) body returns the stored
response with ``applied: false, idempotent: true``; a different body returns 409.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .. import rating as glicko
from ..context import AppContext
from ..errors import conflict, forbidden, not_found, unprocessable
from ..mastery import BADGE_TIERS, level_for_xp, match_xp
from ..models import (
    AccountBadge,
    FighterMastery,
    MatchParticipant,
    MatchPlayerResult,
    MatchResult,
    Rating,
)
from ..schemas import ResultReq
from .allocation import lock_match

log = logging.getLogger("wildrush_svc.results")


def canonical_digest(body: ResultReq) -> tuple[dict[str, Any], str]:
    canonical = body.canonical()
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return canonical, hashlib.sha256(encoded.encode("ascii")).hexdigest()


def _validate(body: ResultReq, mode: str, participants: list[MatchParticipant]) -> None:
    if mode == "ranked" and body.bots:
        raise unprocessable("bots_in_ranked", "Ranked results must not contain bots")
    ids = [p.account_id for p in body.players]
    if len(set(ids)) != len(ids):
        raise unprocessable("invalid_result", "Duplicate account_id in players")
    humans = defaultdict(int)
    bots = defaultdict(int)
    fighters: dict[int, list[str]] = defaultdict(list)
    for p in body.players:
        humans[p.team] += 1
        fighters[p.team].append(p.fighter)
    for b in body.bots:
        bots[b.team] += 1
        fighters[b.team].append(b.fighter)
    for team in (0, 1):
        if humans[team] + bots[team] > 5:
            raise unprocessable("invalid_result", f"Team {team} has more than 5 fighters")
        if len(set(fighters[team])) != len(fighters[team]):
            raise unprocessable("invalid_result", f"Team {team} uses a species twice")
    players_by_id = {p.account_id: p for p in participants if p.role == "player"}
    for p in body.players:
        part = players_by_id.get(p.account_id)
        if part is None:
            raise unprocessable("invalid_result", f"{p.account_id} is not a player of this match")
        if mode in ("casual", "ranked") and part.team != p.team:
            raise unprocessable("invalid_result", f"{p.account_id} was assigned to team {part.team}")
    if mode == "ranked":
        if set(ids) != set(players_by_id) or len(ids) != 10:
            raise unprocessable("invalid_result", "Ranked results must list all 10 matched players")
        if humans[0] != 5 or humans[1] != 5:
            raise unprocessable("invalid_result", "Ranked results need 5 players per team")


def submit(
    db: Session, ctx: AppContext, server_id: str, match_id: uuid.UUID, body: ResultReq
) -> dict[str, Any]:
    now = ctx.clock.now()
    if body.match_id != match_id:
        raise unprocessable("match_id_mismatch", "Body match_id differs from the URL")
    match = lock_match(db, match_id)
    if match is None:
        raise not_found("match_not_found", "Match not found")
    if match.server_id != server_id:
        raise forbidden("wrong_server", "Only the server the match was allocated to may submit")
    canonical, digest = canonical_digest(body)
    if match.state == "finished":
        stored = db.get(MatchResult, match_id)
        if stored is not None and stored.body_sha256 == digest:
            return {**stored.response, "applied": False, "idempotent": True}
        raise conflict("result_conflict", "A different result was already recorded for this match")
    if match.state != "running":
        raise conflict("match_not_running", f"Match is {match.state}; results need a running match")

    participants = list(
        db.scalars(select(MatchParticipant).where(MatchParticipant.match_id == match_id)).all()
    )
    _validate(body, match.mode, participants)

    account_ids = sorted({p.account_id for p in body.players})
    rating_changes: dict[str, dict[str, float]] = {}
    new_ratings: dict[uuid.UUID, tuple[float, float]] = {}

    if match.mode == "ranked":
        # Lock rating rows in a stable order (no deadlocks between concurrent results).
        rows = {
            r.account_id: r
            for r in db.scalars(
                select(Rating).where(Rating.account_id.in_(account_ids)).order_by(Rating.account_id).with_for_update()
            ).all()
        }
        teams: dict[int, list] = {0: [], 1: []}
        for p in body.players:
            teams[p.team].append(p)
        pre = {
            t: [glicko.Glicko(rows[p.account_id].rating, rows[p.account_id].deviation, rows[p.account_id].volatility) for p in teams[t]]
            for t in (0, 1)
        }
        forced = [(t, i) for t in (0, 1) for i, p in enumerate(teams[t]) if p.abandoned]
        post = glicko.team_match_updates(pre[0], pre[1], body.winner_team, forced)
        for t in (0, 1):
            for i, p in enumerate(teams[t]):
                row = rows[p.account_id]
                before = row.rating
                new = post[t][i]
                row.rating = new.rating
                row.deviation = new.deviation
                row.volatility = new.volatility
                row.games += 1
                if t == body.winner_team and not p.abandoned:
                    row.wins += 1
                else:
                    row.losses += 1
                row.updated_at = now
                new_ratings[p.account_id] = (before, new.rating)
                rating_changes[str(p.account_id)] = {"before": round(before, 2), "after": round(new.rating, 2)}

    # Mastery XP (all modes; private x0.5), badge unlocks and history rows.
    mastery_rows = {
        (m.account_id, m.fighter): m
        for m in db.scalars(
            select(FighterMastery)
            .where(FighterMastery.account_id.in_(account_ids))
            .order_by(FighterMastery.account_id, FighterMastery.fighter)
            .with_for_update()
        ).all()
    }
    mastery_changes: dict[str, dict[str, Any]] = {}
    badge_rows: list[dict[str, Any]] = []
    for p in body.players:
        won = p.team == body.winner_team and not p.abandoned
        gained = match_xp(
            won=won,
            control_seconds=p.control_seconds,
            kos=p.kos,
            private=match.mode == "private",
            abandoned=p.abandoned,
            afk=p.afk,
        )
        row = mastery_rows[(p.account_id, p.fighter)]
        old_level = level_for_xp(row.xp)
        row.xp += gained
        new_level = level_for_xp(row.xp)
        unlocks = [
            f"{p.fighter}_{tier}" for tier, lvl in BADGE_TIERS.items() if old_level < lvl <= new_level
        ]
        # Insert every badge the level entitles to (ON CONFLICT DO NOTHING keeps the
        # original unlock time); ``unlocks`` reports the ones reached in this match.
        owed = [f"{p.fighter}_{tier}" for tier, lvl in BADGE_TIERS.items() if lvl <= new_level]
        for badge in owed + ["pack_debut"]:
            badge_rows.append(
                {"account_id": p.account_id, "badge": badge, "unlocked_at": now, "match_id": match_id}
            )
        mastery_changes[str(p.account_id)] = {
            "fighter": p.fighter,
            "xp_gained": gained,
            "xp": row.xp,
            "level": new_level,
            "badges_unlocked": unlocks,
        }
        before_after = new_ratings.get(p.account_id)
        db.add(
            MatchPlayerResult(
                match_id=match_id,
                account_id=p.account_id,
                mode=match.mode,
                team=p.team,
                fighter=p.fighter,
                won=won,
                kos=p.kos,
                knocked_out=p.knocked_out,
                damage_dealt=p.damage_dealt,
                control_seconds=p.control_seconds,
                abandoned=p.abandoned,
                afk=p.afk,
                xp_gained=gained,
                rating_before=before_after[0] if before_after else None,
                rating_after=before_after[1] if before_after else None,
                ended_at=now,
            )
        )
    if badge_rows:
        db.execute(
            pg_insert(AccountBadge).values(badge_rows).on_conflict_do_nothing(
                index_elements=[AccountBadge.account_id, AccountBadge.badge]
            )
        )
    response = {"applied": True, "rating_changes": rating_changes, "mastery_changes": mastery_changes}
    db.add(
        MatchResult(
            match_id=match_id,
            server_id=server_id,
            body=canonical,
            body_sha256=digest,
            response={"rating_changes": rating_changes, "mastery_changes": mastery_changes},
            submitted_at=now,
        )
    )
    match.state = "finished"
    match.ended_at = now
    db.flush()
    log.info("result applied for match %s (%s, %d players)", match_id, match.mode, len(body.players))
    return response
