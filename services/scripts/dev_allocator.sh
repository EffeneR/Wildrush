#!/usr/bin/env bash
# Local allocator agent for development (loopback only).
#
#   services/scripts/dev_allocator.sh start   # needs WR_SERVER_BINARY=/abs/path/to/exported/server
#   services/scripts/dev_allocator.sh start --dummy   # use the test stand-in instead of the Godot export
#   services/scripts/dev_allocator.sh stop|status
#
# Provisions the server id "dev-local" (region "local") on first use and keeps its secret in
# .run/allocator/dev-local.secret (0600). Optional: WR_SERVER_EXTRA_ARGS_JSON, WR_DEV_REGION,
# WR_MAX_MATCHES, WR_PORT_MIN/WR_PORT_MAX (default 24610-24699).
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_dev_common.sh"

SERVER_ID="${WR_DEV_SERVER_ID:-dev-local}"
REGION="${WR_DEV_REGION:-local}"
SECRET_FILE="$ALLOC_DIR/$SERVER_ID.secret"
cmd="${1:-status}"
mode="${2:-}"

case "$cmd" in
  status)
    if pid_alive "$ALLOC_PID"; then log "allocator running (pid $(cat "$ALLOC_PID"), log $ALLOC_LOG)"; exit 0; fi
    log "allocator not running"; exit 1 ;;
  stop)
    if ! pid_alive "$ALLOC_PID"; then rm -f "$ALLOC_PID"; log "allocator not running"; exit 0; fi
    pid="$(cat "$ALLOC_PID")"
    kill -TERM "$pid"
    # the agent SIGTERMs its game servers and waits up to WR_KILL_GRACE_S (10 s) before SIGKILL
    wait_until 30 bash -c "! kill -0 $pid" || { warn "allocator still alive; SIGKILL"; kill -KILL "$pid" || true; }
    rm -f "$ALLOC_PID"; log "allocator stopped"; exit 0 ;;
  start) ;;
  *) die "usage: $0 start [--dummy] | stop | status" ;;
esac

pid_alive "$ALLOC_PID" && { log "allocator already running (pid $(cat "$ALLOC_PID"))"; exit 0; }
http_get "$SVC_URL/healthz" 3 >/dev/null || die "control service not reachable at $SVC_URL (run dev_up.sh)"
load_dev_env
mkdir -p "$ALLOC_DIR"
chmod 700 "$ALLOC_DIR"

if [[ "$mode" == "--dummy" ]]; then
  export WR_SERVER_BINARY="$PY"
  export WR_SERVER_EXTRA_ARGS_JSON="[\"$SERVICES_DIR/tests/fixtures/dummy_game_server.py\"]"
  export DUMMY_BEHAVIOR="${DUMMY_BEHAVIOR:-sleep}"
  log "using the dummy game server stand-in (DUMMY_BEHAVIOR=$DUMMY_BEHAVIOR)"
fi
[[ -n "${WR_SERVER_BINARY:-}" ]] || die "set WR_SERVER_BINARY=/absolute/path/to/the/exported/linux/server (or use --dummy)"

# Provision the dev server id once; recover a lost secret file by rotating.
if [[ ! -s "$SECRET_FILE" ]]; then
  if ! ( cd "$SERVICES_DIR" && "$PY" -m wildrush_svc.admin add-server --id "$SERVER_ID" --name "Local dev host" \
           --region "$REGION" --write-secret-file "$SECRET_FILE" ); then
    log "server id exists without a local secret file: rotating its secret"
    ( cd "$SERVICES_DIR" && "$PY" -m wildrush_svc.admin rotate-secret --id "$SERVER_ID" --write-secret-file "$SECRET_FILE" ) \
      || die "could not provision $SERVER_ID"
  fi
fi
( cd "$SERVICES_DIR" && "$PY" -m wildrush_svc.admin enable-server --id "$SERVER_ID" >/dev/null ) || die "enable-server failed"

export WR_SERVICE_URL="$SVC_URL" WR_SERVER_ID="$SERVER_ID" WR_SERVER_SECRET_FILE="$SECRET_FILE"
export WR_PUBLIC_HOST="127.0.0.1" WR_REGION="$REGION" WR_SERVER_NAME="${WR_SERVER_NAME:-Local dev host}"
export WR_ALLOCATOR_LOG_DIR="${WR_ALLOCATOR_LOG_DIR:-$ALLOC_DIR/match-logs}"
( cd "$SERVICES_DIR" && "$PY" -m allocator --check-config >/dev/null ) || die "allocator configuration invalid (see above)"

log "starting allocator $SERVER_ID (region $REGION) -> $SVC_URL"
(
  cd "$SERVICES_DIR"
  PYTHONPATH="$SERVICES_DIR" nohup setsid "$PY" -m allocator >>"$ALLOC_LOG" 2>&1 </dev/null &
  echo $! > "$ALLOC_PID"
)
sleep 1
pid_alive "$ALLOC_PID" || { tail -n 20 "$ALLOC_LOG" >&2 || true; die "allocator exited immediately"; }
server_listed() {
  "$PY" - "$SVC_URL" "$SERVER_ID" <<'PYEOF'
import json, sys, urllib.request
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
servers = json.load(opener.open(sys.argv[1] + "/v1/servers", timeout=3))
sys.exit(0 if any(s["server_id"] == sys.argv[2] for s in servers) else 1)
PYEOF
}
wait_until 15 server_listed || die "allocator did not heartbeat within 15 s (log: $ALLOC_LOG)"
log "allocator running (pid $(cat "$ALLOC_PID")); it is listed in $SVC_URL/v1/servers; log $ALLOC_LOG"
