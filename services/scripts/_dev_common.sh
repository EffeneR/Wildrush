#!/usr/bin/env bash
# Shared settings/helpers for services/scripts/dev_*.sh (sourced, not executed).
# Everything binds to loopback only. Runtime state lives in .run/ (git-ignored).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICES_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$SERVICES_DIR/.." && pwd)"

RUN_DIR="${WR_RUN_DIR:-$ROOT_DIR/.run}"
PG_DIR="$RUN_DIR/pg"
PG_DATA="$PG_DIR/data"
PG_SOCK="$PG_DIR/sock"
PG_LOG="$PG_DIR/postgres.log"
PG_PORT="${WR_DEV_PG_PORT:-55432}"
PG_BIN="${WR_PG_BIN:-/usr/lib/postgresql/16/bin}"
PY="${WR_PYTHON:-$ROOT_DIR/.venv/bin/python}"
DEV_ENV="$RUN_DIR/dev.env"
SVC_PID="$RUN_DIR/service.pid"
SVC_LOG="$RUN_DIR/service.log"
SVC_HOST="127.0.0.1"
SVC_PORT="${WR_DEV_SERVICE_PORT:-8080}"
SVC_URL="http://$SVC_HOST:$SVC_PORT"
DB_NAME="wildrush"
DB_USER="wildrush"
ALLOC_DIR="$RUN_DIR/allocator"
ALLOC_PID="$ALLOC_DIR/allocator.pid"
ALLOC_LOG="$ALLOC_DIR/allocator.log"

log() { printf '[dev] %s\n' "$*"; }
warn() { printf '[dev] WARN: %s\n' "$*" >&2; }
die() { printf '[dev] ERROR: %s\n' "$*" >&2; exit 1; }

# PostgreSQL refuses to run as root: use the "postgres" system user when we are root.
if [[ "$(id -u)" -eq 0 ]]; then
  PG_OS_USER="postgres"
  as_pg() { runuser -u postgres -- "$@"; }
else
  PG_OS_USER="$(id -un)"
  as_pg() { "$@"; }
fi

pg_running() { as_pg "$PG_BIN/pg_ctl" -D "$PG_DATA" status >/dev/null 2>&1; }

psql_admin() {
  as_pg "$PG_BIN/psql" -X -q -v ON_ERROR_STOP=1 -h "$PG_SOCK" -p "$PG_PORT" -U "$PG_OS_USER" -d postgres "$@"
}

pid_alive() { [[ -f "$1" ]] && kill -0 "$(cat "$1" 2>/dev/null)" 2>/dev/null; }

# http_get URL TIMEOUT_S -> prints body, exit 0 on HTTP 200 (python: curl may be absent)
http_get() {
  "$PY" - "$1" "$2" <<'PYEOF'
import sys, urllib.request
url, timeout = sys.argv[1], float(sys.argv[2])
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with opener.open(url, timeout=timeout) as r:
        print(r.read().decode())
        sys.exit(0 if r.status == 200 else 1)
except Exception as exc:
    print(f"unreachable: {exc}")
    sys.exit(1)
PYEOF
}

# wait_until TIMEOUT_S CMD... (polls every 0.5 s)
wait_until() {
  local timeout="$1"; shift
  local deadline=$((SECONDS + timeout))
  until "$@" >/dev/null 2>&1; do
    (( SECONDS >= deadline )) && return 1
    sleep 0.5
  done
}

load_dev_env() {
  [[ -f "$DEV_ENV" ]] || die "$DEV_ENV missing; run services/scripts/dev_up.sh first"
  set -a
  # shellcheck disable=SC1090
  source "$DEV_ENV"
  set +a
}
