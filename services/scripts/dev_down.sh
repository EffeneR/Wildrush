#!/usr/bin/env bash
# Stop the native dev stack: allocator (if started by dev_allocator.sh), service, PostgreSQL.
# Data in .run/pg is kept. Exit code is nonzero if something could not be stopped.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_dev_common.sh"

rc=0

stop_pidfile() {  # name pidfile grace_s
  local name="$1" pidfile="$2" grace="$3" pid
  if ! pid_alive "$pidfile"; then
    rm -f "$pidfile"
    log "$name not running"
    return 0
  fi
  pid="$(cat "$pidfile")"
  log "stopping $name (pid $pid)"
  kill -TERM "$pid" 2>/dev/null || true
  if ! wait_until "$grace" bash -c "! kill -0 $pid"; then
    warn "$name did not exit after ${grace}s; sending SIGKILL"
    kill -KILL "$pid" 2>/dev/null || true
    wait_until 5 bash -c "! kill -0 $pid" || { warn "$name (pid $pid) still alive"; return 1; }
  fi
  rm -f "$pidfile"
}

stop_pidfile "allocator" "$ALLOC_PID" 30 || rc=1
stop_pidfile "control service" "$SVC_PID" 15 || rc=1

if [[ -f "$PG_DATA/PG_VERSION" ]] && pg_running; then
  log "stopping PostgreSQL"
  as_pg "$PG_BIN/pg_ctl" -D "$PG_DATA" -m fast -w -t 60 stop >/dev/null || { warn "pg_ctl stop failed"; rc=1; }
else
  log "PostgreSQL not running"
fi
exit "$rc"
