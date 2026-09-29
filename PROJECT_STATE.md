# PROJECT_STATE

Last updated: 2026-09-29 (session 2). Branch `claude/blissful-hypatia-rujnlz` (pushed).
Gate-by-gate evidence: `docs/ACCEPTANCE_MATRIX.md`. Decisions: `docs/DECISIONS.md` (D-001…D-022).

## Environment (this container)
Ubuntu 24.04, 4 threads, 15 GB RAM, no GPU (lavapipe/llvmpipe + Xvfb), PostgreSQL 16
native, Docker CLI without daemon. Toolchain under `.toolchain/` via `tools/setup_env.sh`
(Godot 4.7.2-stable + export templates, Blender 4.5.9 LTS, Python venv `.venv`).
After adding `class_name` scripts or assets: `$GODOT_BIN --headless --path game --import`.

## Status: all release gates executed
| Gate | Result | Evidence |
|---|---|---|
| G1 import/parse/export | PASS | 79/79 unit tests (4294 checks), 3 exports, 0 engine errors in flows |
| G2 five rigged fighters | PASS | `evidence/characters/` (all five, in-engine lineup) |
| G3 per-skill behaviour | PASS | `game/tests/unit/test_skills_*.gd` |
| G4 match rules | PASS | `test_match_rules.gd` + complete matches |
| G5 navigation/fairness | PASS | `evidence/arena/travel_times.json` |
| G6 ten client processes | PASS | `evidence/net/ten_clients/result.json` |
| G7 latency/loss matrix | PASS | `evidence/net/netsim_summary/result.json` (localhost proxy) |
| G8 security negatives | PASS | `evidence/security/game_server/result.json`, service pytest (156) |
| G9 E2E ranked, 10 identities | PASS | `evidence/e2e/ranked/result.json`, `evidence/online/online_client_check.json` |
| G10 offline match + 21-min soak | PASS | `evidence/flow/offline_flow.json`, `evidence/soak/server_clients/result.json` |
| G11 UI screenshots/interaction | PASS | `evidence/ui/report.json` (96 shots), `evidence/match/` |
| G12 fresh exported builds | PASS; Windows run BLOCKED | `evidence/export/verify_export.json` |

Performance (software renderer only): `evidence/perf/summary.json`.

## Known limitations / follow-ups
- Windows client exported (`builds/windows_client/WILDRUSH.exe`, PE-checked) but not run: no Windows machine.
- Docker Compose deployment written and statically validated, not executed: no Docker daemon.
- Performance numbers are llvmpipe CPU-rendering numbers; GPU performance unmeasured.
- Character look nits reported by the pipeline (no failing check): Scrap's grey fur renders pale,
  Bruno's idle guard hides his face in the front view, dark fur-clump streaks on limbs,
  slightly knock-kneed crouch from the front.
- First entry into an unseen district stalls on shader compilation under llvmpipe; on GPUs
  Godot's ubershader path should hide most of this, but it has not been measured here.
- No public deployment has been performed; services bind to loopback by default.

## How to resume
`tools/verify.sh` (core gates, ~45 min) or `tools/verify.sh --full` (adds the soak). Asset
pipelines: `tools/build_characters.sh <id>`, `tools/build_arena_art.sh`, `tools/audio/`.
