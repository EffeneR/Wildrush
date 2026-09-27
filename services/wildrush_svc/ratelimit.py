"""In-process sliding-window rate limiter.

Limits are exact sliding windows (a deque of hit timestamps per key). State lives in the
service process only, so run a single service process (the default ``serve`` entry point
uses one uvicorn worker). Restarting the service resets all windows.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Limit:
    name: str
    count: int
    window_s: float = 60.0


# Contract: "login 10/min per IP and 10/min per username · register 5/min · party invites
# 20/min per account · queue join/leave 20/min per account · all others 120/min per account".
LOGIN_PER_IP = Limit("login_ip", 10)
LOGIN_PER_USERNAME = Limit("login_user", 10)
REGISTER_PER_IP = Limit("register_ip", 5)
INVITES_PER_ACCOUNT = Limit("invites", 20)
QUEUE_PER_ACCOUNT = Limit("queue", 20)
GENERAL_PER_ACCOUNT = Limit("account", 120)
# Not specified by the contract (see CONTRACT_NOTES.md):
ANON_PER_IP = Limit("anon_ip", 120)  # unauthenticated endpoints and failed player auth


class RateLimiter:
    def __init__(self, enabled: bool = True, monotonic: Callable[[], float] = time.monotonic) -> None:
        self.enabled = enabled
        self._monotonic = monotonic
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()
        self._ops = 0

    def hit(self, limit: Limit, key: str) -> float | None:
        """Record one request. Returns ``None`` if allowed, else seconds until retry."""
        if not self.enabled:
            return None
        now = self._monotonic()
        cutoff = now - limit.window_s
        with self._lock:
            self._ops += 1
            if self._ops % 5000 == 0:
                self._sweep(now)
            dq = self._hits.setdefault((limit.name, key), deque())
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= limit.count:
                return max(0.001, dq[0] + limit.window_s - now)
            dq.append(now)
            return None

    def _sweep(self, now: float) -> None:
        # Drop keys whose newest hit is older than any window we use (bounded memory).
        stale = [k for k, dq in self._hits.items() if not dq or dq[-1] < now - 3600]
        for k in stale:
            del self._hits[k]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
