"""Pure matchmaking algorithms (no I/O; unit-tested directly).

Rules (docs/API_CONTRACT.md "Queue & matchmaking"):

* Parties are never split and always play on one team (party size <= 5).
* Ranked: exactly 10 humans, never bots; two teams of 5 built by greedy rating balancing
  over party blocks.
* Casual: prefers 10 humans. A bot-filled match is formed only from parties that opted in
  (``allow_bots``) **and** have each waited >= 20 s; it has >= 1 human and bots fill the
  remaining slots of both teams. Parties that did not opt in simply keep waiting.
* Region: every party must accept the region; among common regions (with free server
  capacity) the one with the best (lowest) maximum latency is chosen. A party accepts a
  region if its latency there is <= 150 ms, or -- after it has waited 60 s -- if it
  reported the region at all ("relaxed to any common region after 60 s").
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

TEAM_SIZE = 5
MATCH_SIZE = 2 * TEAM_SIZE
MAX_ANCHORS_PER_PASS = 250  # bounds per-tick work on very large queues


@dataclass(frozen=True)
class MMMember:
    account_id: uuid.UUID
    rating: float


@dataclass(frozen=True)
class MMEntry:
    entry_id: uuid.UUID
    members: tuple[MMMember, ...]
    queued_at: datetime
    region: str
    latency_ms: Mapping[str, int] = field(default_factory=dict)
    allow_bots: bool = False

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def total_rating(self) -> float:
        return sum(m.rating for m in self.members)

    @property
    def mean_rating(self) -> float:
        return self.total_rating / self.size if self.members else 0.0

    def latency_to(self, region: str) -> float | None:
        """Reported latency; the party's own preferred region counts as 0 if unmeasured."""
        if region in self.latency_ms:
            return float(self.latency_ms[region])
        if region == self.region:
            return 0.0
        return None

    def regions(self) -> set[str]:
        return set(self.latency_ms) | {self.region}

    def waited_s(self, now: datetime) -> float:
        return (now - self.queued_at).total_seconds()


@dataclass(frozen=True)
class MMParams:
    max_latency_ms: float = 150.0
    region_relax_s: float = 60.0
    casual_bot_wait_s: float = 20.0


@dataclass(frozen=True)
class FormedMatch:
    mode: str
    region: str
    teams: tuple[tuple[MMEntry, ...], tuple[MMEntry, ...]]
    bots: tuple[int, int]
    max_latency_ms: float

    @property
    def entries(self) -> tuple[MMEntry, ...]:
        return self.teams[0] + self.teams[1]

    @property
    def humans(self) -> int:
        return sum(e.size for e in self.entries)

    def team_sizes(self) -> tuple[int, int]:
        return (sum(e.size for e in self.teams[0]), sum(e.size for e in self.teams[1]))


def accepts_region(entry: MMEntry, region: str, now: datetime, params: MMParams) -> bool:
    latency = entry.latency_to(region)
    if latency is None:
        return False
    return latency <= params.max_latency_ms or entry.waited_s(now) >= params.region_relax_s


def can_pack(sizes: Sequence[int], cap_a: int = TEAM_SIZE, cap_b: int = TEAM_SIZE) -> bool:
    """Can blocks of ``sizes`` be split into two teams with capacities cap_a / cap_b?"""
    total = sum(sizes)
    if total > cap_a + cap_b:
        return False
    reachable = {0}
    for s in sizes:
        reachable |= {r + s for r in reachable if r + s <= cap_a}
    return any(total - r <= cap_b for r in reachable)


def select_group(
    pool: Sequence[MMEntry], anchor: MMEntry, *, target: int, exact: bool
) -> list[MMEntry] | None:
    """Greedy by queue age: add parties while the total fits and stays packable."""
    if anchor.size > TEAM_SIZE:
        return None
    chosen = [anchor]
    total = anchor.size
    for entry in pool:
        if total == target:
            break
        if entry.entry_id == anchor.entry_id or total + entry.size > target:
            continue
        if not can_pack([c.size for c in chosen] + [entry.size]):
            continue
        chosen.append(entry)
        total += entry.size
    if exact and total != target:
        return None
    return chosen


