"""WILDRUSH character pipeline - step 4 (Blender): control rig, clips, bake, checks, export.

blender -b --factory-startup -t 2 --python bl_anim.py -- <work>/<id> <textures_dir> <out_blend> <out_glb> <out_anim_json> [--clips a,b]

Writes: editable .blend (mesh, armature + IK control rig, ctrl_* authoring actions, baked clip
actions), GLB (deform bones only, baked clips), <id>_anim.json (clips, alignment, counts),
and <work>/<id>/checks.json (contract §6 checks).
"""
import os
import sys
import json
import math
import time

import bpy
import numpy as np
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bl_util import log, script_args, activate, load_rig, fighter_json, tri_count, vgroup_matrix  # noqa: E402
import bl_mat  # noqa: E402
import anim_lib as AL  # noqa: E402
import anim_clips as AC  # noqa: E402
import anim_fighters as AF  # noqa: E402

LIMB_TIP = {
    "hand_r": lambda d: d["RightHand.tail"],
    "hand_l": lambda d: d["LeftHand.tail"],
    "foot_r": lambda d: d["RightToes.tail"],
    "foot_l": lambda d: d["LeftToes.tail"],
    "both_hands": lambda d: (d["RightHand.tail"] + d["LeftHand.tail"]) * 0.5,
    "shoulder_r": lambda d: d["RightUpperArm.head"],
    "tail_tip": lambda d: d["tail_tip"],
    "head": lambda d: d["Head.head"],
}


