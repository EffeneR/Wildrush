#!/usr/bin/env bash
# G12: fresh exported build verification, run outside the editor from another working dir.
#   tools/verify_export.sh [--skip-export]
# 1. exports Linux server, Linux client (verification preset) and Windows client
# 2. copies the Linux builds to a fresh temp dir (not the repo) and, from there:
#    a) exported server + exported headless client play a networked match (autopilot client)
#    b) exported client runs the full screen flow: boot -> menu -> offline match -> results -> menu
#    c) checks save paths (settings, offline profile, replays under the user data dir)
#    d) checks both processes shut down with exit code 0
# The Windows client is exported and size/format-checked only (no Windows machine here).
# Evidence: evidence/export/verify_export.json + logs.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/.toolchain/paths.env"
EVI="$ROOT/evidence/export"
mkdir -p "$EVI"
FRESH="$(mktemp -d /tmp/wildrush_g12.XXXXXX)"
USERDATA="$FRESH/userdata"
mkdir -p "$USERDATA"
RESULT="$EVI/verify_export.json"
declare -A STEP

if [[ "${1:-}" != "--skip-export" ]]; then
  cd "$ROOT/game"
  "$GODOT_BIN" --headless --path . --import > "$EVI/import.log" 2>&1
  for spec in "Linux Server|../builds/linux_server/wildrush_server.x86_64" \
              "Linux Client (verification)|../builds/linux_client/wildrush.x86_64" \
              "Windows Client|../builds/windows_client/WILDRUSH.exe"; do
    name="${spec%%|*}"; out="${spec##*|}"
    if "$GODOT_BIN" --headless --path . --export-release "$name" "$out" > "$EVI/export_${name// /_}.log" 2>&1; then
      STEP["export:$name"]=PASS
    else
      STEP["export:$name"]=FAIL
    fi
  done
  cd "$ROOT"
fi

cp -r "$ROOT/builds/linux_server" "$ROOT/builds/linux_client" "$FRESH/"
cd "$FRESH"
# user data isolated in the fresh dir (XDG_DATA_HOME), so nothing from the dev machine leaks in
export XDG_DATA_HOME="$USERDATA"

# a) networked match: exported server + exported client
PORT=24671
./linux_server/wildrush_server.x86_64 --headless -- --port $PORT --mode private --autostart 1 --allow-bots \
  --quit-after-s 75 > "$EVI/server.log" 2>&1 &
SPID=$!
sleep 3
./linux_client/wildrush.x86_64 --headless -- --autopilot fight --connect 127.0.0.1:$PORT --name G12 \
  --log-json "$EVI/client.jsonl" --quit-after-s 60 > "$EVI/client.log" 2>&1
CEXIT=$?
wait $SPID
SEXIT=$?
if grep -q '"match_start"' "$EVI/server.log" && grep -q '"ev":"joined"' "$EVI/server.log" && [[ $CEXIT -eq 0 && $SEXIT -eq 0 ]] \
   && grep -q '"ev": *"stats"' "$EVI/client.jsonl" && ! grep -q "SCRIPT ERROR" "$EVI/server.log" "$EVI/client.log"; then
  STEP[online_match]=PASS
else
  STEP[online_match]=FAIL
fi

# b) full screen flow on the exported client (headless, fixed 60 fps)
./linux_client/wildrush.x86_64 --headless --fixed-fps 60 -- --flow-test --autopilot-self \
  --json "$EVI/flow.json" > "$EVI/flow.log" 2>&1
FEXIT=$?
[[ $FEXIT -eq 0 ]] && STEP[offline_flow]=PASS || STEP[offline_flow]=FAIL

# c) save paths
UD="$USERDATA/WILDRUSH"
[[ -f "$UD/settings.cfg" ]] && STEP[save_settings]=PASS || STEP[save_settings]=FAIL
[[ -f "$UD/profile_offline.json" ]] && STEP[save_profile]=PASS || STEP[save_profile]=FAIL
ls "$UD/replays/"*.wrr > /dev/null 2>&1 && STEP[save_replay]=PASS || STEP[save_replay]=FAIL

# d) Windows client: exported file exists and is a PE executable
WEXE="$ROOT/builds/windows_client/WILDRUSH.exe"
if [[ -f "$WEXE" ]] && head -c 2 "$WEXE" | grep -q "MZ"; then STEP[windows_export_pe]=PASS; else STEP[windows_export_pe]=FAIL; fi
# console wrapper (docs/TROUBLESHOOTING.md tells players to run it to see startup errors)
WCON="${WEXE%.exe}.console.exe"
if [[ -f "$WCON" ]] && head -c 2 "$WCON" | grep -q "MZ"; then STEP[windows_console_wrapper]=PASS; else STEP[windows_console_wrapper]=FAIL; fi
STEP[windows_run]=BLOCKED

{
  echo "{"
  echo "  \"fresh_dir\": \"$FRESH\", \"user_data\": \"$UD\","
  echo "  \"server_exit\": $SEXIT, \"client_exit\": $CEXIT, \"flow_exit\": $FEXIT,"
  echo "  \"windows_run_note\": \"no Windows machine in this environment; export verified as PE only\","
  echo "  \"steps\": {"
  first=1
  for k in "${!STEP[@]}"; do
    [[ $first -eq 0 ]] && echo ","
    printf '    "%s": "%s"' "$k" "${STEP[$k]}"
    first=0
  done
  echo ""
  echo "  }"
  echo "}"
} > "$RESULT"
cat "$RESULT"
for k in "${!STEP[@]}"; do [[ "${STEP[$k]}" == FAIL ]] && exit 1; done
exit 0
