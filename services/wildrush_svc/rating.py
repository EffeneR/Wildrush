"""Glicko-2 ("lite" team variant) for ranked matches.

Reference: Mark E. Glickman, "Example of the Glicko-2 system" (2013). Each ranked match is
one rating period. In a 5v5 match every player is rated against a single *composite
opponent*: the opposing team's mean rating and root-mean-square deviation. All updates of a
match use the pre-match values (simultaneous update).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

SCALE = 173.7178
DEFAULT_RATING = 1500.0
DEFAULT_DEVIATION = 350.0
DEFAULT_VOLATILITY = 0.06
TAU = 0.5
MIN_DEVIATION = 30.0
MAX_DEVIATION = 350.0
_EPSILON = 1e-6


@dataclass(frozen=True)
class Glicko:
    rating: float = DEFAULT_RATING
    deviation: float = DEFAULT_DEVIATION
    volatility: float = DEFAULT_VOLATILITY


@dataclass(frozen=True)
class GameOutcome:
    opponent_rating: float
    opponent_deviation: float
    score: float  # 1 win, 0 loss, 0.5 draw


def _g(phi: float) -> float:
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _e(mu: float, mu_j: float, phi_j: float) -> float:
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def update(player: Glicko, games: Sequence[GameOutcome], tau: float = TAU) -> Glicko:
    """One Glicko-2 rating period for ``player``."""
    mu = (player.rating - DEFAULT_RATING) / SCALE
    phi = player.deviation / SCALE
    sigma = player.volatility

    if not games:
        phi_star = math.sqrt(phi * phi + sigma * sigma)
        return Glicko(player.rating, _clamp_rd(phi_star * SCALE), sigma)

    v_inv = 0.0
    delta_sum = 0.0
    for game in games:
        mu_j = (game.opponent_rating - DEFAULT_RATING) / SCALE
        phi_j = game.opponent_deviation / SCALE
        g = _g(phi_j)
        e = _e(mu, mu_j, phi_j)
        v_inv += g * g * e * (1.0 - e)
        delta_sum += g * (game.score - e)
    v = 1.0 / v_inv
    delta = v * delta_sum

    # Step 5: new volatility via the Illinois algorithm.
    a = math.log(sigma * sigma)
    phi2 = phi * phi

    def f(x: float) -> float:
        ex = math.exp(x)
        num = ex * (delta * delta - phi2 - v - ex)
        den = 2.0 * (phi2 + v + ex) ** 2
        return num / den - (x - a) / (tau * tau)

    big_a = a
    if delta * delta > phi2 + v:
        big_b = math.log(delta * delta - phi2 - v)
    else:
        k = 1
        while f(a - k * tau) < 0:
            k += 1
        big_b = a - k * tau
    f_a = f(big_a)
    f_b = f(big_b)
    for _ in range(200):
        if abs(big_b - big_a) <= _EPSILON:
            break
        big_c = big_a + (big_a - big_b) * f_a / (f_b - f_a)
        f_c = f(big_c)
        if f_c * f_b <= 0:
            big_a, f_a = big_b, f_b
        else:
            f_a /= 2.0
        big_b, f_b = big_c, f_c
    new_sigma = math.exp(big_a / 2.0)

    phi_star = math.sqrt(phi2 + new_sigma * new_sigma)
    new_phi = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    new_mu = mu + new_phi * new_phi * delta_sum
    return Glicko(
        rating=DEFAULT_RATING + SCALE * new_mu,
        deviation=_clamp_rd(SCALE * new_phi),
        volatility=new_sigma,
    )


def _clamp_rd(rd: float) -> float:
    return max(MIN_DEVIATION, min(MAX_DEVIATION, rd))


def composite_opponent(team: Sequence[Glicko]) -> tuple[float, float]:
    """Mean rating and root-mean-square deviation of a team."""
    if not team:
        raise ValueError("empty team")
    mean = sum(p.rating for p in team) / len(team)
    rms = math.sqrt(sum(p.deviation * p.deviation for p in team) / len(team))
    return mean, rms


def team_match_updates(
    team0: Sequence[Glicko],
    team1: Sequence[Glicko],
    winner_team: int,
    losers_forced: Sequence[tuple[int, int]] = (),
) -> tuple[list[Glicko], list[Glicko]]:
    """Update both teams for one match.

    ``losers_forced`` lists ``(team, index)`` pairs scored as a loss regardless of the
    outcome (abandoned players in ranked).
    """
    forced = set(losers_forced)
    opp_for = {0: composite_opponent(team1), 1: composite_opponent(team0)}
    out: tuple[list[Glicko], list[Glicko]] = ([], [])
    for t, team in ((0, team0), (1, team1)):
        opp_r, opp_rd = opp_for[t]
        for i, player in enumerate(team):
            score = 1.0 if (t == winner_team and (t, i) not in forced) else 0.0
            out[t].append(update(player, [GameOutcome(opp_r, opp_rd, score)]))
    return out
