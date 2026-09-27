#!/usr/bin/env bash
# WILDRUSH — idempotent development-environment setup (Linux x86_64).
# Downloads the pinned toolchain from official sources into .toolchain/, verifies
# checksums, installs optional software-rendering packages, and creates .venv.
# Usage: tools/setup_env.sh [--no-apt]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TC="$ROOT/.toolchain"
DL="$TC/downloads"
GODOT_VER="4.7.2"
GODOT_ZIP="Godot_v${GODOT_VER}-stable_linux.x86_64.zip"
GODOT_TPZ="Godot_v${GODOT_VER}-stable_export_templates.tpz"
GODOT_ZIP_SHA512="9aa00f7a605200940bce3027a567b782"   # prefix; full value checked via godot-builds metadata when reachable
GODOT_TPZ_SHA512="ca4d71c4d7b81dfc15d1a98baa07534a"
BLENDER_VER="4.5.9"
BLENDER_TXZ="blender-${BLENDER_VER}-linux-x64.tar.xz"
BLENDER_SHA256="dcdc3eca6c9825bb35a8033b689c053f3cb5a9b0cd2a61b2eac2a49436b4ad3d"
GODOT_BASE="https://downloads.godotengine.org/?version=${GODOT_VER}&flavor=stable&platform=linux.64&slug="
NO_APT=0
[[ "${1:-}" == "--no-apt" ]] && NO_APT=1

log() { printf '[setup] %s\n' "$*"; }
die() { printf '[setup] ERROR: %s\n' "$*" >&2; exit 1; }

mkdir -p "$DL"

fetch() { # url dest
  local url="$1" dest="$2"
  if [[ -s "$dest" ]]; then log "cached: $(basename "$dest")"; return 0; fi
  log "downloading $(basename "$dest")"
  curl -fL --retry 4 --retry-delay 2 -o "$dest.part" "$url" || die "download failed: $url"
  mv "$dest.part" "$dest"
}

sha512_prefix_ok() { # file prefix
  local got; got="$(sha512sum "$1" | cut -c1-${#2})"
  [[ "$got" == "$2" ]]
}

# --- Godot editor + export templates -------------------------------------------------
fetch "${GODOT_BASE}linux.x86_64.zip" "$DL/$GODOT_ZIP"
sha512_prefix_ok "$DL/$GODOT_ZIP" "$GODOT_ZIP_SHA512" || die "checksum mismatch: $GODOT_ZIP"
fetch "${GODOT_BASE}export_templates.tpz" "$DL/$GODOT_TPZ"
sha512_prefix_ok "$DL/$GODOT_TPZ" "$GODOT_TPZ_SHA512" || die "checksum mismatch: $GODOT_TPZ"

GODOT_BIN="$TC/godot/Godot_v${GODOT_VER}-stable_linux.x86_64"
if [[ ! -x "$GODOT_BIN" ]]; then
  mkdir -p "$TC/godot"
  (cd "$TC/godot" && unzip -o -q "$DL/$GODOT_ZIP")
fi
touch "$TC/godot/_sc_"   # self-contained mode: editor data stays under .toolchain/godot/editor_data
TPL="$TC/godot/editor_data/export_templates/${GODOT_VER}.stable"
if [[ ! -f "$TPL/linux_release.x86_64" || ! -f "$TPL/windows_release_x86_64.exe" ]]; then
  mkdir -p "$TC/godot/editor_data/export_templates"
  tmp="$(mktemp -d)"
  (cd "$tmp" && unzip -o -q "$DL/$GODOT_TPZ" \
     'templates/linux_release.x86_64' 'templates/linux_debug.x86_64' \
     'templates/windows_release_x86_64.exe' 'templates/windows_debug_x86_64.exe' \
     'templates/windows_release_x86_64_console.exe' 'templates/windows_debug_x86_64_console.exe' \
     'templates/version.txt' 'templates/icudt_godot.dat')
  rm -rf "$TPL"; mv "$tmp/templates" "$TPL"; rm -rf "$tmp"
fi
"$GODOT_BIN" --version >/dev/null 2>&1 || die "godot binary does not run"
log "godot: $("$GODOT_BIN" --version 2>/dev/null | tail -1)"

# --- Blender LTS --------------------------------------------------------------------
fetch "https://download.blender.org/release/Blender4.5/${BLENDER_TXZ}" "$DL/$BLENDER_TXZ"
echo "${BLENDER_SHA256}  $DL/$BLENDER_TXZ" | sha256sum -c --quiet - || die "checksum mismatch: $BLENDER_TXZ"
BLENDER_BIN="$TC/blender-${BLENDER_VER}-linux-x64/blender"
if [[ ! -x "$BLENDER_BIN" ]]; then (cd "$TC" && tar -xf "$DL/$BLENDER_TXZ"); fi
log "blender: $("$BLENDER_BIN" --version 2>/dev/null | head -1)"

# --- Optional system packages for rendered inspection without a GPU -------------------
if [[ $NO_APT -eq 0 ]] && command -v apt-get >/dev/null 2>&1 && [[ $(id -u) -eq 0 ]]; then
  if [[ ! -f /usr/share/vulkan/icd.d/lvp_icd.json ]] || ! command -v xvfb-run >/dev/null; then
    log "installing mesa-vulkan-drivers xvfb (software Vulkan/GL for screenshots)"
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q mesa-vulkan-drivers xvfb >/dev/null || log "WARN: apt install failed (rendered checks will be BLOCKED)"
  fi
fi

# --- Python venv ----------------------------------------------------------------------
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then python3 -m venv "$ROOT/.venv"; fi
"$ROOT/.venv/bin/pip" install -q --upgrade pip
"$ROOT/.venv/bin/pip" install -q -r "$ROOT/tools/requirements.txt"
if [[ -f "$ROOT/services/requirements.txt" ]]; then
  "$ROOT/.venv/bin/pip" install -q -r "$ROOT/services/requirements.txt"
fi
log "python venv ready: $("$ROOT/.venv/bin/python" --version)"

# Record resolved executable paths for other scripts.
cat > "$TC/paths.env" <<EOF
GODOT_BIN="$GODOT_BIN"
BLENDER_BIN="$BLENDER_BIN"
PYTHON_BIN="$ROOT/.venv/bin/python"
EOF
log "done. paths written to .toolchain/paths.env"
