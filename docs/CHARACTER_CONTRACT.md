# Character & Animation Production Contract

Binding interface between the Blender character pipeline (`blender/characters/`) and the
Godot game (`game/`). Conventions from `docs/DECISIONS.md` D-003, D-011, D-016 apply.

## 1. Outputs per fighter `<id>` ∈ {nyx, bruno, vex, hops, scrap}
| Path | Content |
|------|---------|
| `blender/characters/*.py` | generation scripts (executed, reproducible: `tools/build_characters.sh`) |
| `blender/characters/<id>/<id>.blend` | editable source (mesh, armature, materials, all actions) |
| `blender/characters/<id>/textures/*.png` | source textures (1K–2K) |
| `game/assets/characters/<id>/<id>.glb` | runtime export (embedded textures OK) |
| `game/assets/characters/<id>/<id>_anim.json` | clip metadata (see §5) |
| `game/assets/ui/portraits/<id>.png` | 512×512 RGBA head-and-shoulders portrait rendered from the model (transparent bg) |
| `game/assets/ui/portraits/<id>_full.png` | 768×1024 RGBA full-body render (stance pose) for character select fallback |
| `evidence/characters/<id>_turnaround.png` | Blender render: front / back / left / right |
| `evidence/characters/<id>_skills.png` | Blender render: key poses of Q, E, R, heavy, guard |
| `evidence/characters/report.json` | tri counts, bone counts, material counts, clip list, alignment errors |

## 2. Units, orientation, scale
Metres, 1 Blender unit = 1 m, Z up, character faces **−Y**, origin at the feet
between them, armature and mesh with identity scale/rotation (apply transforms).
Heights (crown of head, excluding ears): Nyx 1.70, Bruno 1.77, Vex 1.73, Hops 1.67
(ears extra), Scrap 1.63. glTF exporter: +Y up conversion on (default).

## 3. Skeleton (names are binding; hierarchy shown)
```
Root (non-deform, at origin)
└─ Hips
   ├─ Spine ─ Chest ─ UpperChest
   │    ├─ Neck ─ Head ─┬─ Jaw
   │    │               ├─ LeftEar1 ─ LeftEar2 [─ LeftEar3 rabbit only]
   │    │               └─ RightEar1 ─ RightEar2 [─ RightEar3]
   │    ├─ LeftShoulder ─ LeftUpperArm ─ LeftLowerArm ─ LeftHand
   │    │      └─ LeftThumb1─LeftThumb2, LeftIndex1─LeftIndex2, LeftMiddle1─LeftMiddle2, LeftRing1─LeftRing2
   │    └─ RightShoulder … (mirror)
   ├─ LeftUpperLeg ─ LeftLowerLeg ─ LeftFoot ─ LeftToes
   ├─ RightUpperLeg … (mirror)
   └─ Tail1 ─ Tail2 ─ … TailN   (N = 6 cat, fox, raccoon; 3 dog; 2 rabbit)
```
Only these deform bones are exported (`export_def_bones=True`); IK/control bones stay
in the .blend. Max 4 influences per vertex, normalized weights.

## 4. Mesh, materials, textures
* Species-specific modelled anatomy (no capsule/sphere assemblies in the final look):
  distinct skull/muzzle, eyes with iris+pupil (cat/fox slit-ish, others round), nose,
  mouth line with jaw deformation, ears (with inner-ear colour), paw-hands (thumb + 3
  fingers, small claws/pads), feet with toes/pads, tail with species silhouette.
* Clothing per spec §6 and `docs/REFERENCE_AUDIT.md` B8–B11 (non-sexualised, soft pads,
  Vex copper panel on anatomical right shoulder only).
* 25–45k triangles total per fighter (profile target), ≤ 5 materials:
  `<id>_fur` (albedo 2K + normal), `<id>_cloth` (see palette masks), `<id>_eye`,
  optional `<id>_detail` (claws/nose/pads), optional `<id>_furcard` (alpha-clip cards,
  restrained: cheeks/tail tuft/chest).
