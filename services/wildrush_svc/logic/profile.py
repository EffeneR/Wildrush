"""Profile, cosmetics and mastery views / updates."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import conflict, not_found
from ..mastery import (
    FIGHTERS,
    PALETTE_LEVELS,
    fighter_badges_for_level,
    level_for_xp,
    next_level_xp,
    unlocked_palettes,
)
from ..models import Account, AccountBadge, FighterMastery
from ..schemas import ProfilePatchReq


def account_badges(db: Session, account_id: uuid.UUID) -> list[str]:
    stored = set(
        db.scalars(select(AccountBadge.badge).where(AccountBadge.account_id == account_id)).all()
    )
    return sorted(stored)


def _mastery_rows(db: Session, account_id: uuid.UUID, *, lock: bool = False) -> dict[str, FighterMastery]:
    stmt = select(FighterMastery).where(FighterMastery.account_id == account_id)
    if lock:
        stmt = stmt.order_by(FighterMastery.fighter).with_for_update()
    rows = {row.fighter: row for row in db.scalars(stmt).all()}
    return rows


def profile_view(db: Session, account_id: uuid.UUID) -> dict[str, Any]:
    account = db.get(Account, account_id)
    if account is None:
        raise not_found("no_such_account", "Account not found")
    rows = _mastery_rows(db, account_id)
    fighters: dict[str, Any] = {}
    for fighter in FIGHTERS:
        row = rows.get(fighter)
        xp = row.xp if row else 0
        level = level_for_xp(xp)
        fighters[fighter] = {
            "xp": xp,
            "level": level,
            "next_level_xp": next_level_xp(xp),
            "palettes": unlocked_palettes(level),
            "selected_palette": row.selected_palette if row else "default",
        }
    return {
        "display_name": account.display_name,
        "selected_badge": account.selected_badge,
        "badges": account_badges(db, account_id),
        "fighters": fighters,
    }


def palettes_by_fighter(db: Session, account_id: uuid.UUID) -> dict[str, str]:
    rows = _mastery_rows(db, account_id)
    return {f: (rows[f].selected_palette if f in rows else "default") for f in FIGHTERS}


def patch_profile(db: Session, account_id: uuid.UUID, body: ProfilePatchReq) -> dict[str, Any]:
    account = db.scalar(select(Account).where(Account.id == account_id).with_for_update())
    if account is None:
        raise not_found("no_such_account", "Account not found")
    fields = body.model_fields_set
    if "display_name" in fields and body.display_name is not None:
        account.display_name = body.display_name
    if "selected_badge" in fields:
        if body.selected_badge is None:
            account.selected_badge = None
        else:
            if body.selected_badge not in account_badges(db, account_id):
                raise conflict("not_unlocked", f"Badge {body.selected_badge!r} is not unlocked")
            account.selected_badge = body.selected_badge
    if "selected_palettes" in fields and body.selected_palettes:
        rows = _mastery_rows(db, account_id, lock=True)
        for fighter, palette in body.selected_palettes.items():
            row = rows[fighter]
            if level_for_xp(row.xp) < PALETTE_LEVELS[palette]:
                raise conflict(
                    "not_unlocked",
                    f"Palette {palette!r} for {fighter} unlocks at mastery level {PALETTE_LEVELS[palette]}",
                )
            row.selected_palette = palette
    db.flush()
    return profile_view(db, account_id)


def all_fighter_badges(levels: dict[str, int]) -> set[str]:
    badges: set[str] = set()
    for fighter, level in levels.items():
        badges.update(fighter_badges_for_level(fighter, level))
    return badges
