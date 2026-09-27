# Acceptance Matrix

Status values: `NOT STARTED` · `IN PROGRESS` · `PASS` (verified by the named check, evidence
linked) · `FAIL` (check ran and failed) · `BLOCKED` (cannot run here; reason given) ·
`NOT RUN`. A row is PASS only with executed evidence. Machine-readable results of the
latest full run: `evidence/verify/latest.json`.

## Release gates (spec §14)

| Gate | Requirement | Check (command / test) | Status | Evidence |
|------|-------------|------------------------|--------|----------|
| G1 | Clean import/export, no parse errors / missing files / unexplained runtime errors | `tools/verify.sh` → `import`, `script_check`, `export_*` steps | NOT STARTED | |
| G2 | Five distinct rigged models, valid materials, all animations, transitions, 15 non-placeholder skills | `test_assets_characters.gd`, `tools/check_glb.py` | NOT STARTED | |
| G3 | Per-skill behaviour: startup, cooldown, stamina, hit validity, miss recovery, wall, interruption, CR | `test_skills_*.gd` | NOT STARTED | |
| G4 | Match rules: one active zone, empty/contested, scoring, rotation/reveal, overtime, respawn, one-time victory/result | `test_match_rules.gd`, `test_match_flow.gd` | NOT STARTED | |
| G5 | Map navigation both teams → all objectives, no special skills, travel-time comparison, no stuck loops, no capture through floors | `test_arena_nav.gd`, `evidence/arena/travel_times.json` | NOT STARTED | |
| G6 | Real dedicated server + multiple client processes, ten-client protocol test | `tests/integration/test_ten_clients.py` | NOT STARTED | |
| G7 | Latency/loss sim 0/50/100/150 ms RTT, ≤3% loss: prediction, reconciliation, dup hits, guard timing, cooldowns, reconnect (localhost sim ≠ WAN) | `tests/integration/test_netsim_matrix.py` | NOT STARTED | |
| G8 | Security negatives: forged damage/score, wrong ownership, reused tickets, invalid payloads, selection races, result replay, unauthorized spectator | `tests/integration/test_security.py`, `services/tests/test_security.py` | NOT STARTED | |
| G9 | E2E service flow account→party/queue→allocation→server join→result→history/rating; ranked with 10 real client identities | `tests/integration/test_e2e_ranked.py` | NOT STARTED | |
| G10 | Offline complete match + bot matches through all three zones + ≥20-min soak at normal speed | `tests/integration/test_offline_match.py`, `tools/soak.sh` | NOT STARTED | |
| G11 | Real UI interaction + screenshot checks (menus, char select, gameplay, scoreboard, settings, respawn, results, replay) | `tools/ui_screenshots.sh`, `evidence/screens/` | NOT STARTED | |
| G12 | Fresh exported build launched outside editor from another working dir; assets, save paths, controls, online/offline, shutdown | `tools/verify_export.sh` | NOT STARTED | |

## Feature requirements

| ID | Spec | Requirement | Status | Evidence |
|----|------|-------------|--------|----------|
| F-TOOL | §1 | Toolchain pinned (`toolchain.lock.json`), setup script idempotent | PASS | `tools/setup_env.sh` re-run exit 0 (2026-09-27) |
| F-REF | §2 | 16 references inspected, manifest + audit | PASS | `docs/REFERENCE_MANIFEST.md`, `docs/REFERENCE_AUDIT.md` |
| F-ROSTER | §3 | 5 fighters, unique species per team, server-controlled slots, swap before lock | NOT STARTED | |
| F-MODES | §3 | Offline, training, private, casual, ranked (10 humans, no bots) | NOT STARTED | |
| F-RULES | §4 | Turf Shift rules data-driven + tests | NOT STARTED | |
| F-LIFE | §4 | Reconnect, abandonment, AFK, rematch, return-to-lobby | NOT STARTED | |
| F-MOVE | §5 | CharacterBody3D 60 Hz controller, accel/decel, snapping, slopes, steps, falls | NOT STARTED | |
| F-CTRL | §5 | Default bindings, remapping, controller mapping, deadzones | NOT STARTED | |
| F-CAM | §5 | Camera framing, retraction, FOV range, no lock/homing | NOT STARTED | |
| F-COMBAT | §5 | States, attack data, swept hits, walls, guard, dodge, stamina, CR, no FF | NOT STARTED | |
| F-NYX | §6 | Perch, Pounce, Crosscut, Slip | NOT STARTED | |
| F-BRUNO | §6 | Grounded, Shoulder Rush, Warning Bark, Stand Firm | NOT STARTED | |
| F-VEX | §6 | Light Steps, False Start, Sidewinder, Tail Sweep | NOT STARTED | |
| F-HOPS | §6 | Lightfoot, Bound, Double Kick, Dropkick | NOT STARTED | |
| F-SCRAP | §6 | Quick Recovery, Catch & Turn, Leg Sweep, Turnabout | NOT STARTED | |
| F-ARENA | §7 | Briarport integrated arena, footprint, zones, spawns, routes, overhead render | NOT STARTED | |
| F-ART-CHAR | §8 | Blender sources, rigs, clips, GLBs, comparisons Blender vs Godot | NOT STARTED | |
| F-ART-ENV | §8 | Modular env kit, collisions, LODs, materials | NOT STARTED | |
| F-NET | §9 | Authoritative ENet server, prediction, reconciliation, interpolation, lag comp, security | NOT STARTED | |
| F-SVC | §9 | Accounts, sessions, profiles, parties, servers, queues, allocation, tickets, results, ratings, history, cosmetics | NOT STARTED | |
| F-DEPLOY | §9 | Native scripts, Docker Compose, .env.example, UDP port docs | NOT STARTED | |
| F-BOTS | §10 | Server-side fair bots, difficulty, perception, stuck recovery | NOT STARTED | |
| F-TRAIN | §10 | Training sandbox features | NOT STARTED | |
| F-LOBBY | §10 | Private lobby admin, team assignment, bots, ready, start, spectate, rematch | NOT STARTED | |
| F-REPLAY | §10 | Recorder + replay list/viewer (pause, seek, speed, follow, free cam) | NOT STARTED | |
| F-UI | §11 | All listed screens implemented with real actions | NOT STARTED | |
| F-HUD | §11 | HUD elements incl. minimap honesty, territory states | NOT STARTED | |
| F-SET | §11 | Settings list complete, saved/restored | NOT STARTED | |
| F-PROG | §11 | Profile, palettes, badges, mastery; offline vs online separation | NOT STARTED | |
| F-AUDIO | §12 | SFX set, positional, buses, voice limiting, ambience/music | NOT STARTED | |
| F-VFX | §12 | Hit/guard/break/parry/knockback VFX, pooled, dedupe | NOT STARTED | |
| F-PERF | §13 | Profiling 10 fighters; measured numbers recorded honestly | NOT STARTED | |
| F-SCRIPTS | §13 | Idempotent scripts: setup, assets, import, test, services, server, client, export | NOT STARTED | |
| F-DOCS | §15 | README, controls guide, troubleshooting, license manifest, deployment docs | NOT STARTED | |
