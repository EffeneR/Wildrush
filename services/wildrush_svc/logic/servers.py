"""Game-server / allocator host registry: provisioning, heartbeats, server browser."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import iso_utc
from ..errors import conflict, not_found
from ..models import Allocation, GameServer
from ..schemas import HeartbeatReq
from ..security import SERVER_ID_RE, new_server_secret
from .allocation import cancel_match, lock_match

REGION_RE = re.compile(r"[a-z0-9-]{2,20}")
HEARTBEAT_RECONCILE_GRACE_S = 20.0


class ProvisioningError(ValueError):
    pass


def add_server(db: Session, *, server_id: str, name: str, region: str, now: datetime) -> str:
    """Provision a server id; returns the new secret (shown once by the admin CLI)."""
    if not SERVER_ID_RE.fullmatch(server_id):
        raise ProvisioningError("server id must match ^[a-z0-9-]{3,40}$")
    if not REGION_RE.fullmatch(region):
        raise ProvisioningError("region must match ^[a-z0-9-]{2,20}$")
    name = name.strip()
    if not 1 <= len(name) <= 64 or not name.isprintable():
        raise ProvisioningError("name must be 1..64 printable characters")
    if db.get(GameServer, server_id) is not None:
        raise ProvisioningError(f"server {server_id!r} already exists (use rotate-secret)")
    secret = new_server_secret()
    db.add(
        GameServer(
            id=server_id,
            name=name,
            region=region,
            secret=secret,
            enabled=True,
            created_at=now,
            host=None,
            port_min=None,
            port_max=None,
            capacity=0,
            build_id=None,
            protocol=None,
            status="offline",
            last_heartbeat_at=None,
            last_poll_at=None,
            active_matches=0,
        )
    )
    db.flush()
    return secret


def rotate_secret(db: Session, server_id: str) -> str:
    server = db.get(GameServer, server_id)
    if server is None:
        raise ProvisioningError(f"unknown server {server_id!r}")
    server.secret = new_server_secret()
    db.flush()
    return server.secret


def set_enabled(db: Session, server_id: str, enabled: bool) -> None:
    server = db.get(GameServer, server_id)
    if server is None:
        raise ProvisioningError(f"unknown server {server_id!r}")
    server.enabled = enabled
    if not enabled:
        server.status = "offline"
    db.flush()


def list_all(db: Session) -> list[GameServer]:
    return list(db.scalars(select(GameServer).order_by(GameServer.id)).all())


def heartbeat(db: Session, server_id: str, body: HeartbeatReq, now: datetime) -> dict[str, Any]:
    server = db.scalar(select(GameServer).where(GameServer.id == server_id).with_for_update())
    if server is None:
        raise not_found("unknown_server", "Unknown server")
    if body.region != server.region:
        raise conflict(
            "region_mismatch",
            f"Heartbeat region {body.region!r} differs from the provisioned region {server.region!r}",
        )
    server.name = body.name
    server.host = body.host
    server.port_min = body.port_min
    server.port_max = body.port_max
    server.capacity = body.capacity
    server.build_id = body.build_id
    server.protocol = body.protocol
    server.status = body.status
    server.last_heartbeat_at = now
    server.active_matches = len(body.matches)
    _reconcile(db, server_id, {m.match_id for m in body.matches}, now)
    db.flush()
    return {"ok": True}


def _reconcile(db: Session, server_id: str, reported: set[uuid.UUID], now: datetime) -> None:
    """Allocations the host no longer runs (e.g. after an allocator restart) are ended and
    their unfinished matches cancelled, so capacity is not leaked. A grace period covers
    heartbeats that were built before a process was started."""
    cutoff = now - timedelta(seconds=HEARTBEAT_RECONCILE_GRACE_S)
    candidates = db.execute(
        select(Allocation.id, Allocation.match_id).where(
            Allocation.server_id == server_id,
            Allocation.state == "started",
            Allocation.started_at < cutoff,
        )
    ).all()
    for allocation_id, match_id in candidates:
        if match_id in reported:
            continue
        match = lock_match(db, match_id)
        alloc = db.scalar(select(Allocation).where(Allocation.id == allocation_id).with_for_update())
        if alloc is None or alloc.state != "started":
            continue
        alloc.state = "ended"
        alloc.ended_at = now
        alloc.end_reason = "missing_from_heartbeat"
        if match is not None:
            cancel_match(db, match, "server_process_missing", now)


def browser(db: Session, now: datetime, stale_s: float) -> list[dict[str, Any]]:
    """Server browser: only enabled servers with a heartbeat younger than ``stale_s``."""
    rows = db.scalars(
        select(GameServer)
        .where(
            GameServer.enabled.is_(True),
            GameServer.last_heartbeat_at.is_not(None),
            GameServer.last_heartbeat_at > now - timedelta(seconds=stale_s),
        )
        .order_by(GameServer.region, GameServer.name, GameServer.id)
    ).all()
    return [
        {
            "server_id": s.id,
            "name": s.name,
            "region": s.region,
            "host": s.host,
            "status": s.status,
            "capacity": s.capacity,
            "active_matches": s.active_matches,
            "last_seen": iso_utc(s.last_heartbeat_at),
            "build_id": s.build_id,
            "protocol": s.protocol,
        }
        for s in rows
    ]
