#!/usr/bin/env bash
# Briarport environment art: reproducible build entry point (idempotent, non-zero exit on failure).
#
#   tools/build_arena_art.sh [--no-render] [--no-godot] [--textures] [--quick-render]
#
#   1. textures   blender/arena/gen_textures.py (venv python)  -> game/assets/arena/textures/*.png
#                 (skipped when blender/arena/textures.json matches the files on disk; --textures forces)
#   2. build      Blender: blender/arena/build_arena.py -> blender/arena/briarport.blend,
#                 geometric verification vs the layout (verify_arena.py), GLB chunks
#                 game/assets/arena/briarport_{A,B,C,north,south,skyline}.glb + arena_art.json
#   3. godot      scratch-project import + blender/arena/godot_check/check_arena.gd
#                 (never imports inside game/; ARENA_CHECK_DIR overrides the scratch dir)
#   4. render     review renders -> evidence/arena/blender_*.png (Eevee under xvfb-run)
#
# Log: evidence/arena/art_build.log. Blender runs with 2 threads (shared machine).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f .toolchain/paths.env ]]; then
  # shellcheck disable=SC1091
  source .toolchain/paths.env
fi
BLENDER_BIN="${BLENDER_BIN:-$ROOT/.toolchain/blender-4.5.9-linux-x64/blender}"
GODOT_BIN="${GODOT_BIN:-$ROOT/.toolchain/godot/Godot_v4.7.2-stable_linux.x86_64}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
THREADS="${ARENA_BLENDER_THREADS:-2}"

DO_RENDER=1
DO_GODOT=1
FORCE_TEX=0
RENDER_ARGS=(--views overview,topdown,A,B,C,north,south --res 1600x900 --samples 16)
for a in "$@"; do
  case "$a" in
    --no-render) DO_RENDER=0 ;;
    --no-godot) DO_GODOT=0 ;;
    --textures) FORCE_TEX=1 ;;
    --quick-render) RENDER_ARGS=(--views overview,A,B,C --res 960x540 --samples 8) ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "unknown option $a" >&2; exit 2 ;;
  esac
done

mkdir -p evidence/arena game/assets/arena/textures
LOG="$ROOT/evidence/arena/art_build.log"
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1

step() { echo; echo "=== $(date -u +%H:%M:%S) $*"; }
die() { echo "BUILD FAILED: $*"; exit 1; }

for bin in "$BLENDER_BIN" "$PYTHON_BIN"; do
  [[ -x "$bin" ]] || die "missing executable $bin (run tools/setup_env.sh)"
done
echo "Briarport art build  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "blender: $BLENDER_BIN ($("$BLENDER_BIN" --version 2>/dev/null | head -1))"
echo "layout:  game/data/arena/briarport_layout.json sha256=$(sha256sum game/data/arena/briarport_layout.json | cut -c1-16)"

# ---------------------------------------------------------------- 1. textures
step "textures"
need_tex=$FORCE_TEX
if [[ $need_tex -eq 0 ]]; then
  if ! "$PYTHON_BIN" - <<'EOF'
import hashlib, json, os, sys
m = "blender/arena/textures.json"
if not os.path.isfile(m):
    sys.exit(1)
man = json.load(open(m))
for f in man["files"]:
    p = os.path.join("game/assets/arena/textures", f["file"])
    if not os.path.isfile(p) or hashlib.sha256(open(p, "rb").read()).hexdigest() != f["sha256"]:
        print("texture out of date:", f["file"]); sys.exit(1)
print(f"textures up to date ({len(man['files'])} files)")
EOF
  then need_tex=1; fi
fi
if [[ $need_tex -eq 1 ]]; then
  "$PYTHON_BIN" blender/arena/gen_textures.py || die "texture generation"
fi

# ---------------------------------------------------------------- 2. blender build + verify + export
step "blender build + verify + export"
"$BLENDER_BIN" -b --factory-startup -t "$THREADS" --python-exit-code 1 \
  --python blender/arena/build_arena.py 2>&1 | grep -v -E '^(Fra:|$)' || true
