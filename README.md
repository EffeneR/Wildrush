# WILDRUSH

Five animals. One pack. A 5v5 third-person, skill-based animal arena fighter:
Nyx, Bruno, Vex, Hops and Scrap fight for **Turf Shift** control of the Briarport waterfront.
Godot 4.7 (typed GDScript, Jolt physics), Blender-built characters and arena, a 60 Hz
authoritative ENet server with client prediction, and a self-hostable FastAPI + PostgreSQL
control service (accounts, parties, casual/ranked queues, allocation, tickets, results,
ratings, history, cosmetics).

* Controls and fighter kits: [`docs/CONTROLS.md`](docs/CONTROLS.md)
* Troubleshooting: [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md)
* Hosting / deployment (native + Docker Compose, TLS, UDP ports): [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
* Licences: [`docs/LICENSE_MANIFEST.md`](docs/LICENSE_MANIFEST.md)
* Current status and evidence: [`PROJECT_STATE.md`](PROJECT_STATE.md), [`docs/ACCEPTANCE_MATRIX.md`](docs/ACCEPTANCE_MATRIX.md)
* Design decisions: [`docs/DECISIONS.md`](docs/DECISIONS.md) · full brief: [`docs/MASTER_SPEC.md`](docs/MASTER_SPEC.md)

## Play
Exported builds (`tools/verify_export.sh` or the commands below) land in `builds/`:
* **Windows client** `builds/windows_client/WILDRUSH.exe` — Play Offline (5v5 vs bots, three
  difficulties), Training, Play Online, Collection, History & Replays, Settings.
* **Linux dedicated server** `builds/linux_server/wildrush_server.x86_64`

Host a private match on your LAN (clients use *Play Online → Direct connect*):
```bash
./wildrush_server.x86_64 --headless -- --port 24610 --mode private --allow-bots \
    [--private-password-file pw.txt] [--observer-key KEY] [--autostart 2]
```
Online queues need the control service (`services/README.md`); the client only talks HTTPS
to it (plain HTTP is allowed for loopback testing only).

## Build from source
```bash
tools/setup_env.sh                                   # pinned Godot 4.7.2 + templates, Blender 4.5.9 LTS, Python venv
source .toolchain/paths.env
$GODOT_BIN --headless --path game --import           # import assets, refresh class cache
$GODOT_BIN --headless --path game --export-release "Windows Client" ../builds/windows_client/WILDRUSH.exe
$GODOT_BIN --headless --path game --export-release "Linux Server" ../builds/linux_server/wildrush_server.x86_64
```
Asset pipelines (reproducible, script-driven): characters `tools/build_characters.sh <id>`
(`blender/characters/`), arena `tools/build_arena_art.sh` (`blender/arena/`), audio
`tools/audio/` (`tools/audio/check_audio.py`), arena layout `tools/arena/gen_layout.py`.

## Verify
| Check | Command |
|---|---|
| Unit + behaviour tests (sim, rules, 15 skills, protocol, roster) | `$GODOT_BIN --headless --fixed-fps 60 --path game res://tests/test_runner.tscn` |
| Arena navigation / fairness | `$GODOT_BIN --headless --path game res://tools/arena_analysis.tscn` |
| 10 real client processes vs dedicated server | `.venv/bin/python tests/integration/test_ten_clients.py` |
| Latency/loss matrix (localhost UDP proxy, not WAN) | `.venv/bin/python tests/integration/test_netsim_matrix.py` |
| Security negatives (game server) | `.venv/bin/python tests/integration/test_security.py` |
| Service tests (incl. signatures, result replay) | `services/scripts/run_tests.sh` |
| E2E ranked with 10 identities (service + allocator + exported server) | `.venv/bin/python tests/integration/test_e2e_ranked.py` |
| 20-min soak | `.venv/bin/python tests/integration/test_soak.py` |
| UI screenshots (Xvfb) | `xvfb-run -a -s "-screen 0 3440x1440x24" $GODOT_BIN --path game res://tools/ui_screenshots.tscn` |
| Screen flow boot → menu → match → results → menu | `$GODOT_BIN --headless --fixed-fps 60 --path game res://tools/flow_test.tscn -- --autopilot-self` |
| Exported builds from a fresh directory | `tools/verify_export.sh` |
| Everything | `tools/verify.sh` |

Evidence from each check is written under `evidence/`.

## Repository layout
```
game/            Godot project (src/sim, src/net, src/present, src/ui, src/bots, data/, assets/, tests/)
services/        control service (FastAPI), allocator agent, migrations, deployment config
blender/         character + arena generation scripts and .blend sources
tools/           setup, verification, audio/arena generators, netsim proxy
tests/           multi-process integration tests (Python harness)
docs/            spec, decisions, contracts, deployment, controls, licences
evidence/        outputs of executed checks (screenshots, logs, JSON results)
references/      owner-supplied reference images (git-ignored, never distributed)
```

## Honest limitations of this environment
No Windows machine (the Windows client is exported and format-checked, not run), no GPU
(rendering checks use llvmpipe/lavapipe, so frame-time numbers are software-rendering
numbers), and no Docker daemon (Compose files are written and statically checked, not run).
Network tests run over localhost with a UDP impairment proxy; they are not WAN measurements.
No public deployment has been performed.
