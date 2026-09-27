#!/usr/bin/env bash
# WILDRUSH audio build: synthesize every cue in docs/AUDIO_CONTRACT.md, write
# game/assets/audio/audio_manifest.json, validate (check_audio.py) and render evidence
# spectrograms. Idempotent and deterministic (fixed seeds, fixed Ogg serials): re-running
# produces byte-identical outputs. Exits nonzero if any step fails.
#
# Usage: tools/audio/build_audio.sh [--check-only]
#   env PYTHON=/path/to/python to override the interpreter (default: <repo>/.venv/bin/python)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/../.." && pwd)"
PY="${PYTHON:-${ROOT}/.venv/bin/python}"
EVID="${ROOT}/evidence/audio"
LOG="${EVID}/build_audio.log"

if [[ ! -x "${PY}" ]]; then
  echo "build_audio: python interpreter not found: ${PY} (run tools/setup_env.sh)" >&2
  exit 2
fi
mkdir -p "${EVID}"

# Keep the build light on shared machines: single-threaded math, lowered priority.
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONHASHSEED=0
NICE=(nice -n 10)

run() {
  echo "==> $*"
  "${NICE[@]}" "$@"
}

{
  echo "WILDRUSH audio build  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "python: ${PY} ($("${PY}" -c 'import sys,numpy,scipy,soundfile;print(sys.version.split()[0],"numpy",numpy.__version__,"scipy",scipy.__version__,"soundfile",soundfile.__version__,"libsndfile",soundfile.__libsndfile_version__)'))"
} | tee "${LOG}"

status=0
if [[ "${1:-}" != "--check-only" ]]; then
  run "${PY}" "${HERE}/build.py" 2>&1 | tee -a "${LOG}" || status=$?
  if [[ ${status} -ne 0 ]]; then
    echo "build_audio: synthesis FAILED (exit ${status}); see ${LOG}" | tee -a "${LOG}" >&2
    exit "${status}"
  fi
fi

run "${PY}" "${HERE}/check_audio.py" --out "${EVID}/check_audio.txt" --json "${EVID}/check_audio.json" 2>&1 \
  | tee -a "${LOG}" || status=$?
if [[ ${status} -ne 0 ]]; then
  echo "build_audio: check_audio FAILED (exit ${status}); see ${EVID}/check_audio.txt" | tee -a "${LOG}" >&2
  exit "${status}"
fi

run "${PY}" "${HERE}/render_spectrograms.py" 2>&1 | tee -a "${LOG}" || status=$?
if [[ ${status} -ne 0 ]]; then
  echo "build_audio: spectrogram rendering FAILED (exit ${status})" | tee -a "${LOG}" >&2
  exit "${status}"
fi

echo "build_audio: OK" | tee -a "${LOG}"
