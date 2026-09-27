"""UTC clock abstraction (injectable so tests can move time forward)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """Wall-clock UTC time."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class OffsetClock(SystemClock):
    """Real UTC time plus an adjustable offset (used by tests to expire things)."""

    def __init__(self) -> None:
        self._offset = timedelta(0)
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            offset = self._offset
        return datetime.now(UTC) + offset

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._offset += timedelta(seconds=seconds)


def iso_utc(dt: datetime | None) -> str | None:
    """RFC 3339 UTC string with second precision (``2026-09-27T13:42:00Z``)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def unix(dt: datetime) -> int:
    return int(dt.timestamp())