* **Palette-ready clothing**: `<id>_cloth` uses `<id>_cloth_mask.png` where R = primary
  region, G = secondary region, B = accent region, A = 1 (trim = none of RGB), plus
  `<id>_cloth_detail.png` (greyscale fabric/leather detail + baked AO in RGB) and a normal
  map. The Blender material composites the default palette colours from
  `game/data/tuning/fighters/<id>.json → palettes.default` so renders look final; the game
  replaces it with a palette shader using the same textures.
* Fur is natural colour (never palette-driven). Team identity is shown by markers, never
  by recolouring fur.

## 5. Animation clips (Blender actions → glTF animations; 60 fps, in place, no root motion)
Names are binding. Durations in seconds; `L` = loop. Timings for attacks/skills come from
`game/data/tuning/fighters/<id>.json` (`total_s`, hit `t0/t1`, `clips` entries) — read
the JSON, do not hard-code.

Common (every fighter):
`idle`(2.0 L), `walk_f` `walk_b` `walk_l` `walk_r` (1.0 L, ref speed 2.0 m/s),
`run_f` `run_b` `run_l` `run_r` (L, one full cycle, ref speed = fighter move_speed for f,
×strafe/backpedal multipliers for others), `turn_l` `turn_r` (0.5, 90° in place),
`jump_start`(0.12) `jump_air`(0.5 L) `jump_fall`(0.5 L) `jump_land`(0.2),
`dodge_f` `dodge_b` `dodge_l` `dodge_r` (0.367), `guard_enter`(0.1) `guard_hold`(1.0 L)
`guard_exit`(0.12) `guard_block`(0.2) `guard_break`(0.9),
`light_s` `light_l` `light_r` `light_air` `heavy` (durations from JSON),
`hit_front`(0.3) `hit_back`(0.3) `hit_heavy`(0.5) `stagger`(0.6) `knockdown`(0.8, ends
lying) `getup`(0.45) `grabbed`(0.45) `knockout`(1.2, non-graphic collapse to a seated/
lying rest) `respawn`(0.8) `victory`(2.5 L) `defeat`(2.0).
Nyx only: `perch_climb`(0.45, climbs 1.2–2.4 m ledge; authored for 1.8 m).
Skills: every name in the fighter JSON: the `clip` field of generic skills
(`skill_e`, `skill_r`, …) and every entry of a skill's `clips` map with its duration.
`skill_*` clips must show clear preparation → action → recovery.

Guard poses are **forearm blocks** (no shield). Stand Firm is a planted wide stance.
Warning Bark uses the jaw + ears (mouth opens, ears pin back). Add ear/face motion
where it helps readability (hit reactions, bark, victory).

### Strike alignment (hit-volume trajectories)
For every hit in the JSON, the limb named by `limb` (`hand_r`→RightHand tip,
`hand_l`, `foot_r`→RightToes tip, `foot_l`, `both_hands`→midpoint of hands,
`shoulder_r`→RightShoulder/UpperArm joint, `tail_tip`→last Tail bone tail, `head`→Head)
must follow the JSON `path` during `[t0, t1]` within **0.15 m** (action-local →
Blender object space: X = −x, Y = −z, Z = y). For `follow: true` / moving skills the
path is relative to the (in-place) character origin. Report per-hit max error.

`<id>_anim.json`:
```json
{"fighter": "nyx", "fps": 60, "clips": {"run_f": {"duration": 0.66, "loop": true, "ref_speed": 7.2}, ...},
 "alignment": {"nyx_light_s#0": {"max_error_m": 0.04}, ...}, "bones": 58, "triangles": 38210}
```

## 6. Quality checks the pipeline must run and report
Rest-pose drift (bind pose vs frame 0 of `idle` sane), zero-length/overlapping bones,
unnormalized/empty weights, vertices with > 4 influences after limiting, mirrored
clothing sides (Vex shoulder panel side), feet contact during `idle`/`walk`/`run`
(foot bottom within 0.03 m of ground on planted frames), tail connected to hips,
glTF export validates and re-imports in Godot 4.7 without errors.
