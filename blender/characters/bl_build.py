"""WILDRUSH character pipeline - step 2 (Blender): assemble the rigged mesh.

blender -b --factory-startup -t 2 --python bl_build.py -- <work_dir>/<id>

  * armature from rig.json (CHARACTER_CONTRACT §3 names; Root non-deform)
  * full closed body decimated -> bone-heat automatic weights (weight source)
  * visible body + clothing decimated to budget (face/hands protected), smart UV
  * weights transferred (nearest-surface barycentric) from the bone-heat source to body
    and clothing, jaw weights from the mouth plane, eyes/teeth/whiskers/claws rigid
  * limit 4 influences + normalise
  * bake data (positions/normals/UVs per triangle) exported for wr_texture.py
Output: <work>/<id>/stage1.blend, bake_fur.npz, bake_cloth.npz, stage1.json
"""
import os
import sys
import math
import json
import time

import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bl_util import (log, script_args, reset_scene, link, activate, mesh_from_arrays, mesh_arrays, tri_count,
                     decimate, set_vgroup, vgroup_matrix, write_vgroups, limit_normalize, transfer_weights,
                     smooth_weights, smart_uv, tri_mesh_export, load_rig)

BUDGET = dict(body=19500, cloth=16500, full=34000)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def build_armature(rig):
    fid = rig["fighter"]
    ad = bpy.data.armatures.new(fid + "_rig")
    arm = bpy.data.objects.new(fid + "_rig", ad)
    link(arm)
    ad.display_type = "STICK"
    activate(arm)
    bpy.ops.object.mode_set(mode="EDIT")
    for b in rig["bones"]:
        eb = ad.edit_bones.new(b["name"])
        eb.head = Vector(b["head"])
        eb.tail = Vector(b["tail"])
        eb.align_roll(Vector(b["zhint"]))
        eb.use_deform = bool(b["deform"])
    for b in rig["bones"]:
        if b["parent"]:
            ad.edit_bones[b["name"]].parent = ad.edit_bones[b["parent"]]
            ad.edit_bones[b["name"]].use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def deform_names(rig):
    return [b["name"] for b in rig["bones"] if b["deform"]]


def heat_weights(src, arm, names):
    activate(src)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    W, _ = vgroup_matrix(src, names)
    empty = [n for k, n in enumerate(names) if W[:, k].max() < 0.05]
    unweighted = int((W.sum(axis=1) < 1e-4).sum())
    return W, empty, unweighted


def jaw_mask(V, rig, S):
    m = rig["mouth"]
    o = np.array(m["frame_o"])
    R = np.array(m["frame_R"])
    q = (V - o) @ R
    back = m["back"]
    piv = np.array(m["pivot"])
    qp = (piv - o) @ R
    below = smoothstep(0.0022, -0.0030, q[:, 2])
    front = smoothstep(qp[1] + 0.004, back + 0.006, q[:, 1])
    depth = smoothstep(-0.060 * S, -0.028 * S, q[:, 2])
    lat = smoothstep(0.075 * S, 0.045 * S, np.abs(q[:, 0]))
    return below * front * depth * lat


def make_eye(e, name):
    r = e["radius"]
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=14, radius=r)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    link(ob)
    axis = Vector(e["axis"]).normalized()
    up = Vector(e["up"]).normalized()
    right = up.cross(axis).normalized()
    up = axis.cross(right).normalized()
    M = Matrix((right, up, axis)).transposed()      # columns: local x,y,z -> world
    V = np.array([v.co[:] for v in me.vertices])
    Vw = V @ np.array(M).T + np.array(e["center"])
    me.vertices.foreach_set("co", Vw.ravel())
    # planar UV along the eye axis: iris texture centred at (0.5, 0.5)
    uvl = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            x, y, z = V[vi]
            uvl.data[li].uv = (0.5 + 0.49 * x / r, 0.5 + 0.49 * y / r)
    me.shade_smooth()
    return ob


