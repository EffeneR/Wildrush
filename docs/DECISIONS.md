# WILDRUSH — Canonical Decisions

Bounded implementation decisions that interpret `docs/MASTER_SPEC.md`. Each entry is
binding for all modules until explicitly superseded here (append a new dated entry;
never silently edit history). IDs are referenced from code comments and tests.

---

## D-001 Toolchain (2026-09-27)
* Godot **4.7.2-stable** standard build (no .NET), typed GDScript only. Official
  archives verified against `godotengine/godot-builds/releases/godot-4.7.2-stable.json`.
  Self-contained editor mode under `.toolchain/godot/` so export templates are project-local.
* Blender **4.5.9 LTS** (supported until mid-2027). Python/background execution only.
  Bundled glTF 2.0 exporter.
* Python 3.11 venv at `.venv` for services and tooling. Exact pins in
  `services/requirements.txt`, `tools/requirements.txt`.
* PostgreSQL 16 (native in dev/tests; `postgres:16` image in Docker Compose).
* Physics engine: **Jolt Physics** (Godot 4.7 built-in) for all 3D physics.
* Renderer: **Forward+** for the client (Vulkan / D3D12 on Windows). The project also
  runs on the Compatibility renderer (`--rendering-method gl_compatibility`) as a
  fallback for weak/old GPUs; visuals are authored to degrade gracefully.
* This container has no GPU: rendered inspection uses Mesa lavapipe (Vulkan) / llvmpipe
  (GL) under Xvfb. Frame-rate numbers measured here are software-rasterizer numbers and
  are reported as such — never as target-hardware performance.

## D-002 Repository layout
```
game/            Godot project (game/project.godot is the entry)
  src/core/        constants, fixed-step clock, ids, math, logging, config
  src/data/        typed Resource definitions + TuningDB (JSON -> Resources)
  src/sim/         authoritative simulation: fighters, actions, combat, hit detection
  src/match/       Turf Shift rules, territory occupancy, respawn, spawn protection
  src/arena/       arena layout loader, collision builder, nav, occupancy volumes
  src/net/         protocol codec, ENet server/client, prediction, interpolation, lagcomp
  src/bots/        bot perception, brain, navigation
  src/present/     visual fighters, animation driver, camera, VFX, audio, markers
  src/ui/          screens, HUD, theme, widgets
  src/online/      control-service HTTP client, session, party, queue
  src/persist/     settings, offline profile, mastery, match history
  src/replay/      recorder + player
  data/            tuning JSON (canonical combat/match numbers), arena layout JSON
  assets/          imported runtime products only (glb, textures, audio, fonts, ui)
  scenes/          top-level scenes
  tests/           GDScript test runner + suites
blender/         Blender generation scripts + saved .blend sources
services/        Python control service (FastAPI + PostgreSQL), allocator, migrations
tools/           setup, build, import, test, run, export, netsim, analysis scripts
tests/           cross-process integration tests (python drivers)
docs/            spec, decisions, audits, acceptance matrix, guides
evidence/        logs, screenshots, renders, machine-readable results
builds/          export outputs (git-ignored; reproducible via tools/export_release.sh)
references/      private user references (git-ignored; see docs/REFERENCE_MANIFEST.md)
```
UI never reaches into authoritative rule objects; it reads snapshots/view-models only.

## D-003 Coordinate conventions
* Godot: Y up, X east(+)/west(−), Z south(+)/north(−). Metres.
* Fighter yaw: `rotation.y = yaw`; forward = `-basis.z` = `(-sin yaw, 0, -cos yaw)`;
  right = `basis.x`. yaw 0 faces north (−Z).
* **Action-local space** used in tuning data (movement curves, hit trajectories):
  `x` = fighter right, `y` = up (0 = feet), `z` = fighter forward.
  World = `origin + right*x + up*y + forward*z`.
* Blender: characters are modelled facing −Y, Z up, 1 unit = 1 m, origin at the feet.
  Mapping action-local → Blender object space: `X = -x, Y = -z, Z = y`.
* glTF export converts Blender −Y-forward to glTF +Z-forward; the Godot `FighterView`
  rotates the imported model by π around Y so the model faces −Z like the sim.
