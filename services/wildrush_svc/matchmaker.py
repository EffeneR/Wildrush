"""Matchmaker: DB tick (every ``WR_MATCHMAKER_INTERVAL_S``, default 1 s) + background loop.

Each tick runs in one transaction guarded by a transaction-level advisory lock, so several
service processes would never run ticks concurrently. Queue rows are read with
``FOR UPDATE SKIP LOCKED``. The grouping logic itself is the pure ``matchmaking`` module.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict

import anyio
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .context import AppContext
from .logic import janitor
from .logic.common import available_hosts
from .logic.private import ALLOCATION_LOCK_KEY
from .matchmaking import FormedMatch, MMEntry, MMMember, MMParams, form_matches
from .models import Allocation, Match, MatchParticipant, QueueEntry, QueueMember, Rating

log = logging.getLogger("wildrush_svc.matchmaker")


class Matchmaker:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self.ticks = 0

    @property
    def params(self) -> MMParams:
        s = self.ctx.settings
        return MMParams(
            max_latency_ms=float(s.mm_max_latency_ms),
            region_relax_s=float(s.mm_region_relax_s),
            casual_bot_wait_s=float(s.mm_casual_bot_wait_s),
        )

    def tick(self) -> list[uuid.UUID]:
        """Run janitor + matchmaking once. Returns the ids of the matches formed."""
        formed_ids: list[uuid.UUID] = []
        with self.ctx.tx() as db:
            if not db.scalar(select(func.pg_try_advisory_xact_lock(ALLOCATION_LOCK_KEY))):
                return formed_ids
            janitor.run(db, self.ctx)
            now = self.ctx.clock.now()
            hosts = available_hosts(db, now=now, stale_s=self.ctx.settings.server_stale_s)
            free: dict[str, int] = {server.id: n for server, n in hosts}
            region_of: dict[str, str] = {server.id: server.region for server, _ in hosts}
            for mode in ("ranked", "casual"):
                formed_ids.extend(self._tick_mode(db, mode, free, region_of))
        self.ticks += 1
        return formed_ids

    def _tick_mode(
        self, db: Session, mode: str, free: dict[str, int], region_of: dict[str, str]
    ) -> list[uuid.UUID]:
        now = self.ctx.clock.now()
        rows = db.scalars(
            select(QueueEntry)
            .where(QueueEntry.mode == mode)
            .order_by(QueueEntry.queued_at, QueueEntry.id)
            .with_for_update(skip_locked=True)
        ).all()
        if not rows:
            return []
        by_id = {row.id: row for row in rows}
        member_rows = db.execute(
            select(QueueMember.entry_id, QueueMember.account_id, Rating.rating)
            .join(Rating, Rating.account_id == QueueMember.account_id)
            .where(QueueMember.entry_id.in_(list(by_id)))
            .order_by(QueueMember.entry_id, QueueMember.account_id)
        ).all()
        members: dict[uuid.UUID, list[MMMember]] = defaultdict(list)
        for entry_id, account_id, rating in member_rows:
            members[entry_id].append(MMMember(account_id=account_id, rating=float(rating)))
        entries = [
            MMEntry(
                entry_id=row.id,
                members=tuple(members[row.id]),
                queued_at=row.queued_at,
                region=row.region,
                latency_ms={str(k): int(v) for k, v in (row.latency_ms or {}).items()},
                allow_bots=row.allow_bots,
            )
            for row in rows
            if members.get(row.id)
        ]
        capacity: dict[str, int] = defaultdict(int)
        for server_id, n in free.items():
            capacity[region_of[server_id]] += n
        formed = form_matches(mode, entries, capacity, now, self.params)
        ids = []
        for fm in formed:
            server_id = self._pick_server(fm.region, free, region_of)
            if server_id is None:  # pragma: no cover - capacity was checked
                continue
            ids.append(self._create_match(db, fm, server_id, by_id))
        return ids

    @staticmethod
    def _pick_server(region: str, free: dict[str, int], region_of: dict[str, str]) -> str | None:
        candidates = [sid for sid, n in free.items() if n > 0 and region_of[sid] == region]
        if not candidates:
            return None
        server_id = max(candidates, key=lambda sid: (free[sid], sid))
        free[server_id] -= 1
        return server_id

    def _create_match(
        self, db: Session, fm: FormedMatch, server_id: str, rows: dict[uuid.UUID, QueueEntry]
    ) -> uuid.UUID:
        now = self.ctx.clock.now()
        match = Match(
            id=uuid.uuid4(),
            mode=fm.mode,
            state="allocating",
            region=fm.region,
            server_id=server_id,
            host=None,
            port=None,
            join_code=None,
            created_by=None,
            expected_players=fm.humans,
            bot_slots=sum(fm.bots),
            created_at=now,
        )
        db.add(match)
        db.flush()
        for team_index, team in enumerate(fm.teams):
            for entry in team:
                row = rows[entry.entry_id]
                for member in entry.members:
                    db.add(
                        MatchParticipant(
                            match_id=match.id,
                            account_id=member.account_id,
                            team=team_index,
                            role="player",
                            lobby_admin=False,
                            party_id=row.party_id,
                            # Only the leader supplies roster prefs in the queue request.
                            roster_prefs=list(row.roster_prefs) if member.account_id == row.leader_id else [],
                            joined_at=now,
                        )
                    )
        db.add(
            Allocation(
                id=uuid.uuid4(), match_id=match.id, server_id=server_id, state="pending", created_at=now
            )
        )
        db.execute(delete(QueueEntry).where(QueueEntry.id.in_([e.entry_id for e in fm.entries])))
        db.flush()
        h0, h1 = fm.team_sizes()
        log.info(
            "formed %s match %s in %s on %s: humans %d/%d bots %d/%d",
            fm.mode, match.id, fm.region, server_id, h0, h1, fm.bots[0], fm.bots[1],
        )
        return match.id

    async def run_forever(self) -> None:
        interval = self.ctx.settings.matchmaker_interval_s
        while True:
            try:
                await anyio.to_thread.run_sync(self.tick)
            except asyncio.CancelledError:
                raise
            except Exception:  # keep the loop alive; the next tick retries
                log.exception("matchmaker tick failed")
            await asyncio.sleep(interval)
