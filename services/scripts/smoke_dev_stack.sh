#!/usr/bin/env bash
# Smoke test of the native dev stack (loopback only):
#   dev_up.sh -> dev_status.sh -> dev_allocator.sh start --dummy -> over HTTP: register two
#   accounts, create a private match (allocator really starts a stand-in server process),
#   join it as observer, check the server browser -> stop what this script started.
# Output: stdout and evidence/services/dev_stack_smoke_latest.txt. Exit nonzero on failure.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_dev_common.sh"
OUT="$ROOT_DIR/evidence/services/dev_stack_smoke_latest.txt"
mkdir -p "$(dirname "$OUT")"
exec > >(tee "$OUT") 2>&1
echo "# WILDRUSH dev stack smoke test — $(date -u +%Y-%m-%dT%H:%M:%SZ)"

svc_was_running=0; pid_alive "$SVC_PID" && svc_was_running=1
alloc_was_running=0; pid_alive "$ALLOC_PID" && alloc_was_running=1
cleanup() {
  local rc=$?
  if (( ! alloc_was_running )); then "$SCRIPT_DIR/dev_allocator.sh" stop || rc=1; fi
  if (( ! svc_was_running )); then "$SCRIPT_DIR/dev_down.sh" || rc=1; fi
  echo "# exit_code: $rc"
  exit "$rc"
}
trap cleanup EXIT

timeout 180 "$SCRIPT_DIR/dev_up.sh"
timeout 60 "$SCRIPT_DIR/dev_status.sh"
if (( alloc_was_running )); then
  log "an allocator is already running: skipping the private-match step (it may run a real server)"
  exit 0
fi
timeout 120 "$SCRIPT_DIR/dev_allocator.sh" start --dummy

timeout 120 "$PY" - "$SVC_URL" <<'PYEOF'
import json, secrets, sys, urllib.error, urllib.request

base = sys.argv[1]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def call(method, path, body=None, token=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with opener.open(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")

tokens = {}
for role in ("host", "guest"):
    user = f"smoke_{role[:1]}{secrets.token_hex(4)}"
    code, _ = call("POST", "/v1/auth/register", {"username": user, "password": "smoke-password-1"})
    assert code == 201, (code, _)
    code, body = call("POST", "/v1/auth/login", {"username": user, "password": "smoke-password-1"})
    assert code == 200, (code, body)
    tokens[role] = body["token"]
code, created = call("POST", "/v1/private", {"region": "local"}, tokens["host"])
assert code == 200, (code, created)
assert created["host"] == "127.0.0.1" and 24610 <= created["port"] <= 24699 and created["ticket"].count(".") == 1
code, joined = call("POST", "/v1/private/join", {"join_code": created["join_code"], "role": "observer"}, tokens["guest"])
assert code == 200 and joined["port"] == created["port"], (code, joined)
code, servers = call("GET", "/v1/servers")
assert code == 200 and any(s["server_id"] == "dev-local" for s in servers), servers
print(f"[smoke] private match {created['match_id']} on 127.0.0.1:{created['port']} (join code {created['join_code']}), observer joined")
PYEOF
log "smoke test passed"