* Animations are authored **in place** (no root motion). Action displacement is owned by
  the simulation (D-011); animation only illustrates it.

## D-004 Simulation clock and determinism
* Fixed 60 Hz authoritative tick (`physics_ticks_per_second = 60`, `max_physics_steps_per_frame = 8`).
* All timing data is expressed in seconds in JSON and converted to integer **ticks** at
  load (`round(sec * 60)`); every window compares integer ticks, never render frames.
* The same `MatchSim` code runs in: offline play (in-process, local "host"), the
  dedicated server, and headless tests. Scenarios use seeded `RandomNumberGenerator`s.
  Network play is **not** claimed to be deterministic; the server is authoritative.
* Rendering interpolates between the last two sim states (`Engine.get_physics_interpolation_fraction()`);
  interpolation never feeds back into the sim.

## D-005 Per-tick event order (authoritative; tested in `test_match_rules`)
1. Ingest inputs (one validated `InputFrame` per fighter; missing input ⇒ repeat last
   held buttons with press-edges cleared).
2. Advance match clock (only in LIVE / SUDDEN_DEATH).
3. Fighter pre-step: timers, stamina/health regen, cooldowns, control-effect timers.
4. Action state machines consume buffered presses (start/cancel/chain actions).
5. Movement integration (`move_and_slide`) incl. action movement curves; then soft
   fighter separation.
6. Hit detection: gather all hit candidates of this tick (swept volumes, lag-comp
   rewound hurtboxes, wall occlusion) → sort by (attacker entity id, action event id,
   target entity id) → resolve. Effects of the same tick apply simultaneously (trades
   are possible); parry/guard/dodge states are those at the start of this tick.
7. Knockouts: every fighter with health ≤ 0 is knocked out (after all hits of the tick),
   removed from occupancy immediately, respawn timer = 10 s.
8. Respawns whose timer elapsed: placed at a safe spawn point, resources restored.
9. Territory occupancy for the active zone (after 7 and 8).
10. Scoring (1 point per full second of continuous sole control; see D-006).
11. Victory / regulation / sudden-death checks.
12. Rotation / reveal updates (frozen in sudden death).
13. Emit events + snapshot (server) / view update (offline).
Match completion is guarded by a one-shot latch; result submission is idempotent.

## D-006 Turf Shift specifics
* Regulation 480 s, target 250, rotation period 60 s, order B → A → C → B …, first
  active zone B at LIVE start; next zone revealed at 45 s into each period (15 s before
  activation). Countdown to next rotation always published.
* Zone state per tick: NEUTRAL (no eligible occupant), CONTROLLED(team) (only one team
  present), CONTESTED (both present). Inactive zones have state INACTIVE.
* Eligible occupant: alive (not knocked out), not in respawn, not a training dummy,
  spawned in the match, and inside the **occupancy volume**: vertical cylinder around
  the zone centre, radius 9.0 m (enter) / 9.35 m (exit hysteresis), vertical band
  `floor_y − 0.6 … floor_y + 2.6` m measured at the fighter's feet. A normal jump
  (apex ≈ 0.9 m) stays inside the band; bridges/roofs above the zone are ≥ 3.5 m and are
  outside it.
* Scoring: while CONTROLLED(team) the team's control timer counts ticks; every 60
  consecutive ticks ⇒ +1 point, timer keeps the remainder. Any other state resets both
  timers to 0 (no hidden capture progress, no unattended ownership). Headcount never
  changes rate. Eliminations award no points.
* Regulation end (clock ≥ 480 s after step 10 of the tick): higher score wins. Tie ⇒
  SUDDEN_DEATH: rotation frozen on the current zone, ordinary respawns continue, the first
  team to score a point wins.
* 250 reached ⇒ immediate win (only one team can score in a tick).

## D-007 Spawns, respawn, protection
* Team 0 ("North") spawns around (0,0,−48); team 1 ("South") around (0,0,48). Five
  spawn points per team, each with a clear exit. Two separated exits per spawn plaza.
* Respawn delay 10 s. Respawn point: the free point of the team's spawn plaza farthest
  from observed enemies (always inside the protected volume).