def assign_teams(
    entries: Sequence[MMEntry], *, balance_humans: bool
) -> tuple[tuple[MMEntry, ...], tuple[MMEntry, ...]] | None:
    """Greedy balancing over party blocks.

    Blocks are placed largest first (then highest mean rating) onto the team with the lower
    rating total (``balance_humans``: the team with fewer humans first, used for bot-filled
    casual matches), considering only placements that keep the remaining blocks packable.
    """
    order = sorted(
        entries, key=lambda e: (-e.size, -e.mean_rating, e.queued_at, str(e.entry_id))
    )
    teams: tuple[list[MMEntry], list[MMEntry]] = ([], [])
    sizes = [0, 0]
    totals = [0.0, 0.0]
    for i, entry in enumerate(order):
        rest = [e.size for e in order[i + 1:]]
        options = []
        for t in (0, 1):
            if sizes[t] + entry.size > TEAM_SIZE:
                continue
            new_sizes = list(sizes)
            new_sizes[t] += entry.size
            if can_pack(rest, TEAM_SIZE - new_sizes[0], TEAM_SIZE - new_sizes[1]):
                options.append(t)
        if not options:
            return None
        if balance_humans:
            t = min(options, key=lambda t: (sizes[t], totals[t], t))
        else:
            t = min(options, key=lambda t: (totals[t], sizes[t], t))
        teams[t].append(entry)
        sizes[t] += entry.size
        totals[t] += entry.total_rating
    return tuple(teams[0]), tuple(teams[1])


def best_region(
    group: Sequence[MMEntry], capacity: Mapping[str, int], now: datetime, params: MMParams
) -> tuple[str, float] | None:
    """Common region with free capacity minimizing the group's maximum latency."""
    common: set[str] | None = None
    for entry in group:
        common = entry.regions() if common is None else common & entry.regions()
    best: tuple[float, str] | None = None
    for region in sorted(common or ()):
        if capacity.get(region, 0) <= 0:
            continue
        if not all(accepts_region(e, region, now, params) for e in group):
            continue
        worst = max(e.latency_to(region) or 0.0 for e in group)
        if best is None or (worst, region) < best:
            best = (worst, region)
    return (best[1], best[0]) if best else None


def _find_group(
    pool: Sequence[MMEntry],
    capacity: Mapping[str, int],
    now: datetime,
    params: MMParams,
    *,
    mode: str,
    exact: bool,
) -> FormedMatch | None:
    for anchor in pool[:MAX_ANCHORS_PER_PASS]:
        best: tuple[tuple[float, str], list[MMEntry]] | None = None
        for region in sorted(anchor.regions()):
            if capacity.get(region, 0) <= 0 or not accepts_region(anchor, region, now, params):
                continue
            candidates = [e for e in pool if accepts_region(e, region, now, params)]
            if exact and sum(e.size for e in candidates) < MATCH_SIZE:
                continue
            group = select_group(candidates, anchor, target=MATCH_SIZE, exact=exact)
            if not group:
                continue
            choice = best_region(group, capacity, now, params)
            if choice is None:
                continue
            key = (choice[1], choice[0])
            if best is None or key < best[0]:
                best = (key, group)
        if best is None:
            continue
        (max_latency, region), group = best
        teams = assign_teams(group, balance_humans=not exact)
        if teams is None:  # cannot happen for packable groups; defensive
            continue
        h0 = sum(e.size for e in teams[0])
        h1 = sum(e.size for e in teams[1])
        bots = (0, 0) if exact else (TEAM_SIZE - h0, TEAM_SIZE - h1)
        return FormedMatch(mode, region, teams, bots, max_latency)
    return None


def form_matches(
    mode: str,
    entries: Iterable[MMEntry],
    capacity: Mapping[str, int],
    now: datetime,
    params: MMParams = MMParams(),
) -> list[FormedMatch]:
    """Form as many matches as possible for one queue mode.

    ``capacity`` maps region -> number of matches that can still be allocated there.
    """
    if mode not in ("casual", "ranked"):
        raise ValueError(f"unsupported queue mode {mode!r}")
    cap = dict(capacity)
    remaining = sorted(entries, key=lambda e: (e.queued_at, str(e.entry_id)))
    formed: list[FormedMatch] = []

    def take(match: FormedMatch) -> None:
        nonlocal remaining
        formed.append(match)
        cap[match.region] = cap.get(match.region, 0) - 1
        used = {e.entry_id for e in match.entries}
        remaining = [e for e in remaining if e.entry_id not in used]

    # Phase 1: full ten-human matches (both modes).
    while True:
        match = _find_group(remaining, cap, now, params, mode=mode, exact=True)
        if match is None:
            break
        take(match)

    # Phase 2 (casual only): bot fill for opted-in parties that waited long enough.
    if mode == "casual":
        while True:
            eligible = [
                e for e in remaining
                if e.allow_bots and e.waited_s(now) >= params.casual_bot_wait_s
            ]
            if not eligible:
                break
            match = _find_group(eligible, cap, now, params, mode=mode, exact=False)
            if match is None:
                break
            take(match)
    return formed
