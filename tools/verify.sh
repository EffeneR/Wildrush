#!/usr/bin/env bash
# Single verification entry point. Runs every executable gate, records PASS/FAIL per step with
# duration and log path in evidence/verify/latest.json. A step that cannot run is BLOCKED with
# a reason, never PASS.
#   tools/verify.sh            core gates (~45 min on 4 CPU threads, no GPU)
#   tools/verify.sh --quick    import, unit tests, arena analysis, protocol security, services
#   tools/verify.sh --full     core gates + 21-minute soak
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source .toolchain/paths.env
OUT="$ROOT/evidence/verify"
mkdir -p "$OUT/logs"
MODE="${1:-core}"
declare -a NAMES STATUS SECS LOGS

step() {  # step <name> <command...>
  local name="$1"; shift
  local log="$OUT/logs/$name.log"
  local t0=$(date +%s)
  echo "[verify] $name ..."
  if "$@" > "$log" 2>&1; then st=PASS; else st=FAIL; fi
  NAMES+=("$name"); STATUS+=("$st"); SECS+=($(( $(date +%s) - t0 ))); LOGS+=("${log#$ROOT/}")
  echo "[verify] $name: $st ($(( $(date +%s) - t0 )) s)"
}

blocked() {  # blocked <name> <reason>
  NAMES+=("$1"); STATUS+=("BLOCKED: $2"); SECS+=(0); LOGS+=("")
  echo "[verify] $1: BLOCKED ($2)"
}

import_clean() {
  "$GODOT_BIN" --headless --path game --import 2>&1 | tee /dev/stderr | grep -q "ERROR" && return 1 || return 0
}
unit_tests() {
  "$GODOT_BIN" --headless --fixed-fps 60 --path game res://tests/test_runner.tscn 2>&1 | tee /dev/stderr | grep -qE "TESTS: [0-9]+ passed, 0 failed"
}
arena() { "$GODOT_BIN" --headless --path game res://tools/arena_analysis.tscn; }
py() { "$PYTHON_BIN" "$@"; }
ui_shots() {
  command -v xvfb-run >/dev/null || return 2
  xvfb-run -a -s "-screen 0 3440x1440x24" "$GODOT_BIN" --path game res://tools/ui_screenshots.tscn
}
online_check() {  # the game's own HTTP client against a live loopback control service
  services/scripts/dev_up.sh || return 1
  "$GODOT_BIN" --headless --path game res://tools/online_client_check.tscn -- \
    --service-url http://127.0.0.1:8080 --json "$ROOT/evidence/online/online_client_check.json"
  local rc=$?
  services/scripts/dev_down.sh || rc=1
  return $rc
}

step import import_clean
step unit_tests unit_tests
step arena_analysis arena
step services_tests services/scripts/run_tests.sh
step audio_check py tools/audio/check_audio.py
if [[ "$MODE" != "--quick" ]]; then
  step security_game_server py tests/integration/test_security.py
  step ten_clients py tests/integration/test_ten_clients.py
  step netsim_matrix py tests/integration/test_netsim_matrix.py
  step exports_and_fresh_build tools/verify_export.sh
  step online_client_check online_check
  step e2e_ranked py tests/integration/test_e2e_ranked.py
  if command -v xvfb-run >/dev/null; then step ui_screenshots ui_shots; else blocked ui_screenshots "xvfb-run not installed"; fi
  blocked windows_client_run "no Windows machine in this environment (export is built and PE-checked)"
  blocked docker_compose_up "no Docker daemon in this environment (compose config statically checked by services/scripts/check_deploy_config.sh)"
fi
if [[ "$MODE" == "--full" ]]; then
  step soak_21min py tests/integration/test_soak.py
fi

{
  echo "{"
  echo "  \"when\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"mode\": \"$MODE\", \"commit\": \"$(git rev-parse --short HEAD)\","
  echo "  \"steps\": ["
  for i in "${!NAMES[@]}"; do
    sep=","; [[ $i -eq $(( ${#NAMES[@]} - 1 )) ]] && sep=""
    printf '    {"name": "%s", "status": "%s", "seconds": %s, "log": "%s"}%s\n' "${NAMES[$i]}" "${STATUS[$i]}" "${SECS[$i]}" "${LOGS[$i]}" "$sep"
  done
  echo "  ]"
  echo "}"
} > "$OUT/latest.json"
cat "$OUT/latest.json"
for s in "${STATUS[@]}"; do [[ "$s" == FAIL ]] && exit 1; done
exit 0
