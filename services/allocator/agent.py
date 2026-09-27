"""WILDRUSH allocator agent (standard library only).

Runs on a game-server host. It heartbeats the control service, polls for allocations,
starts **real** dedicated-server processes with a validated fixed argument list (never a
shell), reports ``started``/``ended``, reaps exited children, stops processes that exceed
``WR_MATCH_TIMEOUT_S`` (SIGTERM, then SIGKILL after ``WR_KILL_GRACE_S``) and terminates all
children on shutdown.

Configuration (environment):

  WR_SERVICE_URL            control service base URL (https unless loopback / WR_DEV_ALLOW_HTTP)
  WR_SERVER_ID              provisioned server id (^[a-z0-9-]{3,40}$)
  WR_SERVER_SECRET_FILE     file containing the secret printed by `admin add-server`
  WR_SERVER_BINARY          absolute path of the exported dedicated-server executable
  WR_SERVER_EXTRA_ARGS_JSON optional JSON list of fixed extra engine args (before --headless)
  WR_PORT_MIN / WR_PORT_MAX UDP port range (default 24610-24699)
  WR_PUBLIC_HOST            host name / IP that game clients connect to
  WR_REGION                 region (must equal the provisioned region)
  WR_MAX_MATCHES            concurrent matches (default 4)
  WR_MATCH_TIMEOUT_S        hard match timeout (default 1500)
  optional: WR_SERVER_NAME, WR_BUILD_ID, WR_PROTOCOL, WR_POLL_INTERVAL_S (1),
  WR_HEARTBEAT_INTERVAL_S (5), WR_KILL_GRACE_S (10), WR_ALLOCATOR_LOG_DIR,
  WR_PORT_CHECK_HOST (0.0.0.0), WR_HTTP_TIMEOUT_S (10), WR_DEV_ALLOW_HTTP

Game server command line (exactly):
  [WR_SERVER_BINARY, *extra_args, "--headless", "--", "--server", "--port", PORT,
   "--match-id", MATCH_ID, "--mode", MODE, "--service-url", WR_SERVICE_URL,
   "--server-id", WR_SERVER_ID, "--secret-file", WR_SERVER_SECRET_FILE,
   "--expected-players", N]
"""

from __future__ import annotations

import ctypes
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import IO, Any
from urllib.parse import urlsplit

log = logging.getLogger("wildrush.allocator")

SERVER_ID_RE = re.compile(r"[a-z0-9-]{3,40}")
REGION_RE = re.compile(r"[a-z0-9-]{2,20}")
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
HOSTNAME_RE = re.compile(
    r"(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"
)
BUILD_ID_RE = re.compile(r"[A-Za-z0-9._+-]{1,64}")
MODES = frozenset({"casual", "ranked", "private"})
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
MAX_EXPECTED_PLAYERS = 10


class ConfigError(ValueError):
    pass


class AllocationRejected(ValueError):
    pass


