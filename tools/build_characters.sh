#!/usr/bin/env bash
# WILDRUSH — rebuild the five fighters end to end (idempotent, reproducible).
#
#   tools/build_characters.sh [nyx bruno vex hops scrap]      (default: all five)
#
# Per fighter: SDF sculpt + marching cubes (venv) -> Blender assembly (decimate, UV, armature,
# bone-heat weights) -> procedural textures (venv) -> control rig + all contract clips + bake +
# checks + .blend + GLB + <id>_anim.json (Blender) -> palette textures + Godot import sidecar ->
# GLB re-import check (Blender) -> evidence renders + UI portraits (Blender Eevee).
# Then one scratch Godot 4.7 project imports every GLB and verifies bones/clips/loops/materials.
# All output goes to evidence/characters/build.log; any failing step exits nonzero.
#
# Env: WILDRUSH_CHAR_WORK (intermediates, default /tmp/wildrush_charwork)
#      WILDRUSH_CHARCHECK_DIR (scratch Godot project, default $WILDRUSH_CHAR_WORK/godot_charcheck)
#      CHAR_MESH_RES / CHAR_CLOTH_RES (marching-cubes voxel size in metres, default 0.0024 / 0.0035)
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$ROOT/.toolchain/paths.env" ]; then
	# shellcheck disable=SC1091
	source "$ROOT/.toolchain/paths.env"
