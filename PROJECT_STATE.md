# PROJECT_STATE

Last updated: 2026-09-29 (session 2). Branch `claude/blissful-hypatia-rujnlz` (pushed).

## Environment (this container)
Ubuntu 24.04, 4 threads, 15 GB RAM, no GPU (lavapipe/llvmpipe + Xvfb), PostgreSQL 16
native, Docker CLI without daemon. Toolchain under `.toolchain/` via `tools/setup_env.sh`
(Godot 4.7.2-stable + export templates, Blender 4.5.9 LTS, Python venv `.venv`).
After adding new `class_name` scripts or assets run `$GODOT_BIN --headless --path game --import`
(refreshes the global class cache; a stale cache shows up as "Could not find type X").

## Done (with executed evidence)
- Core sim (60 Hz authoritative MatchSim, Turf Shift rules, combat, 15 skills + 5 passives):
  unit suite `res://tests/test_runner.tscn` → 73 passed, 0 failed (2026-09-29).
- Arena: layout JSON + collision + navmesh + analysis (`evidence/arena/`); Blender art chunks
  `game/assets/arena/briarport_*.glb` + `arena_art.json` (326k tris, 36 materials) loaded by
  `ArenaView`; Blender verify vs layout PASS (agent report, `blender/arena/PIPELINE_STATE.md`).
- Characters: Nyx and Bruno complete (GLB + anim json + cloth masks, alignment ≤ 0.078 m,
  Godot scratch import clean; `evidence/characters/`). Vex/Hops/Scrap building (character agent).
- Networking: 10-client test previously passed; latency/loss matrix 0/50/100/150 ms with
  0–3 % loss: all 4 conditions PASS (`evidence/net/netsim_summary/result.json`, 2026-09-28).
  Admission gating (no inputs before server welcome), ENet peer timeouts 12 s/30 s,
  public scoreboard broadcast every 2 s.
- Presentation: `scenes/match.tscn` (offline/training/online/replay) with FighterView (GLB or
  procedural stand-in), CameraRig, PlayerInput, ArenaView, VfxDirector, AudioDirector, MatchHud,
  PauseMenu. Evidence: `evidence/match/*.png` (offline, training with Nyx GLB, replay).
  Headless full offline match: 82–70, awards + replay written (2 min wall time).
- UI screens (UI agent): splash, main menu + sub-screens, settings overlay, results, online
  lobby, Online autoload; `game/tools/ui_screenshots.tscn` → `evidence/ui/` (96 shots; lobby
  overflow fixed and re-shot 0 failures).
- Services (FastAPI/PostgreSQL) complete per `services/README.md`, pytest evidence in
  `evidence/services/`.

## In progress
- `game/tools/flow_test.tscn` end-to-end: boot → menu → offline start → match → results → menu.
- Export presets written (`game/export_presets.cfg`: Windows client, Linux server, Linux client
  for local verification) — exports not yet built.

## Next exact actions
1. Finish flow test; build exports; run exported Linux server + client from another dir (G12).
2. Re-run ten-client test; write security integration test (G8) and E2E ranked test with 10
   identities through services + allocator (G9); 20-min soak (G10); perf capture (F-PERF).
3. Integrate Vex/Hops/Scrap GLBs as they land (`--import`, capture in training).
4. `tools/verify.sh`, README/controls/troubleshooting/license manifest, acceptance matrix.

## Workstreams / owners
| Stream | Owner | Interface doc |
|--------|-------|---------------|
| Game code (sim, net, presentation, integration) | lead | DECISIONS.md |
| UI screens + Online autoload | UI agent (stopped; lead maintains) | docs/UI_CONTRACT.md |
| Characters | character agent | docs/CHARACTER_CONTRACT.md, blender/characters/PIPELINE_STATE.md |
| Arena art | environment agent (done) | docs/ENVIRONMENT_CONTRACT.md, blender/arena/PIPELINE_STATE.md |
| Control service | services agent (done) | docs/API_CONTRACT.md, services/CONTRACT_NOTES.md |

## Known blockers / deviations
- No Windows machine: Windows client is exported but cannot be run-tested here.
- No Docker daemon: `docker compose` deployment is written but not executed here.
- No GPU: performance numbers are software-rendering (llvmpipe) numbers.
- Session usage limits interrupted helper agents repeatedly; state files let them resume.