* Spawn protection: damage/control immunity until (a) the fighter starts an offensive
  action, or (b) leaves the protected volume, or (c) 8 s elapse. Visible shimmer + HUD icon.
* Enemy entry into a protected spawn volume is blocked by a barrier collider on a
  team-specific physics layer (only the opposing team collides with it).

## D-008 Controls (defaults, all remappable; see docs/CONTROLS.md)
KB/M: WASD move · mouse camera/facing · LMB light · RMB heavy · Space jump · Shift dodge ·
F guard (hold) · Q/E/R skills · Tab scoreboard (hold) · MMB ping · Enter chat · Esc menu.
Controller: LS move · RS camera · X/□ light · Y/△ heavy · A/✕ jump · B/○ dodge · LT/L2 guard ·
LB/L1 Q · RB/R1 E · RT/R2 R · D-pad↑ ping · D-pad←/→ quick-chat · View/Select scoreboard ·
Menu/Start pause. Deadzones (inner/outer) configurable per stick. Shift is never sprint.

## D-009 Facing, camera
* Fighter facing follows camera yaw with a max turn rate (720°/s free; per-action limits in
  data, e.g. 240°/s during aimed startups, 0°/s after commitment). No target lock, no
  homing after commitment.
* Camera: orbit pivot at fighter chest (1.35 m), shoulder offset 0.45 m right, distance
  4.4 m (range 3.6–5.2), vertical FOV 75° (`keep_aspect = KEEP_HEIGHT`, adjustable 65–90°),
  pitch clamp −55°…+35°, spring-arm style sphere cast retraction (radius 0.25 m) against
  world geometry, smoothing applied only to retraction/extension — rotation is immediate.
  Camera shake: default **off**, optional 0–100 % slider.

## D-010 Shared combat numbers (initial; balance changes logged in docs/BALANCE.md)
* Stamina 100; dodge 25; heavy 15; regen 24/s after 0.9 s without spending; no regen
  while guard is held. Health regen 18/s after 6 s without attacking or being damaged.
* Light strikes: 18 damage; directional variants chosen by movement input at press:
  left / right / straight (neutral, forward, back); air light (one per jump). Chain of up
  to 3; the 3rd has longer recovery and pushes. Light hit-stun is always ≥ 3 ticks
  shorter than the fastest follow-up interval ⇒ no guaranteed light chains.
* Heavy: 38 damage, 0.45 s startup (readable), 15 stamina, guard damage 28, knockback.
* Guard: hold; frontal arc ±60°; movement ×0.45; blocked hits cost stamina = guard
  damage; stamina reaching 0 ⇒ guard break (0.9 s punishable stun). Back is unprotected.
  Guard never blocks grabs (Turnabout) — dodge does.
* Dodge: 0.36 s, evasion window ticks 2–13 (≈0.2 s), 4.2 m, directional (neutral = back),
  25 stamina.
* Control resistance (CR): any hard control (knockdown, grab, bark interrupt, guard break,
  stagger ≥ 0.5 s) grants 3.0 s CR: further hard control is downgraded to a 0.2 s flinch
  and displacement ×0.5; damage still applies. CR is shown above the fighter and in HUD.
* Damage targets: one body hurt capsule per fighter (feet→top of head, radius per
  species); ears, tails, clothing and fur are not hurtboxes. No headshots, no crits,
  no account bonuses.
* Friendly fire: disabled for all attacks. Teammates never hard-collide (soft separation
  only), so they cannot trap each other.

## D-011 Action model
Every attack/skill is an `ActionDef` with phases (startup / active windows / recovery),
integer-tick windows, stamina, cooldown, movement curve (action-local, sim-owned),
hit windows with swept sphere trajectories (action-local keyframes, radius), damage,
guard damage, displacement, hit-stun, flags (low, grab, strike, parryable, unblockable),
interruption rules (armor none/light), cancel windows (into dodge/guard/chain), turn-rate
limits, input-buffer window (6 ticks = 0.1 s; buffered presses expire after that).
Hit detection sweeps the sphere from its previous-tick position to its current-tick
position against every opposing hurt capsule (segment–segment distance) and checks
wall occlusion with a ray from the attacker's chest to the contact point on the
environment layer. One action event can damage a given target at most once.
Canonical numbers live in `game/data/tuning/*.json`; the Blender animation generator
reads the same files so clip phase timing and strike paths match the sim.