def main():
    t0 = time.time()
    args = script_args()
    wdir, texdir, out_blend, out_glb, out_json = args[:5]
    only = None
    if "--clips" in args:
        only = set(args[args.index("--clips") + 1].split(","))
    bpy.ops.wm.open_mainfile(filepath=os.path.join(wdir, "stage1.blend"))
    sc = bpy.context.scene
    sc.render.fps = 60
    sc.render.fps_base = 1.0
    rig = load_rig(wdir)
    fid = rig["fighter"]
    fj = fighter_json(fid)
    arm = bpy.data.objects[fid + "_rig"]
    mesh = bpy.data.objects[fid + "_mesh"]
    bl_mat.setup_materials(mesh, fid, texdir, fj["palettes"]["default"])
    # relative texture paths inside the .blend
    AL.build_control_rig(arm)
    info = AL.RigInfo(arm, rig)
    poles = AL.calibrate_poles(arm, info)
    log("pole calibration:", {k: (round(v[0], 5), v[1]) for k, v in poles.items()})
    solver = AL.Solver(info)
    C = AC.Ctx(fid, info, solver, fj)
    clips, req = AF.build_clips(C)
    # attack hit metadata for alignment (clip-local)
    acts = fj["actions"]
    hitmap = []   # (key, clip, limb, hit, offset)
    for aid, a in acts.items():
        for i, h in enumerate(a.get("hits", [])):
            limb = h.get("limb", a.get("limb"))
            if "clip" in a and "total_s" in a:
                hitmap.append((f"{aid}#{i}", a["clip"], limb, h, 0.0))
    for cname, (fn, dur, meta) in clips.items():
        for limb, h, off in (meta or {}).get("hits", []):
            for aid, a in acts.items():
                for i, hh in enumerate(a.get("hits", [])):
                    if hh is h:
                        hitmap.append((f"{aid}#{i}", cname, limb, h, off))
    # mesh evaluation off while authoring / baking (speed)
    armmod = mesh.modifiers["Armature"]
    armmod.show_viewport = False
    names = list(clips.keys()) if only is None else [n for n in clips if n in only]
    baked = {}
    frames = {}
    for cname in names:
        fn, dur, meta = clips[cname]
        loop = bool((meta or {}).get("loop"))
        ts = time.time()
        act, n, resolved = AL.author_clip(arm, info, solver, cname, fn, dur, loop)
        b = AL.bake_clip(arm, info, cname, n)
        baked[cname] = b
        frames[cname] = n
        log(f"clip {cname:18s} {dur:.3f}s {n:3d}f loop={loop} ({time.time() - ts:.1f}s)")
    armmod.show_viewport = True

    # ------------------------------------------------------------------ checks
    checks = dict(fighter=fid)
    # alignment
    align = {}
    for key, cname, limb, h, off in hitmap:
        if cname not in baked:
            continue
        dur = clips[cname][1]
        ta = max(h["t0"] - off, 0.0)
        tb = min(h["t1"] - off, dur)
        if tb < ta:
            continue
        n = max(2, int(math.ceil((tb - ta) * 60)) + 1)
        ts = [ta + (tb - ta) * k / (n - 1) for k in range(n)]
        pts = AL.eval_points(arm, info, baked[cname], [t * 60 for t in ts])
        err = 0.0
        for t, d in zip(ts, pts):
            tip = LIMB_TIP[limb](d)
            e = (tip - AL.path_at(h["path"], t + off)).length
            err = max(err, e)
        prev = align.get(key, {}).get("max_error_m", 0.0)
        align[key] = dict(max_error_m=round(max(err, prev), 4), clip=cname if key not in align else align[key]["clip"] + "+" + cname,
                          limb=limb, ok=bool(max(err, prev) <= 0.15))
    checks["alignment"] = align
    # feet contact during idle / walk / run planted frames
    contact = {}
    for cname in [c for c in ("idle", "walk_f", "walk_b", "walk_l", "walk_r", "run_f", "run_b", "run_l", "run_r") if c in baked]:
        meta = clips[cname][2] or {}
        n = frames[cname]
        cfr = meta.get("contacts")
        if cfr is None:
            cfr = {"Left": list(range(n)), "Right": list(range(n))}
        worst = 0.0
        slide = 0.0
        allf = sorted(set(cfr["Left"]) | set(cfr["Right"]))
        pts = AL.eval_points(arm, info, baked[cname], allf)
        byf = dict(zip(allf, pts))
        v = meta.get("ref_speed", 0.0)
        for side in ("Left", "Right"):
            prev = None
            for fr in cfr[side]:
                d = byf[fr]
                low = min(d[side + "_heel"].z, d[side + "_ballsole"].z, d[side + "_tipsole"].z)
                worst = max(worst, abs(low))
                bpos = d[side + "_ballsole"]
                if prev is not None and fr == prev[0] + 1:
                    # expected in-place slide = ref speed * dt opposite travel; measure deviation magnitude
                    step = (bpos - prev[1]).length * 60.0
                    slide = max(slide, abs(step - v))
                prev = (fr, bpos)
        contact[cname] = dict(max_foot_height_m=round(worst, 4), ok=bool(worst <= 0.03),
                              planted_speed_dev_mps=round(slide, 3))
    checks["foot_contact"] = contact
    # rest-pose drift: idle frame 0 vs bind -> hips drift small, bone lengths unchanged, feet grounded
    if "idle" in baked:
        set_c = AL.set_constraints_enabled
        set_c(arm, False)
        arm.animation_data.action = baked["idle"]
        sc.frame_set(0)
        pbs = arm.pose.bones
        hips_drift = (pbs["Hips"].head - info.head["Hips"]).length
        len_err = max(abs((pb.tail - pb.head).length - info.length[pb.name]) for pb in pbs if pb.bone.use_deform)
        d0 = AL.eval_points(arm, info, baked["idle"], [0])[0]
        feet = max(abs(min(d0[s + "_heel"].z, d0[s + "_ballsole"].z, d0[s + "_tipsole"].z)) for s in ("Left", "Right"))
        hand_move = max((d0[k] - info.tail[k.split(".")[0]]).length for k in ("RightHand.tail", "LeftHand.tail"))
        checks["rest_drift_idle0"] = dict(hips_drift_m=round(hips_drift, 4), max_bone_length_change_m=round(len_err, 6),
                                          feet_height_m=round(feet, 4), hand_move_from_Apose_m=round(hand_move, 3),
                                          ok=bool(hips_drift < 0.15 and len_err < 0.001 and feet < 0.03))
        set_c(arm, True)
    # skeleton sanity
    zero_len = [b.name for b in arm.data.bones if b.length < 1e-4]
    overlap = []
    bl = [b for b in arm.data.bones if b.use_deform]
    for i, a in enumerate(bl):
        for b in bl[i + 1:]:
            if (a.head_local - b.head_local).length < 1e-4 and (a.tail_local - b.tail_local).length < 1e-4:
                overlap.append((a.name, b.name))
    t1 = arm.data.bones.get("Tail1")
    tail_ok = bool(t1 is not None and t1.parent is not None and t1.parent.name == "Hips")
    dnames = [b.name for b in bl]
    W, _ = vgroup_matrix(mesh, dnames)
    sums = W.sum(axis=1)
    infl = (W > 1e-4).sum(axis=1)
    checks["skeleton"] = dict(deform_bones=len(dnames), zero_length=zero_len, overlapping=overlap,
                              tail_connected_to_hips=tail_ok)
    checks["weights"] = dict(verts=len(W), unnormalized=int((np.abs(sums - 1) > 0.01).sum()), empty=int((sums < 1e-3).sum()),
                             max_influences=int(infl.max()), over_4=int((infl > 4).sum()))
    checks["triangles"] = tri_count(mesh)
    checks["materials"] = [m.name for m in mesh.data.materials]
    checks["clips"] = {k: dict(duration=round(clips[k][1], 4), frames=frames[k]) for k in baked}
    checks["required_missing"] = [k for k in req if k not in baked]
    with open(os.path.join(wdir, "checks.json"), "w") as f:
        json.dump(checks, f, indent=1)
    log("alignment:", {k: v["max_error_m"] for k, v in align.items()})
    log("contacts:", {k: v["max_foot_height_m"] for k, v in contact.items()})

    # ------------------------------------------------------------------ save editable .blend
    if "ctrl_idle" in bpy.data.actions:
        arm.animation_data.action = bpy.data.actions["ctrl_idle"]
    sc.frame_set(0)
    os.makedirs(os.path.dirname(out_blend), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=out_blend, compress=True)
    try:
        bpy.ops.file.make_paths_relative()
    except RuntimeError as e:
        log("make_paths_relative:", e)
    bpy.ops.wm.save_mainfile(compress=True)
    missing = [im.name for im in bpy.data.images if im.source == "FILE" and not os.path.exists(bpy.path.abspath(im.filepath))]
    if missing:
        raise RuntimeError(f"images not found after save: {missing}")
    log(f"saved {out_blend}")

    # ------------------------------------------------------------------ export GLB
    AL.set_constraints_enabled(arm, False)
    for pb in arm.pose.bones:
        for c in list(pb.constraints):
            pb.constraints.remove(c)
    for img in bpy.data.images:
        if img.source == "FILE":
            img.reload()
            w, h = img.size[:]
            if w == 0 or not os.path.exists(bpy.path.abspath(img.filepath)):
                raise RuntimeError(f"texture failed to load for export: {img.filepath} -> {bpy.path.abspath(img.filepath)}")
    for a in list(bpy.data.actions):
        if a.name.startswith("ctrl_"):
            bpy.data.actions.remove(a)
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bl_mat.cloth_to_export(mesh, fid)
    src = bpy.data.objects.get(fid + "_wsrc")
    if src:
        bpy.data.objects.remove(src, do_unlink=True)
    for o in sc.objects:
        o.select_set(False)
    arm.select_set(True)
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = arm
    os.makedirs(os.path.dirname(out_glb), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=out_glb, export_format="GLB", use_selection=True, export_def_bones=True, export_animations=True,
        export_animation_mode="ACTIONS", export_force_sampling=True, export_frame_step=1,
        export_optimize_animation_size=True, export_anim_single_armature=True, export_reset_pose_bones=True,
        export_rest_position_armature=True, export_skins=True, export_influence_nb=4, export_all_influences=False,
        export_morph=False, export_yup=True, export_apply=False, export_texcoords=True, export_normals=True,
        export_tangents=True, export_materials="EXPORT", export_image_format="AUTO", export_cameras=False,
        export_lights=False, export_extras=False, export_leaf_bone=False)
    log(f"exported {out_glb} ({os.path.getsize(out_glb) / 1e6:.1f} MB)")

    # ------------------------------------------------------------------ anim json
    strafe, back = AF.movement_mults(C)
    anim = dict(fighter=fid, fps=60, in_place=True, root_motion=False, forward="-Y (Blender) / +Z (glTF)",
                clips={}, alignment={k: dict(max_error_m=v["max_error_m"], clip=v["clip"]) for k, v in align.items()},
                bones=len(dnames), triangles=tri_count(mesh), materials=[m.name for m in mesh.data.materials],
                cloth_textures=dict(mask=f"{fid}_cloth_mask.png", detail=f"{fid}_cloth_detail.png",
                                    normal=f"{fid}_cloth_normal.png",
                                    note="R=primary G=secondary B=accent, trim=none; see CHARACTER_CONTRACT §4"),
                alignment_space="object space of the in-place clip (action-local x,y,z -> Blender -x,-z,y)")
    for k in baked:
        fn, dur, meta = clips[k]
        e = dict(duration=round(frames[k] / 60.0, 4), nominal=round(dur, 4), frames=frames[k], loop=bool((meta or {}).get("loop")))
        if (meta or {}).get("ref_speed") is not None:
            e["ref_speed"] = round(meta["ref_speed"], 4)
        anim["clips"][k] = e
    with open(out_json, "w") as f:
        json.dump(anim, f, indent=1)
    log(f"done in {time.time() - t0:.1f}s")


main()
