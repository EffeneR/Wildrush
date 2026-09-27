# WILDRUSH — agent entry point

* Full build directive (highest priority): `docs/MASTER_SPEC.md`
* Binding implementation decisions: `docs/DECISIONS.md`
* Current progress, evidence, failures, next exact action: `PROJECT_STATE.md`
* Acceptance status per requirement/gate: `docs/ACCEPTANCE_MATRIX.md`
* References: `docs/REFERENCE_MANIFEST.md`, `docs/REFERENCE_AUDIT.md` (images in `references/`, git-ignored)
* Toolchain: `toolchain.lock.json`; bootstrap with `tools/setup_env.sh`; resolved binaries in `.toolchain/paths.env`

Rules: never claim success without executed evidence; failing/unrunnable checks are
FAIL/BLOCKED, not PASS. Update `PROJECT_STATE.md` after each major step. Godot project
entry is `game/project.godot`. Commit small checkpoints on the session branch.
