"""SQLAlchemy 2.x ORM models.

The schema is created **only** by Alembic migrations (``services/alembic/versions``); the
application never calls ``create_all``. ``tests/test_migrations.py`` runs ``alembic check``
to prove these models and the migrations agree.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

FIGHTERS_SQL = "'nyx', 'bruno', 'vex', 'hops', 'scrap'"
PALETTES_SQL = "'default', 'dusk', 'ember', 'frost'"
MODES_SQL = "'casual', 'ranked', 'private'"
MATCH_STATES_SQL = "'allocating', 'ready', 'running', 'finished', 'cancelled'"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        datetime: DateTime(timezone=True),
        uuid.UUID: PGUUID(as_uuid=True),
        float: Double(),
        dict[str, Any]: JSONB(),
        list[Any]: JSONB(),
    }


# --- accounts ------------------------------------------------------------------------------

class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(16))
    username_lower: Mapped[str] = mapped_column(String(16), unique=True)
    display_name: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime]
    selected_badge: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (CheckConstraint("username_lower = lower(username)", name="username_lower"),)


class Rating(Base):
    """Glicko-2 rating (ranked only)."""

    __tablename__ = "ratings"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    rating: Mapped[float]
    deviation: Mapped[float]
    volatility: Mapped[float]
    games: Mapped[int] = mapped_column(Integer)
    wins: Mapped[int] = mapped_column(Integer)
    losses: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime]


class AuthSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]


class FighterMastery(Base):
    __tablename__ = "fighter_mastery"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    fighter: Mapped[str] = mapped_column(String(8), primary_key=True)
    xp: Mapped[int] = mapped_column(Integer)
    selected_palette: Mapped[str] = mapped_column(String(16))

    __table_args__ = (
        CheckConstraint(f"fighter IN ({FIGHTERS_SQL})", name="fighter"),
        CheckConstraint(f"selected_palette IN ({PALETTES_SQL})", name="palette"),
        CheckConstraint("xp >= 0", name="xp_nonneg"),
    )


class AccountBadge(Base):
    __tablename__ = "account_badges"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    badge: Mapped[str] = mapped_column(String(32), primary_key=True)
    unlocked_at: Mapped[datetime]
    match_id: Mapped[uuid.UUID | None]


# --- parties ------------------------------------------------------------------------------

class Party(Base):
    __tablename__ = "parties"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    leader_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"))
    created_at: Mapped[datetime]


class PartyMember(Base):
    __tablename__ = "party_members"

    party_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parties.id", ondelete="CASCADE"), primary_key=True
    )
    # unique: one party per account
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True, unique=True
    )
    joined_at: Mapped[datetime]


class PartyInvite(Base):
    __tablename__ = "party_invites"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    party_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parties.id", ondelete="CASCADE"))
    from_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    to_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(10))

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'expired', 'cancelled')", name="status"
        ),
        Index("ix_party_invites_to_account_status", "to_account_id", "status"),
        Index(
            "uq_party_invites_pending",
            "party_id",
            "to_account_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )


# --- game servers / allocator hosts -----------------------------------------------------

class GameServer(Base):
    """A provisioned allocator host (``X-WR-Server`` id). Its game-server processes share it."""

    __tablename__ = "servers"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(20))
    secret: Mapped[str] = mapped_column(String(128))  # HMAC key; never logged or returned
    enabled: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime]
    host: Mapped[str | None] = mapped_column(String(255))
    port_min: Mapped[int | None] = mapped_column(Integer)
    port_max: Mapped[int | None] = mapped_column(Integer)
    capacity: Mapped[int] = mapped_column(Integer)
    build_id: Mapped[str | None] = mapped_column(String(64))
    protocol: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10))
    last_heartbeat_at: Mapped[datetime | None]
    last_poll_at: Mapped[datetime | None]
    active_matches: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint("status IN ('offline', 'online', 'draining')", name="status"),
    )


# --- matches --------------------------------------------------------------------------------

class Match(Base):
    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    mode: Mapped[str] = mapped_column(String(8))
    state: Mapped[str] = mapped_column(String(12))
    region: Mapped[str] = mapped_column(String(20))
    server_id: Mapped[str | None] = mapped_column(ForeignKey("servers.id"))
    host: Mapped[str | None] = mapped_column(String(255))
    port: Mapped[int | None] = mapped_column(Integer)
    join_code: Mapped[str | None] = mapped_column(String(8), unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"))
    expected_players: Mapped[int] = mapped_column(Integer)
    bot_slots: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime]
    ready_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    ended_at: Mapped[datetime | None]
    cancel_reason: Mapped[str | None] = mapped_column(String(200))

    __table_args__ = (
        CheckConstraint(f"mode IN ({MODES_SQL})", name="mode"),
        CheckConstraint(f"state IN ({MATCH_STATES_SQL})", name="state"),
        Index("ix_matches_state", "state"),
    )


class MatchParticipant(Base):
    __tablename__ = "match_participants"

    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    team: Mapped[int] = mapped_column(SmallInteger)  # 0/1; -1 = unassigned (private lobby)
    role: Mapped[str] = mapped_column(String(8))
    lobby_admin: Mapped[bool] = mapped_column(Boolean)
    party_id: Mapped[uuid.UUID | None]
    roster_prefs: Mapped[list[Any]]
    joined_at: Mapped[datetime]

    __table_args__ = (
        CheckConstraint("team IN (-1, 0, 1)", name="team"),
        CheckConstraint("role IN ('player', 'observer')", name="role"),
    )


class Allocation(Base):
    __tablename__ = "allocations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), unique=True
    )
    server_id: Mapped[str] = mapped_column(ForeignKey("servers.id"))
    state: Mapped[str] = mapped_column(String(10))
    port: Mapped[int | None] = mapped_column(Integer)
    pid: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime]
    assigned_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    ended_at: Mapped[datetime | None]
    exit_code: Mapped[int | None] = mapped_column(Integer)
    end_reason: Mapped[str | None] = mapped_column(String(200))

    __table_args__ = (
        CheckConstraint(
            "state IN ('pending', 'assigned', 'started', 'ended', 'cancelled')", name="state"
        ),
        Index("ix_allocations_server_state", "server_id", "state"),
        Index(
            "uq_allocations_server_port_active",
            "server_id",
            "port",
            unique=True,
            postgresql_where=text("state IN ('assigned', 'started')"),
        ),
    )


class JoinTicket(Base):
    __tablename__ = "join_tickets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    server_id: Mapped[str] = mapped_column(ForeignKey("servers.id"))
    team: Mapped[int] = mapped_column(SmallInteger)
    role: Mapped[str] = mapped_column(String(8))
    token: Mapped[str] = mapped_column(Text)
    issued_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    redeemed_at: Mapped[datetime | None]

    __table_args__ = (
        Index("ix_join_tickets_match_account", "match_id", "account_id"),
        CheckConstraint("role IN ('player', 'observer')", name="role"),
    )


# --- queue ------------------------------------------------------------------------------------

class QueueEntry(Base):
    """One queued party (or solo player). The whole party is matched as one block."""

    __tablename__ = "queue_entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    mode: Mapped[str] = mapped_column(String(8))
    leader_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    party_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parties.id", ondelete="CASCADE"))
    region: Mapped[str] = mapped_column(String(20))
    latency_ms: Mapped[dict[str, Any]]
    allow_bots: Mapped[bool] = mapped_column(Boolean)
    roster_prefs: Mapped[list[Any]]
    queued_at: Mapped[datetime]

    __table_args__ = (
        CheckConstraint("mode IN ('casual', 'ranked')", name="mode"),
        Index("ix_queue_entries_mode_queued_at", "mode", "queued_at"),
    )


class QueueMember(Base):
    __tablename__ = "queue_members"

    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("queue_entries.id", ondelete="CASCADE"), primary_key=True
    )
    # unique: an account is in at most one queue entry
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True, unique=True
    )


# --- results / history ------------------------------------------------------------------

class MatchResult(Base):
    """Exactly one row per match (primary key = unique constraint on match_id)."""

    __tablename__ = "match_results"

    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True
    )
    server_id: Mapped[str] = mapped_column(String(40))
    body: Mapped[dict[str, Any]]
    body_sha256: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any]]
    submitted_at: Mapped[datetime]


class MatchPlayerResult(Base):
    """Per-player history row written in the same transaction as the result."""

    __tablename__ = "match_player_results"

    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[str] = mapped_column(String(8))
    team: Mapped[int] = mapped_column(SmallInteger)
    fighter: Mapped[str | None] = mapped_column(String(8))  # NULL: ranked no-show (abandoned)
    won: Mapped[bool] = mapped_column(Boolean)
    kos: Mapped[int] = mapped_column(Integer)
    knocked_out: Mapped[int] = mapped_column(Integer)
    damage_dealt: Mapped[float]
    control_seconds: Mapped[float]
    abandoned: Mapped[bool] = mapped_column(Boolean)
    afk: Mapped[bool] = mapped_column(Boolean)
    xp_gained: Mapped[int] = mapped_column(Integer)
    rating_before: Mapped[float | None]
    rating_after: Mapped[float | None]
    ended_at: Mapped[datetime]

    __table_args__ = (Index("ix_match_player_results_account_ended", "account_id", "ended_at"),)


ALL_TABLES = [t.name for t in Base.metadata.sorted_tables]
