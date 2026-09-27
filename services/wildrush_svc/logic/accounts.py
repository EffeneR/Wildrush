"""Accounts, sessions and the ``/v1/me`` view."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import rating as glicko
from ..clock import iso_utc
from ..errors import APIError, conflict, not_found
from ..mastery import FIGHTERS
from ..models import Account, AuthSession, FighterMastery, Rating
from ..security import (
    burn_password_check,
    hash_password,
    hash_token,
    new_session_token,
    verify_password,
)


def create_account(
    db: Session,
    *,
    username: str,
    password_hash: str,
    display_name: str | None,
    now: datetime,
) -> Account:
    """Insert an account with its rating and per-fighter mastery rows."""
    lower = username.lower()
    if db.scalar(select(Account.id).where(Account.username_lower == lower)) is not None:
        raise conflict("username_taken", "That username is already taken")
    account = Account(
        id=uuid.uuid4(),
        username=username,
        username_lower=lower,
        display_name=display_name or username,
        password_hash=password_hash,
        created_at=now,
        selected_badge=None,
    )
    db.add(account)
    try:
        db.flush()
    except IntegrityError as exc:  # concurrent registration of the same name
        raise conflict("username_taken", "That username is already taken") from exc
    db.add(
        Rating(
            account_id=account.id,
            rating=glicko.DEFAULT_RATING,
            deviation=glicko.DEFAULT_DEVIATION,
            volatility=glicko.DEFAULT_VOLATILITY,
            games=0,
            wins=0,
            losses=0,
            updated_at=now,
        )
    )
    for fighter in FIGHTERS:
        db.add(FighterMastery(account_id=account.id, fighter=fighter, xp=0, selected_palette="default"))
    db.flush()
    return account


def register(
    db: Session, *, username: str, password: str, display_name: str | None, now: datetime
) -> Account:
    return create_account(
        db,
        username=username,
        password_hash=hash_password(password),
        display_name=display_name,
        now=now,
    )


def create_session(
    db: Session, account_id: uuid.UUID, *, now: datetime, ttl: timedelta
) -> tuple[str, datetime]:
    token = new_session_token()
    expires_at = now + ttl
    db.add(
        AuthSession(
            id=uuid.uuid4(),
            account_id=account_id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=expires_at,
            revoked_at=None,
        )
    )
    db.flush()
    return token, expires_at


def login(
    db: Session, *, username: str, password: str, now: datetime, ttl: timedelta
) -> tuple[str, datetime, Account]:
    account = db.scalar(select(Account).where(Account.username_lower == username.lower()))
    if account is None:
        burn_password_check(password)
        raise APIError(401, "invalid_credentials", "Invalid username or password")
    ok, needs_rehash = verify_password(account.password_hash, password)
    if not ok:
        raise APIError(401, "invalid_credentials", "Invalid username or password")
    if needs_rehash:
        account.password_hash = hash_password(password)
    token, expires_at = create_session(db, account.id, now=now, ttl=ttl)
    return token, expires_at, account


def logout(db: Session, session_id: uuid.UUID, *, now: datetime) -> None:
    session = db.get(AuthSession, session_id)
    if session is not None and session.revoked_at is None:
        session.revoked_at = now


def me_view(db: Session, account_id: uuid.UUID) -> dict[str, Any]:
    account = db.get(Account, account_id)
    rating = db.get(Rating, account_id)
    if account is None or rating is None:
        raise not_found("no_such_account", "Account not found")
    return {
        "account_id": str(account.id),
        "username": account.username,
        "display_name": account.display_name,
        "created_at": iso_utc(account.created_at),
        "rating": rating_view(rating),
    }


def rating_view(rating: Rating) -> dict[str, Any]:
    return {
        "rating": round(rating.rating, 2),
        "deviation": round(rating.deviation, 2),
        "games": rating.games,
        "wins": rating.wins,
        "losses": rating.losses,
    }