class ServiceUnavailable(RuntimeError):
    pass


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_loopback(host: str) -> bool:
    host = host.strip("[]").lower()
    if host in LOOPBACK:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _valid_host(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return bool(HOSTNAME_RE.fullmatch(host))


def canonical_uuid(value: object) -> str | None:
    """Return ``value`` if it is a canonical lowercase UUID string, else ``None``."""
    if not isinstance(value, str) or not UUID_RE.fullmatch(value):
        return None
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return None
    return value if str(parsed) == value else None


def _int_env(env: Mapping[str, str], name: str, default: int, lo: int, hi: int) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if not lo <= value <= hi:
        raise ConfigError(f"{name} must be within {lo}..{hi}")
    return value


def _float_env(env: Mapping[str, str], name: str, default: float, lo: float, hi: float) -> float:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc
    if not lo <= value <= hi:
        raise ConfigError(f"{name} must be within {lo}..{hi}")
    return value


@dataclass(frozen=True)
class AgentConfig:
    service_url: str
    server_id: str
    secret_file: str
    server_binary: str
    extra_args: tuple[str, ...]
    port_min: int
    port_max: int
    public_host: str
    region: str
    max_matches: int
    match_timeout_s: float
    server_name: str
    build_id: str
    protocol: int
    poll_interval_s: float
    heartbeat_interval_s: float
    kill_grace_s: float
    log_dir: str
    port_check_host: str
    http_timeout_s: float

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> AgentConfig:
        def required(name: str) -> str:
            value = (env.get(name) or "").strip()
            if not value:
                raise ConfigError(f"{name} is required")
            return value

        service_url = required("WR_SERVICE_URL").rstrip("/")
        parts = urlsplit(service_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ConfigError("WR_SERVICE_URL must be an absolute http(s) URL")
        if parts.query or parts.fragment or parts.path not in ("", "/"):
            raise ConfigError("WR_SERVICE_URL must be scheme://host[:port] without a path")
        if parts.scheme == "http" and not _is_loopback(parts.hostname) and not _truthy(env.get("WR_DEV_ALLOW_HTTP")):
            raise ConfigError("WR_SERVICE_URL must use https unless it is a loopback address (or WR_DEV_ALLOW_HTTP=1)")

        server_id = required("WR_SERVER_ID")
        if not SERVER_ID_RE.fullmatch(server_id):
            raise ConfigError("WR_SERVER_ID must match ^[a-z0-9-]{3,40}$")

        secret_file = os.path.abspath(required("WR_SERVER_SECRET_FILE"))
        if not os.path.isfile(secret_file):
            raise ConfigError(f"WR_SERVER_SECRET_FILE {secret_file} does not exist")

        server_binary = required("WR_SERVER_BINARY")
        if not os.path.isabs(server_binary):
            raise ConfigError("WR_SERVER_BINARY must be an absolute path")
        if not os.path.isfile(server_binary) or not os.access(server_binary, os.X_OK):
            raise ConfigError(f"WR_SERVER_BINARY {server_binary} is not an executable file")

        extra_args: tuple[str, ...] = ()
        raw_extra = (env.get("WR_SERVER_EXTRA_ARGS_JSON") or "").strip()
        if raw_extra:
            try:
                parsed = json.loads(raw_extra)
            except ValueError as exc:
                raise ConfigError("WR_SERVER_EXTRA_ARGS_JSON must be a JSON list of strings") from exc
            if not isinstance(parsed, list) or not all(isinstance(a, str) for a in parsed):
                raise ConfigError("WR_SERVER_EXTRA_ARGS_JSON must be a JSON list of strings")
            if len(parsed) > 32:
                raise ConfigError("WR_SERVER_EXTRA_ARGS_JSON: at most 32 arguments")
            for arg in parsed:
                if not arg or "\x00" in arg or len(arg) > 1024:
                    raise ConfigError("WR_SERVER_EXTRA_ARGS_JSON: arguments must be 1..1024 chars without NUL")
                if arg == "--":
                    raise ConfigError("WR_SERVER_EXTRA_ARGS_JSON must not contain '--' (engine args only)")
            extra_args = tuple(parsed)

        port_min = _int_env(env, "WR_PORT_MIN", 24610, 1024, 65535)
        port_max = _int_env(env, "WR_PORT_MAX", 24699, 1024, 65535)
        if port_min > port_max:
            raise ConfigError("WR_PORT_MIN must be <= WR_PORT_MAX")
        if port_max - port_min > 1000:
            raise ConfigError("the port range may span at most 1001 ports")

        public_host = required("WR_PUBLIC_HOST")
        if not _valid_host(public_host):
            raise ConfigError("WR_PUBLIC_HOST must be a host name or IP address")
        region = required("WR_REGION")
        if not REGION_RE.fullmatch(region):
            raise ConfigError("WR_REGION must match ^[a-z0-9-]{2,20}$")

        max_matches = _int_env(env, "WR_MAX_MATCHES", 4, 1, 256)
        if max_matches > port_max - port_min + 1:
            raise ConfigError("WR_MAX_MATCHES exceeds the number of ports in the range")
        build_id = (env.get("WR_BUILD_ID") or "unknown").strip()
        if not BUILD_ID_RE.fullmatch(build_id):
            raise ConfigError("WR_BUILD_ID must match ^[A-Za-z0-9._+-]{1,64}$")
        server_name = (env.get("WR_SERVER_NAME") or server_id).strip()
        if not 1 <= len(server_name) <= 64 or not server_name.isprintable():
            raise ConfigError("WR_SERVER_NAME must be 1..64 printable characters")
        port_check_host = (env.get("WR_PORT_CHECK_HOST") or "0.0.0.0").strip()
        log_dir = (env.get("WR_ALLOCATOR_LOG_DIR") or "").strip() or os.path.join(
            tempfile.gettempdir(), "wildrush-allocator", server_id, "logs"
        )
        return cls(
            service_url=service_url,
            server_id=server_id,
            secret_file=secret_file,
            server_binary=server_binary,
            extra_args=extra_args,
            port_min=port_min,
            port_max=port_max,
            public_host=public_host,
            region=region,
            max_matches=max_matches,
            match_timeout_s=_float_env(env, "WR_MATCH_TIMEOUT_S", 1500.0, 1.0, 7 * 86400.0),
            server_name=server_name,
            build_id=build_id,
            protocol=_int_env(env, "WR_PROTOCOL", 1, 0, 1_000_000),
            poll_interval_s=_float_env(env, "WR_POLL_INTERVAL_S", 1.0, 0.05, 60.0),
            heartbeat_interval_s=_float_env(env, "WR_HEARTBEAT_INTERVAL_S", 5.0, 0.1, 25.0),
            kill_grace_s=_float_env(env, "WR_KILL_GRACE_S", 10.0, 0.1, 300.0),
            log_dir=os.path.abspath(log_dir),
            port_check_host=port_check_host,
            http_timeout_s=_float_env(env, "WR_HTTP_TIMEOUT_S", 10.0, 0.5, 120.0),
        )


def load_secret(path: str) -> str:
    try:
        st = os.stat(path)
        with open(path, encoding="utf-8") as fh:
            secret = fh.read().strip()
    except OSError as exc:
        raise ConfigError(f"cannot read WR_SERVER_SECRET_FILE: {exc.strerror}") from exc
    if not secret or len(secret) > 256 or not secret.isascii() or not secret.isprintable() or " " in secret:
        raise ConfigError("WR_SERVER_SECRET_FILE must contain the printed secret (one token)")
    if st.st_mode & 0o077:
        log.warning("secret file %s is readable by group/others; chmod 600 recommended", path)
    return secret


# --- request signing (same algorithm as the service; see API_CONTRACT.md) ------------------

def sign_request(secret: str, method: str, path: str, timestamp: str, body: bytes) -> str:
    message = f"{method.upper()}\n{path}\n{timestamp}\n{hashlib.sha256(body).hexdigest()}"
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


class ServiceClient:
    def __init__(self, base_url: str, server_id: str, secret: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.server_id = server_id
        self._secret = secret
        self.timeout = timeout
        host = urlsplit(self.base_url).hostname or ""
        handlers: list[urllib.request.BaseHandler] = []
        if _is_loopback(host):
            handlers.append(urllib.request.ProxyHandler({}))  # never proxy loopback
        self._opener = urllib.request.build_opener(*handlers)

    def call(self, method: str, path: str, payload: Any | None = None) -> tuple[int, Any]:
        body = b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(time.time()))
        headers = {
            "X-WR-Server": self.server_id,
            "X-WR-Timestamp": timestamp,
            "X-WR-Signature": sign_request(self._secret, method, path, timestamp, body),
            "Accept": "application/json",
            "User-Agent": "wildrush-allocator/1",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=body if payload is not None else None, method=method, headers=headers
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read()
                return response.status, _json_or_none(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return exc.code, _json_or_none(raw)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise ServiceUnavailable(str(getattr(exc, "reason", exc))) from exc


def _json_or_none(raw: bytes) -> Any:
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


# --- processes ---------------------------------------------------------------------------------

def udp_port_free(port: int, host: str = "0.0.0.0") -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_DGRAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


@dataclass(frozen=True)
class Allocation:
    allocation_id: str
    match_id: str
    mode: str
    port: int
    expected_players: int


def validate_allocation(
    raw: object,
    cfg: AgentConfig,
    busy_ports: set[int],
    port_free: Callable[[int], bool],
) -> Allocation:
    if not isinstance(raw, dict):
        raise AllocationRejected("allocation is not an object")
    allocation_id = canonical_uuid(raw.get("allocation_id"))
    match_id = canonical_uuid(raw.get("match_id"))
    if allocation_id is None:
        raise AllocationRejected("allocation_id is not a UUID")
    if match_id is None:
        raise AllocationRejected("match_id is not a UUID")
    mode = raw.get("mode")
    if mode not in MODES:
        raise AllocationRejected("mode must be casual, ranked or private")
    port = raw.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or not cfg.port_min <= port <= cfg.port_max:
        raise AllocationRejected("port outside the configured range")
    if port in busy_ports or not port_free(port):
        raise AllocationRejected(f"port {port} is not free")
    expected = raw.get("expected_players")
    if not isinstance(expected, int) or isinstance(expected, bool) or not 1 <= expected <= MAX_EXPECTED_PLAYERS:
        raise AllocationRejected("expected_players must be 1..10")
    return Allocation(allocation_id, match_id, str(mode), port, expected)


def build_server_argv(cfg: AgentConfig, alloc: Allocation) -> list[str]:
    """The exact, fixed argument vector for a dedicated game-server process (no shell)."""
    if canonical_uuid(alloc.match_id) is None or alloc.mode not in MODES:
        raise AllocationRejected("invalid allocation")
    if not cfg.port_min <= alloc.port <= cfg.port_max:
        raise AllocationRejected("port outside the configured range")
    if not 1 <= alloc.expected_players <= MAX_EXPECTED_PLAYERS:
        raise AllocationRejected("expected_players must be 1..10")
    return [
        cfg.server_binary,
        *cfg.extra_args,
        "--headless",
        "--",
        "--server",
        "--port", str(alloc.port),
        "--match-id", alloc.match_id,
        "--mode", alloc.mode,
        "--service-url", cfg.service_url,
        "--server-id", cfg.server_id,
        "--secret-file", cfg.secret_file,
        "--expected-players", str(alloc.expected_players),
    ]


def _set_parent_death_signal() -> None:  # pragma: no cover - runs in the child
    """Linux: SIGTERM the game server if the agent dies unexpectedly."""
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    except Exception:
        pass


@dataclass
class Child:
    alloc: Allocation
    proc: subprocess.Popen[bytes]
    started_mono: float
    log_path: str
    log_file: IO[bytes] | None
    started_reported: bool = False
    term_sent_mono: float | None = None
    kill_sent: bool = False
    stop_reason: str | None = None


@dataclass
class Agent:
    cfg: AgentConfig
    client: ServiceClient
    popen: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen
    port_free: Callable[[int], bool] | None = None
    monotonic: Callable[[], float] = time.monotonic
    children: dict[str, Child] = field(default_factory=dict)
    pending_ended: list[dict[str, Any]] = field(default_factory=list)
    rejected: set[str] = field(default_factory=set)
    stopping: bool = False
    _next_heartbeat: float = 0.0
    _next_poll: float = 0.0

    def __post_init__(self) -> None:
        if self.port_free is None:
            host = self.cfg.port_check_host
            self.port_free = lambda port: udp_port_free(port, host)

    # -- lifecycle ------------------------------------------------------------------------

    def request_stop(self, signum: int | None = None, _frame: object = None) -> None:
        if not self.stopping:
            log.info("stop requested (signal %s)", signum)
        self.stopping = True

    def run(self) -> int:
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)
        log.info(
            "allocator %s (%s) -> %s, ports %d-%d, max %d matches, timeout %.0fs",
            self.cfg.server_id, self.cfg.region, self.cfg.service_url,
            self.cfg.port_min, self.cfg.port_max, self.cfg.max_matches, self.cfg.match_timeout_s,
        )
        while not self.stopping:
            try:
                self.step()
            except Exception:  # never die on a transient error
                log.exception("allocator step failed")
            time.sleep(min(0.1, self.cfg.poll_interval_s))
        self.shutdown()
        return 0

    def step(self) -> None:
        now = self.monotonic()
        self.reap()
        self.enforce_timeouts(now)
        if now >= self._next_heartbeat:
            self.heartbeat("online")
            self._next_heartbeat = now + self.cfg.heartbeat_interval_s
        self.report_started()
        self.flush_ended()
        if not self.stopping and now >= self._next_poll:
            self.poll()
            self._next_poll = now + self.cfg.poll_interval_s

    def shutdown(self) -> None:
        log.info("shutting down: terminating %d game server(s)", len(self.children))
        try:
            self.heartbeat("draining")
        except Exception:
            pass
        now = self.monotonic()
        for child in self.children.values():
            child.stop_reason = child.stop_reason or "allocator_shutdown"
            if child.term_sent_mono is None:
                self._signal(child, signal.SIGTERM)
                child.term_sent_mono = now
        deadline = now + self.cfg.kill_grace_s
        while self.children and self.monotonic() < deadline:
            self.reap()
            time.sleep(0.05)
        for child in list(self.children.values()):
            if child.proc.poll() is None:
                self._signal(child, signal.SIGKILL)
                child.kill_sent = True
                try:
                    child.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    log.error("pid %d did not exit after SIGKILL", child.proc.pid)
        self.reap()
        self.flush_ended()

    # -- service calls -------------------------------------------------------------------

    def heartbeat(self, status: str) -> None:
        body = {
            "name": self.cfg.server_name,
            "region": self.cfg.region,
            "host": self.cfg.public_host,
            "port_min": self.cfg.port_min,
            "port_max": self.cfg.port_max,
            "capacity": self.cfg.max_matches,
            "build_id": self.cfg.build_id,
            "protocol": self.cfg.protocol,
            "status": status,
            "matches": [
                {
                    "match_id": c.alloc.match_id,
                    "port": c.alloc.port,
                    "players": c.alloc.expected_players,
                    "state": "stopping" if c.term_sent_mono is not None else "running",
                }
                for c in self.children.values()
            ],
        }
        try:
            code, data = self.client.call("POST", "/v1/servers/heartbeat", body)
        except ServiceUnavailable as exc:
            log.warning("heartbeat failed: %s", exc)
            return
        if code != 200:
            log.warning("heartbeat rejected: %s %s", code, _error_code(data))

    def poll(self) -> None:
        free_slots = self.cfg.max_matches - len(self.children)
        if free_slots <= 0:
            return
        busy = {c.alloc.port for c in self.children.values()}
        ports: list[int] = []
        assert self.port_free is not None
        for port in range(self.cfg.port_min, self.cfg.port_max + 1):
            if len(ports) >= free_slots:
                break
            if port not in busy and self.port_free(port):
                ports.append(port)
        try:
            code, data = self.client.call("POST", "/v1/allocator/poll", {"free_ports": ports})
        except ServiceUnavailable as exc:
            log.warning("poll failed: %s", exc)
            return
        if code != 200 or not isinstance(data, dict):
            log.warning("poll rejected: %s %s", code, _error_code(data))
            return
        allocations = data.get("allocations")
        if not isinstance(allocations, list):
            return
        for raw in allocations:
            self._handle_allocation(raw)

    def _handle_allocation(self, raw: object) -> None:
        allocation_id = raw.get("allocation_id") if isinstance(raw, dict) else None
        if isinstance(allocation_id, str) and allocation_id in self.children:
            # Re-sent because our "started" report did not arrive: report again.
            self.children[allocation_id].started_reported = False
            return
        if isinstance(allocation_id, str) and allocation_id in self.rejected:
            return
        if len(self.children) >= self.cfg.max_matches:
            return  # stays assigned; handed out again on a later poll
        assert self.port_free is not None
        busy = {c.alloc.port for c in self.children.values()}
        try:
            alloc = validate_allocation(raw, self.cfg, busy, self.port_free)
            self.spawn(alloc)
        except AllocationRejected as exc:
            log.warning("rejecting allocation %s: %s", allocation_id, exc)
            if canonical_uuid(allocation_id) and isinstance(raw, dict) and canonical_uuid(raw.get("match_id")):
                self.rejected.add(str(allocation_id))
                self.pending_ended.append(
                    {
                        "allocation_id": allocation_id,
                        "match_id": raw["match_id"],
                        "exit_code": -1,
                        "reason": f"rejected: {exc}"[:200],
                    }
                )

    def spawn(self, alloc: Allocation) -> Child:
        argv = build_server_argv(self.cfg, alloc)
        os.makedirs(self.cfg.log_dir, mode=0o750, exist_ok=True)
        log_path = os.path.join(self.cfg.log_dir, f"{alloc.match_id}.log")
        log_file = open(log_path, "ab")  # noqa: SIM115 - closed when the child is reaped
        env = {k: v for k, v in os.environ.items() if not k.startswith("WR_")}
        kwargs: dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": log_file,
            "stderr": subprocess.STDOUT,
            "close_fds": True,
            "start_new_session": True,
            "env": env,
            "cwd": os.path.dirname(self.cfg.server_binary) or "/",
            "shell": False,
        }
        if sys.platform.startswith("linux"):
            kwargs["preexec_fn"] = _set_parent_death_signal
        try:
            proc = self.popen(argv, **kwargs)
        except OSError as exc:
            log_file.close()
            raise AllocationRejected(f"could not start server: {exc.strerror}") from exc
        child = Child(alloc=alloc, proc=proc, started_mono=self.monotonic(), log_path=log_path, log_file=log_file)
        self.children[alloc.allocation_id] = child
        log.info(
            "started match %s (%s) pid %d on port %d, log %s",
            alloc.match_id, alloc.mode, proc.pid, alloc.port, log_path,
        )
        return child

    def report_started(self) -> None:
        for child in list(self.children.values()):
            if child.started_reported or child.term_sent_mono is not None:
                continue
            body = {
                "allocation_id": child.alloc.allocation_id,
                "match_id": child.alloc.match_id,
                "port": child.alloc.port,
                "pid": child.proc.pid,
            }
            try:
                code, data = self.client.call("POST", "/v1/allocator/started", body)
            except ServiceUnavailable as exc:
                log.warning("started report failed (will retry): %s", exc)
                return
            if code == 200:
                child.started_reported = True
            elif code in (404, 409):
                log.warning("service refused match %s (%s): stopping it", child.alloc.match_id, _error_code(data))
                child.stop_reason = f"refused_by_service: {_error_code(data)}"
                self._signal(child, signal.SIGTERM)
                child.term_sent_mono = self.monotonic()
            else:
                log.warning("started report rejected: %s %s (will retry)", code, _error_code(data))

    def flush_ended(self) -> None:
        remaining: list[dict[str, Any]] = []
        for item in self.pending_ended:
            try:
                code, data = self.client.call("POST", "/v1/allocator/ended", item)
            except ServiceUnavailable:
                remaining.append(item)
                continue
            if code == 200:
                continue
            if code == 429 or code >= 500:
                remaining.append(item)
            else:
                log.warning("ended report for %s rejected: %s %s", item["match_id"], code, _error_code(data))
        self.pending_ended = remaining[-1000:]

    # -- child management -------------------------------------------------------------------

    def reap(self) -> None:
        for allocation_id, child in list(self.children.items()):
            code = child.proc.poll()
            if code is None:
                continue
            if child.log_file is not None:
                child.log_file.close()
                child.log_file = None
            reason = child.stop_reason or ("exited" if code == 0 else "crashed")
            log.info("match %s pid %d exited with %s (%s)", child.alloc.match_id, child.proc.pid, code, reason)
            self.pending_ended.append(
                {
                    "allocation_id": allocation_id,
                    "match_id": child.alloc.match_id,
                    "exit_code": max(-1000, min(1000, int(code))),
                    "reason": reason[:200],
                }
            )
            del self.children[allocation_id]

    def enforce_timeouts(self, now: float) -> None:
        for child in self.children.values():
            if child.term_sent_mono is None:
                if now - child.started_mono >= self.cfg.match_timeout_s:
                    log.warning("match %s exceeded %.0fs: SIGTERM", child.alloc.match_id, self.cfg.match_timeout_s)
                    child.stop_reason = "timeout"
                    self._signal(child, signal.SIGTERM)
                    child.term_sent_mono = now
            elif not child.kill_sent and now - child.term_sent_mono >= self.cfg.kill_grace_s:
                log.warning("match %s ignored SIGTERM for %.0fs: SIGKILL", child.alloc.match_id, self.cfg.kill_grace_s)
                self._signal(child, signal.SIGKILL)
                child.kill_sent = True

    @staticmethod
    def _signal(child: Child, sig: int) -> None:
        if child.proc.poll() is not None:
            return
        try:
            # The child is a session leader (start_new_session): signal its whole group.
            os.killpg(child.proc.pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                child.proc.send_signal(sig)
            except ProcessLookupError:
                pass


def _error_code(data: Any) -> str:
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        return str(data["error"].get("code"))
    return "-"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(
        level=os.environ.get("WR_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        cfg = AgentConfig.from_env(os.environ)
        secret = load_secret(cfg.secret_file)
    except ConfigError as exc:
        log.error("configuration error: %s", exc)
        return 2
    if "--check-config" in args:
        example = Allocation(str(uuid.uuid4()), str(uuid.uuid4()), "casual", cfg.port_min, 10)
        print(json.dumps({"config": {k: v for k, v in cfg.__dict__.items()}, "argv_example": build_server_argv(cfg, example)}, indent=2))
        return 0
    agent = Agent(cfg=cfg, client=ServiceClient(cfg.service_url, cfg.server_id, secret, cfg.http_timeout_s))
    return agent.run()


if __name__ == "__main__":
    sys.exit(main())