## D-012 Lag compensation
Server keeps 32 ticks of hurtbox history per fighter. For an attack by peer P the
server rewinds opposing hurtboxes by `clamp(round((rtt_P/2 + interp_delay) * 60), 0, 12)`
ticks (≤ 200 ms) where `rtt_P` is the **server-measured** ENet RTT; client-supplied
timestamps are never used for rewind. Defender guard/dodge/parry state is evaluated at
the server's current tick (defender reaction arriving in time is honoured). Walls are
static, checked in current geometry.

## D-013 Networking
* SceneMultiplayer over ENetMultiplayerPeer, UDP default port 24610 (range 24610–24699
  for allocator). `server_relay = false`, `allow_object_decoding = false`.
* A single `NetBridge` node at `/root/Net` exists on server and client with identical RPC
  signatures (checked by `test_net_rpc_signatures`).
* Handshake through SceneMultiplayer auth: protocol version, build id, join ticket
  (HMAC, server-bound, match-bound, single-use, 60 s expiry) or private-lobby password.
* Channels: 0 reliable lifecycle/events; 1 unreliable-ordered inputs (client→server,
  60 Hz, last 4 frames redundantly); 2 unreliable-ordered snapshots (server→client, 20 Hz).
* Client prediction for the local fighter (movement, action state, stamina, cooldowns);
  reconciliation on each snapshot by replaying unacknowledged inputs; remote fighters
  interpolated 100 ms behind.
* Server-side visibility: enemy entries are included in a client's snapshot only when
  observed by that client's team (line of sight from a living teammate, 70 m) or heard
  (≤ 14 m) or pinged, plus 0.5 s memory. Authorized observers receive full snapshots.
* Limits: input packet ≤ 96 B, reliable message ≤ 1 KiB, chat ≤ 120 chars & 1 msg/s,
  pings 2/s; violations are dropped and counted; repeated abuse ⇒ disconnect.
* Localhost network simulation uses `tools/netsim/udp_proxy.py` (real UDP datagrams,
  per-direction delay/jitter/loss). This is labelled *localhost simulation*, not WAN.

## D-014 Services
FastAPI + SQLAlchemy 2 + psycopg 3 + Alembic + argon2-cffi on PostgreSQL 16. Contract in
`docs/API_CONTRACT.md`. Sessions: opaque random tokens (hashed at rest), 12 h expiry.
Join tickets: HMAC-SHA256 over (ticket id, match id, account id, server id, expiry) with
a per-server secret; redeemed exactly once via the service. Results: server-signed,
idempotent per match id (unique constraint + transactional rating update).
Rating: Glicko-2-lite (rating, deviation) per account for ranked only.
Public traffic must be HTTPS (Caddy reverse proxy in compose); the client refuses
non-HTTPS service URLs except loopback hosts.

## D-015 Modes
* Offline: local authoritative sim, bots fill 9 slots, clearly labelled "BOT".
* Training: separate sandbox scene, dummies, overrides — never available in matches.
* Private: direct connect / server-browser; host administers teams, bots, observers.
* Casual queue: 1–10 humans; bot fill only if every queued party opted in ("allow bots").
* Ranked queue: exactly 10 humans; no bots ever; AFK/disconnect never replaced.
* Reconnect reservation 90 s (fighter removed from world meanwhile, not occupying).
* AFK: no input for 60 s in LIVE ⇒ warning at 45 s; casual/private-with-bots ⇒ labelled
  bot takeover; ranked ⇒ abandonment flag, no replacement.
* Forfeit: a team with zero connected humans (and no bots allowed) for 30 s loses.

## D-016 Character production pipeline
Characters are modelled procedurally in Blender (scripts under `blender/characters/`)
using signed-distance-field sculpting (smooth unions, anatomical landmarks, species
parameters) → marching cubes → cleanup/remesh → UV → baked procedural fur/cloth
textures (1K–2K) → armature with ear/jaw/tail bones → automatic weights + data-transfer
for clothing → procedural keyframed + IK-baked animation clips (timing from tuning JSON)
→ glTF (.glb) export → Godot import check. Sources (.blend, scripts, textures) are kept.

