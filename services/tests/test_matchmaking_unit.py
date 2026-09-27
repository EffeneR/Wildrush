"""Pure matchmaking rules (no database)."""

from __future__ import annotations

import itertools
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from wildrush_svc.matchmaking import (
    MMEntry,
    MMMember,
    MMParams,
    assign_teams,
    can_pack,
    form_matches,
)

NOW = datetime(2026, 9, 27, 12, 0, 0, tzinfo=UTC)
_counter = itertools.count()


def entry(size: int = 1, *, waited: float = 0.0, ratings: list[float] | None = None, region: str = "eu",
          latency: dict[str, int] | None = None, bots: bool = False) -> MMEntry:
    n = next(_counter)
    ratings = ratings or [1500.0] * size
    assert len(ratings) == size
    return MMEntry(
        entry_id=uuid.UUID(int=n + 1),
        members=tuple(MMMember(uuid.UUID(int=10_000 + n * 10 + i), r) for i, r in enumerate(ratings)),
        queued_at=NOW - timedelta(seconds=waited) - timedelta(microseconds=n),
        region=region,
        latency_ms=latency if latency is not None else {region: 40},
        allow_bots=bots,
    )


CAP = {"eu": 5, "us": 5}


def humans(match) -> int:
    return match.humans


def test_can_pack():
    assert can_pack([5, 5]) and can_pack([3, 2, 3, 2]) and can_pack([1] * 10) and can_pack([4, 1, 4, 1])
    assert not can_pack([3, 3, 3]) and not can_pack([4, 4, 2]) and not can_pack([6]) and not can_pack([5, 5, 1])


def test_ranked_requires_exactly_ten_humans_and_never_bots():
    nine = [entry(waited=3600) for _ in range(9)]
    assert form_matches("ranked", nine, CAP, NOW) == []
    ten = nine + [entry(waited=5)]
    matches = form_matches("ranked", ten, CAP, NOW)
    assert len(matches) == 1
    m = matches[0]
    assert humans(m) == 10 and m.team_sizes() == (5, 5) and m.bots == (0, 0)
    # even when everyone opted into bots and waited forever, ranked never adds bots
    lonely = [entry(waited=10_000, bots=True) for _ in range(3)]
    assert form_matches("ranked", lonely, CAP, NOW) == []


def test_ranked_eleven_players_leaves_newest_waiting():
    players = [entry(waited=100 - i) for i in range(11)]
    matches = form_matches("ranked", players, CAP, NOW)
    assert len(matches) == 1
    used = {e.entry_id for e in matches[0].entries}
    assert players[-1].entry_id not in used  # the most recent joiner waits


def test_parties_never_split_and_share_a_team():
    parties = [entry(3), entry(2), entry(4), entry(1)]
    matches = form_matches("ranked", parties, CAP, NOW)
    assert len(matches) == 1
    m = matches[0]
    for team in m.teams:
        assert sum(e.size for e in team) == 5
    placed = {e.entry_id: t for t, team in enumerate(m.teams) for e in team}
    assert set(placed) == {p.entry_id for p in parties}
    assert placed[parties[0].entry_id] == placed[parties[1].entry_id]  # 3 + 2
    assert placed[parties[2].entry_id] == placed[parties[3].entry_id]  # 4 + 1


def test_unpackable_parties_do_not_match():
    # 3+3+3 = 9 cannot form two teams of <= 5; a full match needs an extra solo that packs.
    assert form_matches("ranked", [entry(3), entry(3), entry(3), entry(1)], CAP, NOW) == []
    matches = form_matches("ranked", [entry(3), entry(3), entry(2), entry(2)], CAP, NOW)
    assert len(matches) == 1 and matches[0].team_sizes() == (5, 5)


def test_greedy_rating_balance():
    ratings = [1000 + 100 * i for i in range(10)]
    players = [entry(ratings=[r]) for r in ratings]
    m = form_matches("ranked", players, CAP, NOW)[0]
    totals = [sum(e.total_rating for e in team) for team in m.teams]
    assert abs(totals[0] - totals[1]) <= 100
    # a much stronger premade is balanced by the strongest solos on the other side
    party = entry(5, ratings=[2000.0] * 5)
    solos = [entry(ratings=[r]) for r in (2100, 1950, 2050, 1900, 2000)]
    m = form_matches("ranked", [party, *solos], CAP, NOW)[0]
    assert {e.entry_id for e in m.teams[0]} == {party.entry_id} or {e.entry_id for e in m.teams[1]} == {party.entry_id}


