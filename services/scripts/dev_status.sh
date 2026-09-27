#!/usr/bin/env bash
# Show the state of the native dev stack. Exit 0 only if PostgreSQL and the service are healthy.
set -uo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_dev_common.sh"

rc=0
if [[ -f "$PG_DATA/PG_VERSION" ]] && pg_running; then
  if as_pg "$PG_BIN/pg_isready" -q -h "$PG_SOCK" -p "$PG_PORT"; then
    log "postgres : running, accepting connections on 127.0.0.1:$PG_PORT"
  else
    log "postgres : running but NOT accepting connections"; rc=1
  fi
else
  log "postgres : stopped"; rc=1
fi

if pid_alive "$SVC_PID"; then
  if body="$(http_get "$SVC_URL/healthz" 5)"; then
    log "service  : running (pid $(cat "$SVC_PID")) $SVC_URL/healthz -> $body"
  else
    log "service  : pid $(cat "$SVC_PID") alive but unhealthy: $body"; rc=1
  fi
else
  log "service  : stopped"; rc=1
fi

if pid_alive "$ALLOC_PID"; then
  log "allocator: running (pid $(cat "$ALLOC_PID"), log $ALLOC_LOG)"
else
  log "allocator: not running (optional; see services/scripts/dev_allocator.sh)"
fi
exit "$rc"
