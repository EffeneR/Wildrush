# PROJECT_STATE

Last updated: 2026-09-29 (session 2, final). Branch `claude/blissful-hypatia-rujnlz` (pushed).
Gate-by-gate evidence: `docs/ACCEPTANCE_MATRIX.md`. Decisions: `docs/DECISIONS.md` (D-001…D-023).

## Environment (this container)
Ubuntu 24.04, 4 threads, 15 GB RAM, no GPU (lavapipe/llvmpipe + Xvfb), PostgreSQL 16
native, Docker CLI without daemon. Toolchain under `.toolchain/` via `tools/setup_env.sh`
(Godot 4.7.2-stable + export templates, Blender 4.5.9 LTS, Python venv `.venv`).
After adding `class_name` scripts or assets: `$GODOT_BIN --headless --path game --import`.

## Status: all release gates executed in one recorded run
`tools/verify.sh --full` at commit `6354d25` (clean tree) → `evidence/verify/latest.json`:
15 steps — 13 PASS, 2 BLOCKED (Windows client run: no Windows machine; Docker Compose up:
no Docker daemon), 0 FAIL; script exit code 0. Per-step logs: `evidence/verify/logs/`.

| Gate | Result | Evidence |
|---|---|---|
| G1 import/parse/export | PASS | clean import, 79/79 unit tests (4294 checks), 3 exports + Windows console wrapper |
| G2 five rigged fighters | PASS | `evidence/characters/report.json` (asset pipeline run), in-engine lineup |
| G3 per-skill behaviour | PASS | `game/tests/unit/test_skills_*.gd`, `test_combat.gd` |
| G4 match rules | PASS | `test_match_rules.gd` + complete matches (bot, offline, exported, ranked) |
| G5 navigation/fairness | PASS | `evidence/arena/travel_times.json` (worst team diff 1.31 %, 0/252 unreachable) |
| G6 ten client processes | PASS | `evidence/net/ten_clients/result.json` |
| G7 latency/loss matrix | PASS | `evidence/net/netsim_summary/result.json` (localhost proxy, not WAN) |
| G8 security negatives | PASS | `evidence/security/game_server/result.json` (15/15), services pytest 156 passed |
| G9 E2E ranked, 10 identities | PASS | `evidence/e2e/ranked/result.json` (match `ba4262e2`), `evidence/online/online_client_check.json` (21/21) |
| G10 offline match + 21-min soak | PASS | `evidence/flow/offline_flow.json`, `evidence/export/flow.json`, `evidence/soak/server_clients/result.json` |
| G11 UI screenshots/interaction | PASS | `evidence/ui/report.json` (96 shots, 9 interactions), `evidence/match/` |
| G12 fresh exported builds | PASS; Windows run BLOCKED | `evidence/export/verify_export.json` |

Performance (software renderer only): `evidence/perf/summary.json`.

## Corrections made in the final verification pass
- `tools/verify.sh` had never been run end to end; its first full run showed the `unit_tests`
  step misreporting FAIL although 79/79 passed (`grep -q` pipe under `pipefail`; the same pattern
  could have passed an import containing ERRORs). Fixed (D-023); the full run above is after the fix.
- The acceptance matrix named 8 checks/paths that do not exist (e.g. `test_arena_nav.gd`,
  `tools/soak.sh`); the Check column now names the checks that actually run. Security count
  corrected to 15/15 (was written as 16/16); unsupported numbers replaced by traceable ones.
- `evidence/flow/offline_flow.json` was stale (recorded `ok: false` from before the GLB-load
  fix) while cited as PASS evidence; regenerated from the project: ok, 0 engine errors.
- The Windows release export did not contain `WILDRUSH.console.exe`, which the troubleshooting
  guide tells players to run; the preset now exports it (checked by `tools/verify_export.sh`).
- Evidence folders kept files from earlier runs next to the latest result (e.g. client logs of
  three E2E runs, replays of three soaks). Files from earlier runs were removed so each folder
  matches the recorded run, and after that run the harnesses (`tests/integration/harness.py`,
  `test_e2e_ranked.py`) were changed to empty their evidence folder at the start of a run.
- Re-run after the full run: `tools/setup_env.sh` (exit 0), `services/scripts/smoke_dev_stack.sh`
  (PASS), `services/scripts/check_deploy_config.sh` with the official Caddy 2.11.4 (all PASS).

## Known limitations / follow-ups
- Windows client exported (`builds/windows_client/WILDRUSH.exe` + `WILDRUSH.console.exe`,
  PE-checked) but not run: no Windows machine.
- Docker Compose deployment written and statically validated, not executed: no Docker daemon.
- Performance numbers are llvmpipe CPU-rendering numbers; GPU performance unmeasured.
- Character look nits reported by the pipeline (no failing check): Scrap's grey fur renders pale,
  Bruno's idle guard hides his face in the front view, dark fur-clump streaks on limbs,
  slightly knock-kneed crouch from the front.
- First entry into an unseen district stalls on shader compilation under llvmpipe; on GPUs
  Godot's ubershader path should hide most of this, but it has not been measured here.
- Godot prints "116 ObjectDB instances were leaked at exit" after the unit tests (37 after the
  online check): a fixed-size set of RefCounted objects alive at shutdown, not growing per
  match (D-023). Not yet traced object by object.
- Unreproduced: in an ad-hoc experiment running two complete bot matches in one test process,
  the second match's test failed once (1 of 4 two-match runs; the 3 re-runs passed with
  identical deterministic results; the failure text was not captured). The 10-bot unit test and
  the soak's back-to-back server matches pass. If it recurs, the runner prints `FAIL …` followed
  by the indented reasons (assertion or runtime error).
- No public deployment has been performed; services bind to loopback by default.

## How to resume
`tools/verify.sh` (core gates, ~30 min here) or `tools/verify.sh --full` (adds the 21-min soak).
Asset pipelines: `tools/build_characters.sh <id>`, `tools/build_arena_art.sh`, `tools/audio/`.