def make_cone(name, base, direction, length, r0, r1=0.0, segs=6, rings=2, bend=None, uv_rect=(0, 0, 1, 1),
              up=None):
    d = Vector(direction).normalized()
    upv = Vector(up) if up is not None else (Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0)))
    x = d.cross(upv).normalized()
    y = x.cross(d).normalized()
    verts = []
    uvs = []
    faces = []
    b = Vector(base)
    for i in range(rings + 1):
        t = i / rings
        c = b + d * (length * t)
        if bend is not None:
            c += Vector(bend) * (length * t * t)
        rr = r0 + (r1 - r0) * t
        for k in range(segs):
            a = 2 * math.pi * k / segs
            verts.append(c + (x * math.cos(a) + y * math.sin(a)) * rr)
    tip = b + d * (length * 1.06) + (Vector(bend) * length * 1.1 if bend is not None else Vector())
    verts.append(tip)
    verts.append(b - d * 0.0005)
    ti = len(verts) - 2
    bi = len(verts) - 1
    for i in range(rings):
        for k in range(segs):
            a0 = i * segs + k
            a1 = i * segs + (k + 1) % segs
            faces.append((a0, a1, a1 + segs))
            faces.append((a0, a1 + segs, a0 + segs))
    last = rings * segs
    for k in range(segs):
        faces.append((last + k, last + (k + 1) % segs, ti))
        faces.append(((k + 1) % segs, k, bi))
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    uvl = me.uv_layers.new(name="UVMap")
    u0, v0, u1, v1 = uv_rect
    nring = rings + 1
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            if vi == ti:
                t = 1.0
            elif vi == bi:
                t = 0.0
            else:
                t = (vi // segs) / rings
            k = (vi % segs) / segs if vi < ti else 0.5
            uvl.data[li].uv = (u0 + (u1 - u0) * (0.15 + 0.7 * k), v0 + (v1 - v0) * (0.05 + 0.9 * t))
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    link(ob)
    return ob


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    return ob


def material(name, color):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    return m


def main():
    t0 = time.time()
    wdir = script_args()[0]
    rig = load_rig(wdir)
    fid = rig["fighter"]
    S = rig.get("head_scale", 1.0)
    reset_scene()
    report = dict(fighter=fid)
    arm = build_armature(rig)
    names = deform_names(rig)

    # ---- weight source: full closed body, bone heat
    d = np.load(os.path.join(wdir, "body_full.npz"))
    src = mesh_from_arrays(fid + "_wsrc", d["V"], d["F"])
    n = decimate(src, BUDGET["full"], symmetric=True)
    log(f"weight source decimated to {n} tris ({time.time() - t0:.1f}s)")
    Wsrc, empty, unweighted = heat_weights(src, arm, names)
    log(f"bone heat: empty bones {empty}, unweighted verts {unweighted} ({time.time() - t0:.1f}s)")
    report["heat_empty_bones"] = empty
    report["heat_unweighted_verts"] = unweighted
    if unweighted > 0:
        # fill unweighted vertices from their nearest weighted neighbours
        V, T = mesh_arrays(src)
        ok = Wsrc.sum(axis=1) > 1e-4
        from mathutils.kdtree import KDTree
        kd = KDTree(int(ok.sum()))
        idx_ok = np.flatnonzero(ok)
        for j, i in enumerate(idx_ok):
            kd.insert(Vector(V[i]), j)
        kd.balance()
        for i in np.flatnonzero(~ok):
            co, j, dist = kd.find(Vector(V[i]))
            Wsrc[i] = Wsrc[idx_ok[j]]
        write_vgroups(src, Wsrc, names)

    # ---- visible body
    d = np.load(os.path.join(wdir, "body_hi.npz"))
    body = mesh_from_arrays(fid + "_body", d["V"], d["F"])
    # decimate weights: 1 = collapse freely, lower = keep denser (never 0: that freezes vertices)
    set_vgroup(body, "protect", 1.0 - 0.72 * np.clip(d["W"], 0, 1))
    n0 = tri_count(body)
    mod = body.modifiers.new("dec", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = BUDGET["body"] / n0
    mod.use_symmetry = True
    mod.symmetry_axis = "X"
    mod.vertex_group = "protect"
    mod.vertex_group_factor = 0.012
    activate(body)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    log(f"body {n0} -> {tri_count(body)} tris ({time.time() - t0:.1f}s)")
    body.vertex_groups.remove(body.vertex_groups["protect"])
    hc = np.array(rig["landmarks"]["head_frame"]["o"])
    hands = [np.array(rig["hand_frames"][s]["wrist"]) for s in ("Left", "Right")]

    def texel_factor(c):
        f = 1.0
        if np.linalg.norm(c - hc) < 0.17 * S:
            f = 1.65
        for h in hands:
            if np.linalg.norm(c - h) < 0.14:
                f = max(f, 1.2)
        return f
    smart_uv(body, angle=64.0, margin=0.003, factor_fn=texel_factor, pack_margin=0.0025)
    log(f"body UV done ({time.time() - t0:.1f}s)")

    # ---- clothing
    d = np.load(os.path.join(wdir, "cloth_hi.npz"))
    cloth = mesh_from_arrays(fid + "_cloth", d["V"], d["F"])
    ga = cloth.data.attributes.new("garment", "INT", "FACE")
    ga.data.foreach_set("value", d["G"].astype(np.int64))
    set_vgroup(cloth, "protect", 1.0 - 0.65 * d["O"])
    n0 = tri_count(cloth)
    mod = cloth.modifiers.new("dec", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = BUDGET["cloth"] / n0
    mod.vertex_group = "protect"
    mod.vertex_group_factor = 0.010
    activate(cloth)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    log(f"cloth {n0} -> {tri_count(cloth)} tris ({time.time() - t0:.1f}s)")
    cloth.vertex_groups.remove(cloth.vertex_groups["protect"])
    smart_uv(cloth, angle=60.0, margin=0.003, pack_margin=0.003)
    log(f"cloth UV done ({time.time() - t0:.1f}s)")

    # ---- weights: transfer from bone-heat source
    Wb = transfer_weights(src, body, names)
    V, _ = mesh_arrays(body)
    # jaw from the mouth plane (heat cannot separate the lips)
    ji = names.index("Jaw")
    hi = names.index("Head")
    jm = jaw_mask(V, rig, S)
    hj = Wb[:, hi] + Wb[:, ji]
    Wb[:, ji] = hj * jm
    Wb[:, hi] = hj * (1 - jm)
    Wb = limit_normalize(Wb, 4)
    write_vgroups(body, Wb, names)
    Wc = transfer_weights(src, cloth, names)
    Wc = smooth_weights(cloth, Wc, iters=3, alpha=0.5)
    # clothing never follows the jaw / ears / fingers
    for nm in ("Jaw",):
        k = names.index(nm)
        Wc[:, hi] += Wc[:, k]
        Wc[:, k] = 0
    Wc = limit_normalize(Wc, 4)
    write_vgroups(cloth, Wc, names)
    log(f"weights transferred ({time.time() - t0:.1f}s)")

    # ---- eyes / teeth / claws / whiskers
    extras = []
    for i, e in enumerate(rig["eyes"]):
        ob = make_eye(e, f"{fid}_eye{i}")
        set_vgroup(ob, "Head", np.ones(len(ob.data.vertices)))
        extras.append(("eye", ob))
    for i, t in enumerate(rig["teeth"]):
        ob = make_cone(f"{fid}_tooth{i}", t["base"], t["dir"], t["length"], t["radius"], 0.0 if not t.get("flat") else t["radius"] * 0.8,
                       segs=5 if not t.get("flat") else 4, rings=1, uv_rect=(0.26, 0.02, 0.49, 0.98))
        set_vgroup(ob, t["bone"], np.ones(len(ob.data.vertices)))
        extras.append(("detail", ob))
    for i, c in enumerate(rig["claws"]):
        up = Vector(c["up"])
        ob = make_cone(f"{fid}_claw{i}", c["base"], c["dir"], c["length"], c["radius"], 0.0, segs=6, rings=2,
                       bend=(-up * 0.18)[:], uv_rect=(0.01, 0.02, 0.24, 0.98), up=c["up"])
        set_vgroup(ob, c["bone"], np.ones(len(ob.data.vertices)))
        extras.append(("detail", ob))
    for i, w in enumerate(rig["whiskers"]):
        ob = make_cone(f"{fid}_whisker{i}", w["base"], w["dir"], w["length"], 0.0011, 0.0003, segs=3, rings=3,
                       bend=(0, 0.15, -0.12), uv_rect=(0.51, 0.02, 0.74, 0.98))
        set_vgroup(ob, "Head", np.ones(len(ob.data.vertices)))
        extras.append(("detail", ob))

    # ---- materials
    mats = dict(fur=material(fid + "_fur", (0.5, 0.5, 0.5, 1)), cloth=material(fid + "_cloth", (0.2, 0.2, 0.22, 1)),
                eye=material(fid + "_eye", (0.8, 0.5, 0.1, 1)), detail=material(fid + "_detail", (0.9, 0.9, 0.85, 1)))
    body.data.materials.append(mats["fur"])
    cloth.data.materials.append(mats["cloth"])
    for kind, ob in extras:
        ob.data.materials.append(mats[kind])

    # ---- bake data (before join so vertex indices are local)
    tri_mesh_export(body, os.path.join(wdir, "bake_fur.npz"))
    tri_mesh_export(cloth, os.path.join(wdir, "bake_cloth.npz"), extra_face_attr="garment")

    # ---- join into one skinned mesh
    parts = [body, cloth] + [o for _, o in extras]
    mesh = join(parts, fid + "_mesh")
    # keep the garment attribute only for reference
    for g in list(mesh.vertex_groups):
        if g.name not in names:
            mesh.vertex_groups.remove(g)
    W, _ = vgroup_matrix(mesh, names)
    W = limit_normalize(W, 4)
    write_vgroups(mesh, W, names)
    mesh.parent = arm
    mod = mesh.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    mod.use_vertex_groups = True
    # weight source kept (hidden) in the .blend for re-transfer / inspection
    src.hide_render = True
    src.hide_set(True)
    src.parent = arm
    counts = (W > 1e-4).sum(axis=1)
    report.update(tris=tri_count(mesh), verts=len(mesh.data.vertices), max_influences=int(counts.max()),
                  zero_weight_verts=int((W.sum(axis=1) < 0.5).sum()),
                  materials=[m.name for m in mesh.data.materials], bones=len(names))
    with open(os.path.join(wdir, "stage1.json"), "w") as f:
        json.dump(report, f, indent=1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(wdir, "stage1.blend"), compress=True)
    log(f"stage1 done: {report} ({time.time() - t0:.1f}s)")


main()