fi
BLENDER="${BLENDER_BIN:-$ROOT/.toolchain/blender-4.5.9-linux-x64/blender}"
GODOT="${GODOT_BIN:-$ROOT/.toolchain/godot/Godot_v4.7.2-stable_linux.x86_64}"
PY="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
CH="$ROOT/blender/characters"
GA="$ROOT/game/assets/characters"
EV="$ROOT/evidence/characters"
PORTRAITS="$ROOT/game/assets/ui/portraits"
WORK="${WILDRUSH_CHAR_WORK:-/tmp/wildrush_charwork}"
CHECK="${WILDRUSH_CHARCHECK_DIR:-$WORK/godot_charcheck}"
RES="${CHAR_MESH_RES:-0.0024}"
CRES="${CHAR_CLOTH_RES:-0.0035}"
LOG="$EV/build.log"
FIGHTERS=("$@")
if [ ${#FIGHTERS[@]} -eq 0 ]; then
	FIGHTERS=(nyx bruno vex hops scrap)
fi
# other workstreams share this 4-thread machine: keep every tool at 2 threads
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2

mkdir -p "$WORK" "$EV" "$PORTRAITS" "$GA"
{
	echo "==== build_characters.sh $(date -u +%Y-%m-%dT%H:%M:%SZ) fighters: ${FIGHTERS[*]}"
	echo "blender: $BLENDER"; echo "godot: $GODOT"; echo "python: $PY"; echo "work: $WORK res=$RES cloth_res=$CRES"
} >>"$LOG"

run() {
	local name="$1"
	shift
	echo "---- [$name] $*" >>"$LOG"
	local t0
	t0=$(date +%s)
	"$@" >>"$LOG" 2>&1
	local rc=$?
	echo "---- [$name] exit=$rc ($(($(date +%s) - t0))s)" >>"$LOG"
	echo "[$name] exit=$rc ($(($(date +%s) - t0))s)"
	if [ $rc -ne 0 ]; then
		echo "FAILED: $name (see $LOG)" | tee -a "$LOG"
		exit $rc
	fi
}

# BUILD_FROM=mesh|assemble|textures|anim|render skips earlier steps (iteration aid; default: everything)
FROM="${BUILD_FROM:-mesh}"
step_on() {
	local order="mesh assemble textures anim render"
	local seen=0
	for s in $order; do
		[ "$s" = "$FROM" ] && seen=1
		[ "$s" = "$1" ] && { [ $seen -eq 1 ] && return 0 || return 1; }
	done
	return 1
}

for id in "${FIGHTERS[@]}"; do
	mkdir -p "$CH/$id/textures" "$GA/$id"
	step_on mesh && run "$id mesh" "$PY" "$CH/wr_mesh.py" "$id" "$WORK" --res "$RES" --cloth-res "$CRES"
	step_on assemble && run "$id assemble" "$BLENDER" -b --factory-startup -t 2 --python-exit-code 1 --python "$CH/bl_build.py" -- "$WORK/$id"
	step_on textures && run "$id textures" "$PY" "$CH/wr_texture.py" "$id" "$WORK" "$CH/$id/textures"
	step_on anim && run "$id animate+export" "$BLENDER" -b --factory-startup -t 2 --python-exit-code 1 --python "$CH/bl_anim.py" -- \
		"$WORK/$id" "$CH/$id/textures" "$CH/$id/$id.blend" "$GA/$id/$id.glb" "$GA/$id/${id}_anim.json"
	step_on anim && run "$id palette textures" cp "$CH/$id/textures/${id}_cloth_mask.png" "$CH/$id/textures/${id}_cloth_detail.png" \
		"$CH/$id/textures/${id}_cloth_normal.png" "$GA/$id/"
	step_on anim && run "$id import sidecar" "$PY" "$CH/write_import_sidecar.py" "$GA/$id/${id}_anim.json" "$GA/$id/$id.glb.import"
	step_on anim && run "$id checks copy" cp "$WORK/$id/checks.json" "$EV/${id}_checks.json"
	step_on anim && run "$id blender reimport" "$BLENDER" -b --factory-startup -t 2 --python-exit-code 1 --python "$CH/bl_verify_glb.py" -- \
		"$GA/$id/$id.glb" "$EV/${id}_glbcheck.json"
	run "$id renders" "$BLENDER" -b "$CH/$id/$id.blend" -t 2 --gpu-backend vulkan --python-exit-code 1 --python "$CH/bl_render.py" -- \
		"$id" "$EV" "$PORTRAITS"
done

# ---- Godot 4.7 import check in a scratch project (never inside game/)
ALL=()
for id in nyx bruno vex hops scrap; do
	[ -f "$GA/$id/$id.glb" ] && ALL+=("$id")
done
rm -rf "$CHECK"
mkdir -p "$CHECK/chars"
cp "$CH/godot_check/project.godot.in" "$CHECK/project.godot"
cp "$CH/godot_check/check_chars.gd" "$CHECK/"
for id in "${ALL[@]}"; do
	mkdir -p "$CHECK/chars/$id"
	cp "$GA/$id/$id.glb" "$GA/$id/${id}_anim.json" "$GA/$id/$id.glb.import" "$GA/$id/${id}_cloth_mask.png" \
		"$GA/$id/${id}_cloth_detail.png" "$GA/$id/${id}_cloth_normal.png" "$CHECK/chars/$id/"
done
echo "---- [godot import] $GODOT --headless --path $CHECK --import" >>"$LOG"
timeout 1200 "$GODOT" --headless --path "$CHECK" --import >"$EV/godot_import.log" 2>&1
rc=$?
cat "$EV/godot_import.log" >>"$LOG"
echo "[godot import] exit=$rc" | tee -a "$LOG"
if [ $rc -ne 0 ] || grep -E "^ERROR|SCRIPT ERROR|Error importing" "$EV/godot_import.log" >/dev/null; then
	echo "FAILED: godot import (see $EV/godot_import.log)" | tee -a "$LOG"
	exit 1
fi
IDS=$(
	IFS=,
	echo "${ALL[*]}"
)
run "godot check" timeout 900 xvfb-run -a -s "-screen 0 1600x900x24" "$GODOT" --path "$CHECK" --resolution 1600x900 \
	--script res://check_chars.gd -- "$IDS" "$EV/godot_check.png" "$EV/godot_check.json"
run "report" "$PY" "$CH/report.py" "$WORK" "$EV" "$GA" "${ALL[@]}"
echo "==== build_characters.sh OK $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG"
exit 0
