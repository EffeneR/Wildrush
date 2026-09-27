#!/usr/bin/env bash
# Run the services test suite against a REAL throw-away PostgreSQL 16 cluster (started by the
# session fixture in tests/conftest.py; set WR_TEST_DATABASE_URL to use an existing database).
# The raw pytest output is saved to evidence/services/pytest_latest.txt.
# Exit code = pytest's exit code (nonzero on any failure; 124 on timeout).
#   services/scripts/run_tests.sh [extra pytest args, e.g. -k ranked or -m "not live"]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICES_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$SERVICES_DIR/.." && pwd)"
PY="${WR_PYTHON:-$ROOT_DIR/.venv/bin/python}"
PG_BIN="${WR_PG_BIN:-/usr/lib/postgresql/16/bin}"
EVIDENCE_DIR="$ROOT_DIR/evidence/services"
OUT="$EVIDENCE_DIR/pytest_latest.txt"

[[ -x "$PY" ]] || { echo "python not found at $PY (run tools/setup_env.sh)" >&2; exit 2; }
mkdir -p "$EVIDENCE_DIR"
cd "$SERVICES_DIR"

{
  echo "# WILDRUSH services test run"
  echo "# date_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# host: $(uname -srm)"
  echo "# python: $("$PY" --version 2>&1)"
  echo "# postgresql: $("$PG_BIN/postgres" --version 2>/dev/null || echo 'not found (WR_TEST_DATABASE_URL?)')"
  echo "# cwd: $SERVICES_DIR"
  echo "# command: $PY -m pytest -v -p no:cacheprovider $*"
} > "$OUT"

set +e
timeout "${WR_TEST_TIMEOUT_S:-1800}" "$PY" -m pytest -v -p no:cacheprovider "$@" 2>&1 | tee -a "$OUT"
rc=${PIPESTATUS[0]}
set -e
echo "# exit_code: $rc" >> "$OUT"
echo "[run_tests] raw output saved to $OUT (exit code $rc)"
exit "$rc"