def test_assign_teams_balances_mixed_blocks():
    blocks = [entry(3, ratings=[1500, 1500, 1500]), entry(2, ratings=[2000, 2000]), entry(2, ratings=[1000, 1000]),
              entry(ratings=[1800]), entry(ratings=[1200]), entry(ratings=[1500])]
    teams = assign_teams(blocks, balance_humans=False)
    assert teams is not None
    sizes = [sum(e.size for e in t) for t in teams]
    assert sizes == [5, 5]
    totals = [sum(e.total_rating for e in t) for t in teams]
    assert abs(totals[0] - totals[1]) <= 600


def test_casual_prefers_ten_humans_without_bots():
    players = [entry(waited=30, bots=True) for _ in range(10)]
    m = form_matches("casual", players, CAP, NOW)
    assert len(m) == 1 and m[0].humans == 10 and m[0].bots == (0, 0)


def test_casual_bot_fill_requires_opt_in_and_20s_wait():
    waited = [entry(waited=25, bots=True), entry(waited=21, bots=True)]
    m = form_matches("casual", waited, CAP, NOW)
    assert len(m) == 1
    assert m[0].humans == 2 and m[0].bots == (4, 4) and m[0].team_sizes() == (1, 1)

    too_early = [entry(waited=19, bots=True)]
    assert form_matches("casual", too_early, CAP, NOW) == []

    no_opt_in = [entry(waited=500, bots=False)]
    assert form_matches("casual", no_opt_in, CAP, NOW) == []


def test_casual_bot_group_only_contains_opted_in_parties():
    opted = entry(2, waited=30, bots=True)
    not_opted = entry(1, waited=300, bots=False)
    fresh_opted = entry(1, waited=5, bots=True)
    matches = form_matches("casual", [opted, not_opted, fresh_opted], CAP, NOW)
    assert len(matches) == 1
    ids = {e.entry_id for e in matches[0].entries}
    assert ids == {opted.entry_id}
    assert matches[0].bots in ((3, 5), (5, 3))
    team_of_party = [t for t, team in enumerate(matches[0].teams) if team]
    assert len(team_of_party) == 1  # the party of 2 plays together


def test_region_best_max_latency_and_relaxation():
    near = {"eu": 40, "us": 120}
    players = [entry(latency=near) for _ in range(9)] + [entry(latency={"eu": 60, "us": 30})]
    m = form_matches("ranked", players, CAP, NOW)[0]
    assert m.region == "eu" and m.max_latency_ms == 60

    far = [entry(latency={"eu": 200}, region="eu") for _ in range(10)]
    assert form_matches("ranked", far, CAP, NOW) == []  # > 150 ms, not waited 60 s
    relaxed = [entry(latency={"eu": 200}, region="eu", waited=61) for _ in range(10)]
    m = form_matches("ranked", relaxed, CAP, NOW)
    assert len(m) == 1 and m[0].region == "eu"

    # no common region -> no match even after relaxation
    split = [entry(latency={"eu": 20}, region="eu", waited=500) for _ in range(5)] + [
        entry(latency={"us": 20}, region="us", waited=500) for _ in range(5)
    ]
    assert form_matches("ranked", split, CAP, NOW) == []


def test_capacity_limits_matches_per_region():
    players = [entry() for _ in range(20)]
    assert len(form_matches("ranked", players, {"eu": 1}, NOW)) == 1
    assert len(form_matches("ranked", players, {"eu": 2}, NOW)) == 2
    assert form_matches("ranked", players, {"eu": 0}, NOW) == []
    assert form_matches("ranked", players, {"us": 3}, NOW) == []


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        form_matches("private", [], CAP, NOW)


@pytest.mark.parametrize("seed", range(25))
def test_randomized_invariants(seed):
    import random

    rng = random.Random(seed)
    entries = []
    for _ in range(rng.randint(1, 30)):
        size = rng.choice([1, 1, 1, 2, 2, 3, 4, 5])
        entries.append(entry(size, waited=rng.uniform(0, 90), ratings=[rng.uniform(900, 2200) for _ in range(size)],
                             bots=rng.random() < 0.5, latency={"eu": rng.randint(10, 250), "us": rng.randint(10, 250)}))
    for mode in ("ranked", "casual"):
        matches = form_matches(mode, entries, {"eu": 3, "us": 3}, NOW, MMParams())
        seen = set()
        for m in matches:
            for team in m.teams:
                assert sum(e.size for e in team) <= 5
            for e in m.entries:
                assert e.entry_id not in seen  # nobody matched twice
                seen.add(e.entry_id)
                assert e.latency_to(m.region) is not None
            if mode == "ranked" or m.bots == (0, 0):
                assert m.humans == 10 and m.team_sizes() == (5, 5)
            else:
                assert all(e.allow_bots and e.waited_s(NOW) >= 20 for e in m.entries)
                assert m.humans >= 1 and m.team_sizes()[0] + m.bots[0] == 5 and m.team_sizes()[1] + m.bots[1] == 5
