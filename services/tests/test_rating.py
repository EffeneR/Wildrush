"""Glicko-2 sanity checks."""

from __future__ import annotations

import math

import pytest

from wildrush_svc import rating as g


def test_glickman_reference_example():
    # Glickman, "Example of the Glicko-2 system": 1500/200/0.06 vs three opponents, tau 0.5.
    player = g.Glicko(1500.0, 200.0, 0.06)
    games = [g.GameOutcome(1400, 30, 1.0), g.GameOutcome(1550, 100, 0.0), g.GameOutcome(1700, 300, 0.0)]
    out = g.update(player, games, tau=0.5)
    assert out.rating == pytest.approx(1464.06, abs=0.05)
    assert out.deviation == pytest.approx(151.52, abs=0.05)
    assert out.volatility == pytest.approx(0.05999, abs=1e-5)


def test_no_games_only_inflates_deviation():
    out = g.update(g.Glicko(1600, 100, 0.06), [])
    assert out.rating == 1600 and out.deviation > 100


def test_team_update_is_symmetric_and_bounded():
    team0 = [g.Glicko() for _ in range(5)]
    team1 = [g.Glicko() for _ in range(5)]
    post0, post1 = g.team_match_updates(team0, team1, winner_team=0)
    gains = [p.rating - 1500 for p in post0]
    losses = [1500 - p.rating for p in post1]
    assert all(x > 0 for x in gains) and all(x > 0 for x in losses)
    assert max(gains) - min(gains) < 1e-9
    assert sum(gains) == pytest.approx(sum(losses), rel=1e-9)  # equal teams: zero-sum
    assert all(p.deviation < 350 for p in post0 + post1)


def test_upset_moves_more_than_expected_win():
    strong = [g.Glicko(1900, 80, 0.06) for _ in range(5)]
    weak = [g.Glicko(1400, 80, 0.06) for _ in range(5)]
    expected_win, _ = g.team_match_updates(strong, weak, winner_team=0)
    upset_loss, upset_win = g.team_match_updates(strong, weak, winner_team=1)
    assert expected_win[0].rating - 1900 < 5
    assert upset_win[0].rating - 1400 > 20
    assert 1900 - upset_loss[0].rating > 20


def test_forced_loss_for_abandoner():
    team = [g.Glicko() for _ in range(5)]
    post0, _ = g.team_match_updates(team, [g.Glicko() for _ in range(5)], winner_team=0, losers_forced=[(0, 2)])
    assert post0[2].rating < 1500 < post0[0].rating


def test_deviation_clamped():
    p = g.Glicko(1500, 30, 0.06)
    for _ in range(200):
        p = g.update(p, [g.GameOutcome(1500, 30, 1.0)])
    assert p.deviation >= g.MIN_DEVIATION and math.isfinite(p.rating)