rc=${PIPESTATUS[0]}
[[ $rc -eq 0 ]] || die "blender build/verify/export exited $rc"
[[ -f game/assets/arena/arena_art.json ]] || die "arena_art.json not written"
rm -f blender/arena/briarport.blend1

# ---------------------------------------------------------------- 3. godot scratch import check
if [[ $DO_GODOT -eq 1 ]]; then
  step "godot scratch import check"
  [[ -x "$GODOT_BIN" ]] || die "missing Godot $GODOT_BIN"
  CHK="${ARENA_CHECK_DIR:-$(mktemp -d -t arenacheck.XXXXXX)}"
  case "$CHK" in "$ROOT"/game*) die "refusing to use a check dir inside game/";; esac
  echo "scratch project: $CHK"
  rm -rf "$CHK/assets" "$CHK/.godot"
  mkdir -p "$CHK/assets/arena/textures"
  cp blender/arena/godot_check/project.godot "$CHK/project.godot"
  cp blender/arena/godot_check/check_arena.gd "$CHK/check_arena.gd"
  cp game/data/arena/briarport_layout.json "$CHK/layout.json"
  cp game/assets/arena/*.glb game/assets/arena/arena_art.json "$CHK/assets/arena/"
  cp game/assets/arena/textures/*.png "$CHK/assets/arena/textures/"
  imp_log="$CHK/import.log"
  timeout 1800 "$GODOT_BIN" --headless --path "$CHK" --import > "$imp_log" 2>&1 || die "godot --import exited $? (see $imp_log)"
  if grep -E "ERROR|SCRIPT ERROR|Failed|failed" "$imp_log" | grep -v -E "at: |Pages in use exist" > "$CHK/import_errors.txt"; then
    cat "$CHK/import_errors.txt"
    die "godot import reported errors"
  fi
  n_imp=$(ls "$CHK"/assets/arena/*.glb.import 2>/dev/null | wc -l)
  echo "godot import clean: $n_imp glb + $(ls "$CHK"/assets/arena/textures/*.png.import | wc -l) textures imported"
  timeout 900 "$GODOT_BIN" --headless --path "$CHK" --script res://check_arena.gd > "$CHK/check.log" 2>&1 || {
    grep -E "ARENA_CHECK|ERROR" "$CHK/check.log" | head -40; die "godot arena check failed"; }
  grep -E "^ARENA_CHECK" "$CHK/check.log"
  cp "$CHK/arena_check.json" "$ROOT/blender/arena/godot_check/last_check.json"
fi

# ---------------------------------------------------------------- 4. review renders
if [[ $DO_RENDER -eq 1 ]]; then
  step "review renders"
  command -v xvfb-run >/dev/null || die "xvfb-run missing (Eevee needs a display)"
  xvfb-run -a -s "-screen 0 1280x720x24" "$BLENDER_BIN" -b blender/arena/briarport.blend -t "$THREADS" \
    --python-exit-code 1 --python blender/arena/render_review.py -- "${RENDER_ARGS[@]}" 2>&1 \
    | grep -E '^\[render\]|Error|Traceback' || true
  rc=${PIPESTATUS[0]}
  [[ $rc -eq 0 ]] || die "render exited $rc"
fi

step "done"
"$PYTHON_BIN" - <<'EOF'
import json
m = json.load(open("game/assets/arena/arena_art.json"))
for c in m["chunks"]:
    print(f"  {c['path']:42s} {c['triangles']:8d} tris  {c['bytes'] // 1024:6d} KiB")
t = m["totals"]
print(f"  total {t['triangles']} tris, {t['materials']} materials, {t['textures']} textures "
      f"({t['texture_bytes'] // (1 << 20)} MiB), verification passed={m['verification'].get('passed')}")
EOF
echo "BUILD OK"