## D-017 References and brand
Private reference images stay local (git-ignored). The in-game logo is a cut-out derived
from reference #1 (game logo) — used as the brand asset, not redesigned. All other UI
art (icons, emblems, portraits) is original, generated from the game's own models or
drawn as SVG.

## D-018 Git
Small local commits on branch `claude/blissful-hypatia-rujnlz`; pushed only to the
owner's own repository branch designated for this session (the session's delivery
channel — the container is ephemeral). No public release, no other remotes.
Large binaries (toolchain, builds) are not committed.

## D-019 Presentation layer (match hosts)
The match scene (`scenes/match.tscn`) never touches rule objects directly. It reads a
`MatchHost` (`src/present/match_host.gd`): `LocalMatchHost` (offline/training — the same
`MatchSim` + server-side bots in-process), `NetMatchHost` (online — predicted local fighter +
100 ms interpolated remotes from `ClientSession`), `ReplayHost` (recorded 20 Hz frames +
events, no re-simulation). `FighterView` plays the contract clips from the Blender GLB when
imported, otherwise a procedural stand-in (`ProcRig`) with the same clip names/timings, so
gameplay presentation never depends on art availability. Offline fog-of-war uses the same
`TeamVisibility` rules as the server (minimap/plates show only what the team can see).

## D-020 Untrusted input handling
Client→server messages and auth payloads are Godot binary Variants; before `bytes_to_var`
they are structurally validated (`Protocol.valid_variant_bytes`: nil/bool/int/float/String/
Vector3/Array/Dictionary only, depth ≤ 4, ≤ 64 entries, strict UTF-8, exact length), so
malformed or hostile bytes are dropped silently and never reach engine decoders. Abuse kicks
are deferred to the end of the frame and every ENet-level peer is tracked (`_raw_peers`) so
the server never addresses a peer ENet already dropped. Direct-connect servers (no service
secret) reject tickets without computing an HMAC. Verified by `tests/integration/test_security.py`.

## D-021 Connection robustness
ENet peers use timeout limit 32 / min 12 s / max 30 s (engine default min is 5 s, shorter than
a loading hitch on slow machines). Clients send no inputs before the server's `welcome`
(which it sends only after admitting the peer), so unreliable inputs can never overtake the
reliable authentication-complete packet. Heavy match assets are loaded on worker threads
while the player is in menus (`Game.preload_match_assets`).

## D-022 Builds and verification hooks
Export presets: Windows client (one exe with the pack embedded, plus the console wrapper
`WILDRUSH.console.exe` in release builds too, for startup diagnostics; `tools/` and `tests/`
excluded), Linux dedicated
server (`dedicated_server=true`, character/arena/audio assets excluded; `OS.has_feature(
"dedicated_server")` makes the binary a server without flags), Linux client used only to
verify builds here. Release templates refuse command-line scene overrides, so verification
builds reach the flow test through `--flow-test` in `boot.gd` (active only when
`res://tools/flow_test.tscn` is packed, i.e. never in the Windows client). Pipeline assets
are used only when actually imported (`AssetUtil.imported`), never merely present on disk.

## D-023 Verification entry point semantics
`tools/verify.sh` is the single record of a verification run (`evidence/verify/latest.json`,
with the commit and whether the tree was dirty when the run started). A step is PASS only when
its process exits 0 AND its output check passes; output checks grep the finished step log after
the process has exited (never `cmd | tee | grep -q` under `pipefail`, which misreported a
passing test run as FAIL and could report an import with errors as PASS). Steps that cannot
run here are recorded as `BLOCKED: <reason>`, never PASS; any FAIL makes the script exit 1.
Godot's "ObjectDB instances leaked at exit" warning is not a failure condition: it reports a
fixed-size set of plain RefCounted objects still alive at shutdown — 17 with no test run,
116 after one and still 116 after two complete bot matches in the same process, so it does not
grow per match (measured; the likely holders are static caches such as `Behaviors._reg`, not
yet confirmed object by object).
