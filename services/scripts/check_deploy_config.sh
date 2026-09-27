#!/usr/bin/env bash
# Static validation of the container deployment files (no containers are started):
#   * `docker compose config` for deploy/docker-compose.yml and deploy/allocator.compose.yml
#     (works with the Docker CLI alone; no daemon needed), using a temp copy with
#     placeholder secrets so real secrets are never touched;
#   * `caddy validate` for deploy/Caddyfile if a caddy binary is available (WR_CADDY_BIN or PATH).
# Output goes to stdout and evidence/services/deploy_checks_latest.txt.
# Exit: 0 all executed checks passed, 1 a check failed. Missing tools are reported as
# BLOCKED (not PASS) and make the exit code 3 unless WR_ALLOW_BLOCKED=1.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICES_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$SERVICES_DIR/.." && pwd)"
OUT="$ROOT_DIR/evidence/services/deploy_checks_latest.txt"
mkdir -p "$(dirname "$OUT")"
exec > >(tee "$OUT") 2>&1

failed=0
blocked=0
result() { printf '%-60s %s\n' "$1" "$2"; }
echo "# WILDRUSH deployment config checks — $(date -u +%Y-%m-%dT%H:%M:%SZ)"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cp -r "$SERVICES_DIR/deploy" "$tmp/deploy"
cp "$SERVICES_DIR/.env.example" "$tmp/.env"
rm -f "$tmp/deploy/secrets/"*.txt "$tmp/deploy/secrets/"*.secret
printf 'placeholder-not-a-secret\n' > "$tmp/deploy/secrets/pg_password.txt"
printf 'placeholder-not-a-secret\n' > "$tmp/deploy/secrets/allocator.secret"

if docker compose version >/dev/null 2>&1; then
  echo "# $(docker compose version)"
  if (cd "$tmp/deploy" && timeout 60 docker compose --env-file ../.env -f docker-compose.yml config --quiet); then
    result "docker compose config deploy/docker-compose.yml" PASS
  else
    result "docker compose config deploy/docker-compose.yml" FAIL; failed=1
  fi
  bind_line="$(cd "$tmp/deploy" && timeout 60 docker compose --env-file ../.env -f docker-compose.yml config | grep -c 'host_ip: 127.0.0.1')"
  if [[ "$bind_line" == "3" ]]; then
    result "caddy ports bound to 127.0.0.1 by default" PASS
  else
    result "caddy ports bound to 127.0.0.1 by default" "FAIL ($bind_line)"; failed=1
  fi
  if (cd "$tmp/deploy" && WR_ALLOCATOR_SERVER_ID=eu-1 WR_ALLOCATOR_PUBLIC_HOST=game.example.org WR_ALLOCATOR_REGION=eu \
        timeout 60 docker compose --env-file ../.env -f allocator.compose.yml config --quiet); then
    result "docker compose config deploy/allocator.compose.yml" PASS
  else
    result "docker compose config deploy/allocator.compose.yml" FAIL; failed=1
  fi
else
  result "docker compose config" "BLOCKED (docker compose CLI not available)"; blocked=1
fi

CADDY="${WR_CADDY_BIN:-$(command -v caddy || true)}"
if [[ -n "$CADDY" && -x "$CADDY" ]]; then
  echo "# caddy $("$CADDY" version)"
  if WR_DOMAIN=wildrush.example.org timeout 60 "$CADDY" validate --config "$SERVICES_DIR/deploy/Caddyfile" --adapter caddyfile >"$tmp/caddy.log" 2>&1; then
    result "caddy validate deploy/Caddyfile" PASS
  else
    cat "$tmp/caddy.log"; result "caddy validate deploy/Caddyfile" FAIL; failed=1
  fi
else
  result "caddy validate deploy/Caddyfile" "BLOCKED (no caddy binary; set WR_CADDY_BIN)"; blocked=1
fi

if docker info >/dev/null 2>&1; then
  result "docker daemon" "available (build/up not attempted by this script)"
else
  result "docker build / docker compose up" "BLOCKED (no Docker daemon)"
fi

(( failed )) && exit 1
(( blocked )) && [[ "${WR_ALLOW_BLOCKED:-0}" != "1" ]] && exit 3
exit 0
