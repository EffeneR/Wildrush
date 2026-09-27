"""Mastery XP, levels and cosmetic unlocks (contract: "Profile, cosmetics, mastery")."""

from __future__ import annotations

import math
from typing import Literal

FIGHTERS: tuple[str, ...] = ("nyx", "bruno", "vex", "hops", "scrap")
Fighter = Literal["nyx", "bruno", "vex", "hops", "scrap"]

# palette -> mastery level that unlocks it
PALETTE_LEVELS: dict[str, int] = {"default": 1, "dusk": 3, "ember": 5, "frost": 7}
PALETTES: tuple[str, ...] = tuple(PALETTE_LEVELS)
Palette = Literal["default", "dusk", "ember", "frost"]

# per-fighter badge suffix -> mastery level
BADGE_TIERS: dict[str, int] = {"initiate": 2, "adept": 4, "veteran": 6, "master": 8}
GLOBAL_BADGES: tuple[str, ...] = ("pack_debut",)
ALL_BADGES: tuple[str, ...] = tuple(
    f"{f}_{tier}" for f in FIGHTERS for tier in BADGE_TIERS
) + GLOBAL_BADGES

LEVEL_THRESHOLDS: tuple[int, ...] = (0, 300, 800, 1500, 2400, 3500, 4800, 6300, 8000, 10000)
MAX_LEVEL = len(LEVEL_THRESHOLDS)

XP_BASE = 100
XP_WIN = 50
XP_PER_CONTROL_POINT = 2
XP_CONTROL_CAP = 200
XP_PER_KO = 10
XP_KO_CAP = 100
PRIVATE_MULTIPLIER = 0.5


def level_for_xp(xp: int) -> int:
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if xp >= threshold:
            level = i + 1
    return level


def next_level_xp(xp: int) -> int | None:
    level = level_for_xp(xp)
    return LEVEL_THRESHOLDS[level] if level < MAX_LEVEL else None


def unlocked_palettes(level: int) -> list[str]:
    return [p for p, lvl in PALETTE_LEVELS.items() if level >= lvl]


def fighter_badges_for_level(fighter: str, level: int) -> list[str]:
    return [f"{fighter}_{tier}" for tier, lvl in BADGE_TIERS.items() if level >= lvl]


def match_xp(
    *, won: bool, control_seconds: float, kos: int, private: bool, abandoned: bool, afk: bool
) -> int:
    """XP for one player in one server-submitted match.

    100 base + 50 win + 2 x points-while-controlling (cap 200) + 10 x KOs (cap 100);
    a point is one full second of sole control (D-006). Private matches x0.5 (floored).
    Abandoned or AFK-flagged players earn nothing (CONTRACT_NOTES.md).
    """
    if abandoned or afk:
        return 0
    control_points = max(0, math.floor(control_seconds))
    xp = XP_BASE
    xp += XP_WIN if won else 0
    xp += min(XP_PER_CONTROL_POINT * control_points, XP_CONTROL_CAP)
    xp += min(XP_PER_KO * max(0, kos), XP_KO_CAP)
    if private:
        xp = math.floor(xp * PRIVATE_MULTIPLIER)
    return int(xp)
