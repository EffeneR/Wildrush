#!/bin/bash
# SessionStart hook: let the HyperFrames CLI (npx hyperframes render) use the
# chrome-headless-shell that Claude Code cloud containers ship under
# /opt/pw-browsers, instead of downloading its own copy every session.
# Local sessions are untouched; there `npx hyperframes browser ensure` applies.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ] || [ -z "${CLAUDE_ENV_FILE:-}" ]; then
  exit 0
fi

for shell in /opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell; do
  if [ -x "$shell" ]; then
    echo "export HYPERFRAMES_BROWSER_PATH=\"$shell\"" >> "$CLAUDE_ENV_FILE"
    break
  fi
done
