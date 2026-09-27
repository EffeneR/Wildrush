"""Shared Blender helpers for the WILDRUSH character pipeline (run inside Blender)."""
import math
import os
import sys
import json

import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix, Quaternion
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def log(*a):
    print("[bl]", *a, flush=True)


def script_args():
    if "--" in sys.argv:
        return sys.argv[sys.argv.index("--") + 1:]
    return []


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    sc.render.fps = 60
    sc.render.fps_base = 1.0
    return sc


def link(ob, coll=None):
    (coll or bpy.context.scene.collection).objects.link(ob)
    return ob


def activate(ob):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)


def mesh_from_arrays(name, V, F, smooth=True):
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.ravel())
    me.loops.add(F.size)
    me.loops.foreach_set("vertex_index", F.ravel())
    me.polygons.add(len(F))
    me.polygons.foreach_set("loop_start", np.arange(0, F.size, 3))
    me.polygons.foreach_set("loop_total", np.full(len(F), 3))
    me.update()
    me.validate()
    if smooth:
        me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    link(ob)
    return ob


def mesh_arrays(ob, world=False):
    me = ob.data
    V = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", V)
    V = V.reshape(-1, 3)
    me.calc_loop_triangles()
    T = np.zeros(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", T)
    if world:
        M = np.array(ob.matrix_world)
        V = V @ M[:3, :3].T + M[:3, 3]
    return V, T.reshape(-1, 3)


def tri_count(ob):
    ob.data.calc_loop_triangles()
    return len(ob.data.loop_triangles)


def apply_modifier(ob, mod):
    activate(ob)
    bpy.ops.object.modifier_apply(modifier=mod.name)


def decimate(ob, target_tris, vgroup=None, factor=1.0, symmetric=False):
    n = tri_count(ob)
    if n <= target_tris:
        return n
    mod = ob.modifiers.new("dec", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = target_tris / n
    mod.use_collapse_triangulate = True
    if symmetric:
        mod.use_symmetry = True
        mod.symmetry_axis = "X"
    if vgroup:
        mod.vertex_group = vgroup
        mod.vertex_group_factor = factor
    apply_modifier(ob, mod)
    return tri_count(ob)


def set_vgroup(ob, name, weights):
    vg = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
    w = np.asarray(weights, dtype=np.float64)
    for i, x in enumerate(w):
        if x > 0.0:
            vg.add([i], float(x), "REPLACE")
    return vg


def vgroup_matrix(ob, names=None):
    """Dense (V, G) weights matrix for the object's vertex groups."""
    groups = [g.name for g in ob.vertex_groups] if names is None else list(names)
    gi = {g.name: g.index for g in ob.vertex_groups}
    col = {n: k for k, n in enumerate(groups)}
    W = np.zeros((len(ob.data.vertices), len(groups)), dtype=np.float64)
    idx2name = {g.index: g.name for g in ob.vertex_groups}
    for v in ob.data.vertices:
        for g in v.groups:
            nm = idx2name.get(g.group)
            if nm in col:
                W[v.index, col[nm]] = g.weight
    return W, groups


def write_vgroups(ob, W, names, clear=True, eps=1e-4):
    if clear:
        for g in list(ob.vertex_groups):
            if g.name in names:
                ob.vertex_groups.remove(g)
    for k, n in enumerate(names):
        vg = ob.vertex_groups.get(n) or ob.vertex_groups.new(name=n)
        col = W[:, k]
        idx = np.flatnonzero(col > eps)
        # group vertices by (rounded) weight to cut Python overhead
        for i in idx:
            vg.add([int(i)], float(col[i]), "REPLACE")


def limit_normalize(W, k=4):
    """Keep the k largest influences per row, renormalise."""
    if W.shape[1] > k:
        part = np.argpartition(-W, k, axis=1)[:, k:]
        np.put_along_axis(W, part, 0.0, axis=1)
    s = W.sum(axis=1, keepdims=True)
    W = np.where(s > 1e-9, W / np.maximum(s, 1e-12), W)
    return W


def transfer_weights(src_ob, dst_ob, names, max_dist=0.5):
    """Nearest-surface barycentric weight transfer (object spaces assumed identical)."""
    Vs, Ts = mesh_arrays(src_ob)
    Ws, _ = vgroup_matrix(src_ob, names)
    bvh = BVHTree.FromPolygons([tuple(v) for v in Vs], [tuple(t) for t in Ts], all_triangles=True)
    Vd, _ = mesh_arrays(dst_ob)
    out = np.zeros((len(Vd), len(names)))
    for i, co in enumerate(Vd):
        loc, nrm, fi, dist = bvh.find_nearest(Vector(co), max_dist)
        if fi is None:
            continue
        a, b, c = Vs[Ts[fi, 0]], Vs[Ts[fi, 1]], Vs[Ts[fi, 2]]
        p = np.array(loc)
        v0, v1, v2 = b - a, c - a, p - a
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        d20, d21 = v2 @ v0, v2 @ v1
        den = d00 * d11 - d01 * d01
        if abs(den) < 1e-18:
            bw = np.array([1 / 3, 1 / 3, 1 / 3])
        else:
            v = (d11 * d20 - d01 * d21) / den
            w = (d00 * d21 - d01 * d20) / den
            bw = np.clip(np.array([1 - v - w, v, w]), 0, 1)
            bw /= bw.sum()
        out[i] = bw[0] * Ws[Ts[fi, 0]] + bw[1] * Ws[Ts[fi, 1]] + bw[2] * Ws[Ts[fi, 2]]
    return out


def smooth_weights(ob, W, iters=2, alpha=0.5):
    me = ob.data
    E = np.zeros(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", E)
    E = E.reshape(-1, 2)
    n = len(me.vertices)
    for _ in range(iters):
        acc = np.zeros_like(W)
        cnt = np.zeros(n)
        np.add.at(acc, E[:, 0], W[E[:, 1]])
        np.add.at(acc, E[:, 1], W[E[:, 0]])
        np.add.at(cnt, E[:, 0], 1)
        np.add.at(cnt, E[:, 1], 1)
        avg = acc / np.maximum(cnt, 1)[:, None]
        W = (1 - alpha) * W + alpha * avg
    return W


def uv_islands(me, uv_layer_name=None):
    """Face islands in UV space (faces sharing an edge with identical UVs)."""
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    bm.faces.ensure_lookup_table()
    parent = list(range(len(bm.faces)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for e in bm.edges:
        if len(e.link_faces) != 2:
            continue
        f1, f2 = e.link_faces
        l1 = [l for l in f1.loops if l.edge == e][0]
        l2 = [l for l in f2.loops if l.edge == e][0]
        # l1 goes v0->v1 in f1, l2 goes v1->v0 in f2
        a1, b1 = l1[uvl].uv, l1.link_loop_next[uvl].uv
        a2, b2 = l2.link_loop_next[uvl].uv, l2[uvl].uv
        if (a1 - a2).length < 1e-6 and (b1 - b2).length < 1e-6:
            ra, rb = find(f1.index), find(f2.index)
            if ra != rb:
                parent[ra] = rb
    isl = np.array([find(i) for i in range(len(bm.faces))])
    bm.free()
    return isl


def scale_uv_islands(ob, factor_fn):
    """Scale each UV island about its centre by factor_fn(island 3D centroid)."""
    me = ob.data
    isl = uv_islands(me)
    uv = me.uv_layers.active.data
    UV = np.zeros(len(uv) * 2)
    uv.foreach_get("uv", UV)
    UV = UV.reshape(-1, 2)
    V = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", V)
    V = V.reshape(-1, 3)
    ls = np.zeros(len(me.polygons), dtype=np.int64)
    lt = np.zeros(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("loop_start", ls)
    me.polygons.foreach_get("loop_total", lt)
    lv = np.zeros(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    loop_face = np.repeat(np.arange(len(me.polygons)), lt)
    loop_isl = isl[loop_face]
    for r in np.unique(isl):
        m = loop_isl == r
        c3 = V[lv[m]].mean(axis=0)
        f = factor_fn(c3)
        if abs(f - 1.0) < 1e-3:
            continue
        cu = UV[m].mean(axis=0)
        UV[m] = cu + (UV[m] - cu) * f
    uv.foreach_set("uv", UV.ravel())
    me.update()


def smart_uv(ob, angle=66.0, margin=0.004, factor_fn=None, pack_margin=0.003):
    activate(ob)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    if factor_fn is not None:
        scale_uv_islands(ob, factor_fn)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin=pack_margin)
    bpy.ops.object.mode_set(mode="OBJECT")


def tri_mesh_export(ob, path, extra_face_attr=None):
    """Save triangles with per-corner UVs, per-vertex positions/normals for texture baking."""
    me = ob.data
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    tv = np.zeros(nt * 3, dtype=np.int64)
    tl = np.zeros(nt * 3, dtype=np.int64)
    tp = np.zeros(nt, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", tv)
    me.loop_triangles.foreach_get("loops", tl)
    me.loop_triangles.foreach_get("polygon_index", tp)
    V = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", V)
    N = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("normal", N)
    uv = me.uv_layers.active.data
    UV = np.zeros(len(uv) * 2)
    uv.foreach_get("uv", UV)
    mi = np.zeros(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("material_index", mi)
    data = dict(V=V.reshape(-1, 3), N=N.reshape(-1, 3), T=tv.reshape(-1, 3), UV=UV.reshape(-1, 2)[tl].reshape(-1, 3, 2),
                M=mi[tp])
    if extra_face_attr and extra_face_attr in me.attributes:
        a = me.attributes[extra_face_attr]
        arr = np.zeros(len(me.polygons), dtype=np.int64)
        a.data.foreach_get("value", arr)
        data["G"] = arr[tp]
    np.savez_compressed(path, **data)


def load_rig(wdir):
    with open(os.path.join(wdir, "rig.json")) as f:
        return json.load(f)


def fighter_json(fid):
    with open(os.path.join(REPO, "game", "data", "tuning", "fighters", fid + ".json")) as f:
        return json.load(f)
