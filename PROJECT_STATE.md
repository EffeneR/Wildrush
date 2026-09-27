# PROJECT_STATE

Last updated: 2026-09-27 (session 1)

## Environment (this container)
Ubuntu 24.04, 4 threads, 15 GB RAM, no GPU (lavapipe/llvmpipe + Xvfb), PostgreSQL 16
native, Docker CLI without daemon. Toolchain installed under `.toolchain/` via
`tools/setup_env.sh` (Godot 4.7.2-stable, Blender 4.5.9 LTS, Python venv `.venv`).

## Completed
- Workspace inspected (repo was empty; branch `claude/blissful-hypatia-rujnlz`).
- All 16 references extracted to `references/` (git-ignored) and visually inspected.
- Toolchain downloaded from official sources, checksums verified, pinned in
  `toolchain.lock.json`; setup script idempotent (re-run exit 0).
- Verified: Godot Forward+ renders via lavapipe under Xvfb; Blender Eevee + Cycles render
  headless; Blender glTF export works.
- Docs: `docs/MASTER_SPEC.md`, `docs/DECISIONS.md`, `docs/REFERENCE_MANIFEST.md`,
  `docs/REFERENCE_AUDIT.md`, `docs/ACCEPTANCE_MATRIX.md`, `docs/API_CONTRACT.md`, `CLAUDE.md`.

## In progress
- Godot project skeleton + tuning data + core simulation.

## Workstreams / owners
| Stream | Owner | Interface doc |
|--------|-------|---------------|
| Game code (sim, net, UI, integration) | lead | DECISIONS.md |
| Control service | services agent | API_CONTRACT.md |

## Known blockers / deviations
- No Windows machine: Windows client can be exported but not run-tested natively here.
- No Docker daemon: `docker compose` deployment can be written but not executed here.
- No GPU: performance numbers from this container are software-rendering numbers.

## Next exact action
Create `game/project.godot`, test runner, tuning JSON, core sim classes.
