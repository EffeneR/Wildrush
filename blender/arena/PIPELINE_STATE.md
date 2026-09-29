# Briarport environment-art pipeline — state

Owner: environment art. Paths owned: `blender/arena/`, `game/assets/arena/`,
`evidence/arena/blender_*.png`, `evidence/arena/art_build.log`, `tools/build_arena_art.sh`.
Contract: `docs/ENVIRONMENT_CONTRACT.md`. Layout (read-only): `game/data/arena/briarport_layout.json`.

Last updated: 2026-09-29 (session 2)

## Done (executed)
- Pipeline derisked (session 1): Blender 4.5.9 glTF export -> GLB post-process to external
  texture URIs (`glb_tools.externalize_images`) -> Godot 4.7.2 import in a scratch project:
  textures resolve to shared `res://.../textures/*.png`, ORM -> AO + roughness(G), COLOR_0 ->
  vertex_color_use_as_albedo, MASK -> alpha scissor + no culling, linked duplicates share one
  mesh, coordinates round-trip (layout (x,y,z) <-> Blender (x,-z,y) <-> glTF (x,y,z)).
- Textures: `gen_textures.py` + `gen_textures_b.py` + `texlib.py` (venv python, fixed seeds)
  -> 87 PNGs in `game/assets/arena/textures/` (~42 MB), atlases `atlas_{detail,foliage,ironwork}.json`,
  `textures.json` (sha256 list). Reviewed visually (tiling OK).
- `common.py` (paths, 37-entry material table, TEXEL densities, Layout queries, chunk_of).
- `bl_core.py` (MeshBuilder in layout space, world-planar UVs, materials, objects, Kit instancing).
- `bl_ground.py`: floor tops (exact heights, edge bands/patterns), floor sides + dock faces,
  canal walls (-3 m to adjoining level, follows stairs), copings, canal beds, water_* quads,
  balustrades along canal-edge blockers, stairs (nosings on ramp line), metal ramp, arched
  bridges, puddle_* meshes (+0.005), flush decals (grates, manholes, paint lines, fountain ring).
- `bl_arch.py`: building parcels from `kind: building` solids, facades with openings, trims,
  windows/doors/shops/balconies/shutters, roofs (gable, stepped canal gables, hip + cupola,
  flat/crenellated, clock tower), passages over spawn exits + yard gates, chimneys.
- `build_arena.py` builds ground + buildings and saves `briarport.blend` (runs in ~4 s).
- `render_review.py` (Eevee under xvfb-run; ~80-130 s per 960x540 view at 8 samples).

## Done in session 2 (executed)
- `bl_props.py`: arcade + loggia (terrace + balustrade, hanging lanterns), edge arch screens, columns,
  stalls, planters + trees/shrubs (foliage_*), fountain + bronze three-claw sculpture (water_fountain*),
  banner posts (banner_*), low walls (ivy / concrete + stencil logo), crate stacks + tarp, containers,
  lamp posts (emissive_*), wall/street banners, boats, barrels, pallets, forklift, crane (outside
  boundary, hook outside the 9 m circle), chimney smoke emitters (emit_smoke_* empties at layout points).
- `bl_skyline.py`: clock tower, 2 cathedrals, round tower, city ring, harbour (water_harbour), ground.
- `verify_arena.py`: floor tops, ramps/nosings, headroom, solid faces, zones, specials, budgets -> PASS
  (0 failures; floor worst 0.005 m = puddles). Integrated in build_arena.py (exit 3 on failure).
- `bl_export.py`: 6 GLB chunks + `arena_art.json` (chunks[].path = res://assets/arena/briarport_*.glb
  as loaded by game/src/present/arena_view.gd).
- `godot_check/` scratch-project import + check script; `tools/build_arena_art.sh` entry point.

## Status 2026-09-29 (current)
- Final re-export done with `tools/build_arena_art.sh` (01:07 UTC): 6 chunks
  A 96,493 / B 47,312 / C 18,646 / north 88,600 / south 73,762 / skyline 3,336 = 328,149 tris,
  36 materials, 86 referenced textures (87 on disk; container_green is used by ArenaView's fallback kit).
- All 87 textures now 1K-2K (ORM full-res for 1K sets, 1K ORM for 2K sets; small sets upscaled to 1K),
  47.5 MiB. textures.json hashes match (build skips regeneration when unchanged).
- Verification (Blender, verify_arena.py): PASS - floor tops worst 0.005 m (puddles, +0.005 by contract),
  stairs/ramp 0.000 m, solid faces worst 0.14 m (<= 0.15), headroom 5,988 samples clear, zones clear,
  specials present, budgets OK. Layout overlap noted (not an art error): crates_c_ne(_s) overlaps
  platform_c_ramp(_s) by 0.5 m (x 47..49, z -11..-10.5 / 10.5..11).
- Godot 4.7.2 scratch import: clean (6 GLB + 87 PNG). Engine check (godot_check/check_arena.gd):
  PASS - scenes load from res:// paths, shared external textures only, water AABBs match the layout
  (coordinate mapping verified), 216 floor raycasts on imported trimesh, worst 0.004 m.
  Last result: godot_check/last_check.json.
- Evidence renders: running at the time of writing -> evidence/arena/blender_{overview,topdown,A,B,C,north,south}.png

## Next / optional
- Inspect the final evidence renders; re-run `tools/build_arena_art.sh` after any change.
- Optional polish: more cargo dressing along yard walls, gatehouse rustication, Godot-side screenshots
  (`godot_check/shot_arena.gd`, copy game/src/present/shaders/water.gdshader to the scratch root first).

## Commands (run from repo root)
```
tools/build_arena_art.sh [--no-render] [--no-godot] [--textures] [--quick-render]   # everything
ARENA_CHECK_DIR=<scratch dir> tools/build_arena_art.sh                              # choose Godot scratch dir
.venv/bin/python blender/arena/gen_textures.py                       # textures (~3 min)
.toolchain/blender-4.5.9-linux-x64/blender -b --factory-startup -t 2 \
    --python-exit-code 1 --python blender/arena/build_arena.py        # build + save .blend
xvfb-run -a -s "-screen 0 1280x720x24" .toolchain/blender-4.5.9-linux-x64/blender -b \
    blender/arena/briarport.blend -t 2 --python-exit-code 1 \
    --python blender/arena/render_review.py -- --views overview,A,B,C  # review renders
```
Notes: Eevee needs an X display (xvfb-run); plain `-b` fails with "Couldn't open libEGL.so.1".
Blender returns 0 on Python exceptions unless `--python-exit-code 1` is given.
Saving twice creates `briarport.blend1` -> build sets save_version=0 (backup disabled).

## Known issues / decisions
- Crane yaw -100 in the layout: interpreted as a compass bearing so the jib points toward the
  yard (points from (66,-6) at zone C); documented in arena_art.json.
- Boats: yaw taken from the layout, but hulls are aligned to their canal's long axis when the
  given yaw would put a boat crosswise in a 4-5 m canal (visual-only decor).
- Layout regenerated 2026-09-27 with nav-only changes (agent_radius 0.5, max_climb 0.3); no
  geometry changes (verified by JSON diff).
