# WILDRUSH character pipeline — state

Owner: technical artist/animator workstream. Paths owned: `blender/characters/`,
`game/assets/characters/<id>/`, `game/assets/ui/portraits/`, `evidence/characters/`,
`tools/build_characters.sh`. Contract: `docs/CHARACTER_CONTRACT.md`.

Last update: 2026-09-29 (session 3)

## One command
```
tools/build_characters.sh [nyx bruno vex hops scrap]     # default: all five; exit != 0 on any failure
  env WILDRUSH_CHAR_WORK=<dir>        intermediates (default /tmp/wildrush_charwork)
      WILDRUSH_CHARCHECK_DIR=<dir>    scratch Godot project (default $WORK/godot_charcheck)
      BUILD_FROM=mesh|assemble|textures|anim|render   skip earlier steps (iteration)
      CHAR_MESH_RES / CHAR_CLOTH_RES  voxel size (default 0.0024 / 0.0035 m)
log: evidence/characters/build.log ; summary: evidence/characters/report.json
```
Session runs used `WILDRUSH_CHAR_WORK=<scratchpad>/work WILDRUSH_CHARCHECK_DIR=<scratchpad>/charcheck`.

## Environment notes (verified)
* Blender renders need `--gpu-backend vulkan` (no libEGL here; lavapipe works). Always `-t 2`.
  Every Blender call uses `--python-exit-code 1` (otherwise script errors exit 0).
* venv python `/home/user/Wildrush/.venv/bin/python`, `OMP_NUM_THREADS=2`.
* Decimate vertex-group: weight 1 = collapse freely, 0 = frozen (never use 0), fractional = denser.
* Godot import sidecar `<id>.glb.import` (written by `write_import_sidecar.py`) sets `animation/fps=60`
  (Godot default resamples to 30) and `settings/loop_mode=1` for every clip flagged loop in
  `<id>_anim.json`. Verified in the scratch project: loops + 1/60 step come through.
* Godot extracts embedded textures next to the GLB on import (default `embedded_image_handling=1`).

## Pipeline stages
| Step | Script | Output |
|------|--------|--------|
| mesh | `wr_mesh.py` (venv) | SDF sculpt -> marching cubes: body_hi / body_full / cloth_hi npz, rig.json |
| assemble | `bl_build.py` | decimate (body 19.5k, cloth 16.5k tris), smart UV, armature, bone-heat on full body, weight transfer (side-masked limbs, jaw from mouth plane), eyes/teeth/claws/whiskers -> stage1.blend |
| textures | `wr_texture.py` + `wr_fur.py` | fur albedo 2K + normal 1K; cloth mask/detail (sRGB, matches game palette shader)/normal/basecolor; eye; detail |
| anim | `bl_anim.py` (+`anim_lib.py`, `anim_clips.py`, `anim_fighters.py`, `bl_mat.py`) | control rig (IK arms/legs, calibrated poles), every contract clip authored per frame from tuning JSON, nla.bake to deform bones, checks.json, `<id>.blend`, GLB, `<id>_anim.json` |
| copy | build script | cloth mask/detail/normal PNG + `.glb.import` sidecar next to the GLB |
| verify | `bl_verify_glb.py` | Blender re-import (bones/tris/materials/images/anims) -> evidence/characters/<id>_glbcheck.json |
| render | `bl_render.py` (Eevee) | evidence turnaround/skills/blender + UI portraits |
| godot | `godot_check/` scratch project | import log + check_chars.gd (bones, clips vs anim.json incl. lengths/loops, materials) + screenshot |
| report | `report.py` | evidence/characters/report.json |

## Status per fighter
| Fighter | Mesh/clothing | Rig | Textures | Clips | GLB | Godot (scratch) | Renders |
|---------|---------------|-----|----------|-------|-----|-----------------|---------|
| nyx   | done | done (49 deform bones) | done | 49/49, all hits <= 0.078 m | done | clean | done |
| bruno | head+body+outfit designed, preview OK | NOT DONE | NOT DONE | builders written | NOT DONE | NOT DONE | NOT DONE |
| vex   | head+outfit designed | NOT DONE | NOT DONE | builders written | NOT DONE | NOT DONE | NOT DONE |
| hops  | head+outfit designed | NOT DONE | NOT DONE | builders written | NOT DONE | NOT DONE | NOT DONE |
| scrap | head+outfit designed | NOT DONE | NOT DONE | builders written | NOT DONE | NOT DONE | NOT DONE |

## Known issues / todo (visual)
* Nyx rebuild in progress with: per-leg trouser tubes (no web between thighs), wider stance, outward
  knee poles, firmer jaw close, shorter canines, tighter render framing.
* Final consistency: rebuild all five with one `tools/build_characters.sh` run at the end.

## Next exact action
Finish Nyx rebuild -> run `tools/build_characters.sh bruno` -> inspect renders -> vex -> hops -> scrap.

## Check log (appended per fighter export)
* nyx 2026-09-28T20:19Z: `CHARCHECK nyx bones=49 tris=37838 clips=49 missing=[] len_mismatch=[] loop_mismatch=[] mats=["nyx_fur", "nyx_cloth", "nyx_eye", "nyx_detail"]`; Blender re-import ok (49 bones, 49 anims, 6 images); godot_import.log: no ERROR lines.
