"""Blender core helpers for the Briarport art build: MeshBuilder (layout-space geometry with
world-scale planar UVs), materials from common.MATERIALS, objects/collections/instancing.

All positions handed to MeshBuilder are LAYOUT space (x east, y up, z south). to_mesh() maps
them to Blender (x, -z, y). Faces are given counter-clockwise as seen from their front side.
"""
from __future__ import annotations

import math
import os

import bpy
import numpy as np

import common as C

# ----------------------------------------------------------------------------- vector helpers


def v_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def v_dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def v_len(a):
    return math.sqrt(v_dot(a, a))


def v_norm(a):
    ln = v_len(a)
    if ln < 1e-12:
        return (0.0, 1.0, 0.0)
    return (a[0] / ln, a[1] / ln, a[2] / ln)


def poly_normal(pts):
    """Newell normal of a polygon (layout space)."""
    nx = ny = nz = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0, z0 = pts[i]
        x1, y1, z1 = pts[(i + 1) % n]
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return v_norm((nx, ny, nz))


def planar_frame(n):
    """Tangent (u) and bitangent (v) for planar UVs given a face normal (layout space).
    Vertical faces: u to the viewer's right, v up. Floors: u east, v north."""
    up = (0.0, 1.0, 0.0)
    t = v_cross(up, n)
    if v_len(t) < 1e-6:
        t = (1.0, 0.0, 0.0)
    t = v_norm(t)
    b = v_norm(v_cross(n, t))
    return t, b


# 4x4 affine transforms (row-major, layout space) -----------------------------------------
def M_identity():
    return np.identity(4)


def M_translate(x, y, z):
    m = np.identity(4)
    m[0, 3], m[1, 3], m[2, 3] = x, y, z
    return m


def M_yaw(a):
    """Rotation about +Y (up) by angle a (radians). Godot convention: forward -Z turns toward -X for a>0."""
    c, s = math.cos(a), math.sin(a)
    m = np.identity(4)
    m[0, 0], m[0, 2] = c, s
    m[2, 0], m[2, 2] = -s, c
    return m


def M_rotx(a):
    c, s = math.cos(a), math.sin(a)
    m = np.identity(4)
    m[1, 1], m[1, 2] = c, -s
    m[2, 1], m[2, 2] = s, c
    return m


def M_rotz(a):
    c, s = math.cos(a), math.sin(a)
    m = np.identity(4)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    return m


def M_scale(sx, sy=None, sz=None):
    sy = sx if sy is None else sy
    sz = sx if sz is None else sz
    m = np.identity(4)
    m[0, 0], m[1, 1], m[2, 2] = sx, sy, sz
    return m


def M_chain(*ms):
    out = np.identity(4)
    for m in ms:
        out = out @ m
    return out


def M_apply(m, p):
    x, y, z = p
    return (m[0, 0] * x + m[0, 1] * y + m[0, 2] * z + m[0, 3],
            m[1, 0] * x + m[1, 1] * y + m[1, 2] * z + m[1, 3],
            m[2, 0] * x + m[2, 1] * y + m[2, 2] * z + m[2, 3])


# ----------------------------------------------------------------------------- MeshBuilder
class MB:
    """Accumulates polygons in layout space. Each polygon owns its vertices (flat/hard edges)
    unless added through strip helpers that share vertices for smooth surfaces."""

    def __init__(self):
        self.P = []
        self.F = []
        self.UV = []
        self.FM = []
        self.SM = []
        self.mats = []
        self._mi = {}

    # materials
    def m(self, name):
        if name not in C.MATERIALS:
            raise KeyError(f"unknown material {name}")
        i = self._mi.get(name)
        if i is None:
            i = len(self.mats)
            self.mats.append(name)
            self._mi[name] = i
        return i

    def tris(self):
        return sum(len(f) - 2 for f in self.F)

    def empty(self):
        return not self.F

    # raw add
    def add_face(self, pts, mat, uvs, smooth=False):
        base = len(self.P)
        self.P.extend(pts)
        self.F.append(tuple(range(base, base + len(pts))))
        self.UV.append(tuple(uvs))
        self.FM.append(self.m(mat))
        self.SM.append(smooth)

    def add_indexed(self, pts, faces, uvs, mat, smooth=True):
        """Shared-vertex mesh piece: pts list, faces as index tuples into pts, uvs per face corner."""
        base = len(self.P)
        self.P.extend(pts)
        mi = self.m(mat)
        for f, fu in zip(faces, uvs):
            self.F.append(tuple(base + i for i in f))
            self.UV.append(tuple(fu))
            self.FM.append(mi)
            self.SM.append(smooth)

    # polygons with automatic world-planar UVs
    def poly(self, pts, mat, uv=None, texel=None, uv_origin=(0.0, 0.0, 0.0), uv_rot=False, uv_off=(0.0, 0.0),
             smooth=False, normal=None, facing=None):
        """Add a planar polygon. facing: desired normal direction -- the vertex order is reversed
        if needed so the front face points that way."""
        if facing is not None:
            if v_dot(poly_normal(pts), facing) < 0:
                pts = list(pts)[::-1]
                if uv is not None:
                    uv = list(uv)[::-1]
        if uv is None:
            n = normal or poly_normal(pts)
            t, b = planar_frame(n)
            su, sv = texel or C.TEXEL[C.MATERIALS[mat]["texel"]]
            uv = []
            for p in pts:
                q = v_sub(p, uv_origin)
                u, v = v_dot(q, t) / su + uv_off[0], v_dot(q, b) / sv + uv_off[1]
                uv.append((v, -u) if uv_rot else (u, v))
        self.add_face(pts, mat, uv, smooth)

    def quad(self, p0, p1, p2, p3, mat, **kw):
        self.poly([p0, p1, p2, p3], mat, **kw)

    def box(self, x0, y0, z0, x1, y1, z1, mat, skip=(), mats=None, **kw):
        """Axis-aligned box. skip: subset of {'top','bottom','n','s','e','w'}; mats: per-face override."""
        mats = mats or {}
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        if z1 < z0:
            z0, z1 = z1, z0
        F = {
            "top": [(x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)],
            "bottom": [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
            "s": [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
            "n": [(x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)],
            "e": [(x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)],
            "w": [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)],
        }
        for k, pts in F.items():
            if k in skip:
                continue
            self.poly(pts, mats.get(k, mat), **kw)

    def fbox(self, O, t, n, s0, s1, y0, y1, d0, d1, mat, skip=(), mats=None, **kw):
        """Box in a horizontal local frame: origin O (x, y, z), unit tangent t and outward normal n
        (both horizontal 3-vectors). s along t, y up, d along n. Faces: front(d1) back(d0)
        left(s0) right(s1) top bottom. Orientation is enforced with `facing`."""
        mats = mats or {}

        def P(s, y, d):
            return (O[0] + t[0] * s + n[0] * d, O[1] + y, O[2] + t[2] * s + n[2] * d)
        F = {
            "front": ([P(s0, y0, d1), P(s1, y0, d1), P(s1, y1, d1), P(s0, y1, d1)], n),
            "back": ([P(s1, y0, d0), P(s0, y0, d0), P(s0, y1, d0), P(s1, y1, d0)], (-n[0], 0.0, -n[2])),
            "left": ([P(s0, y0, d0), P(s0, y0, d1), P(s0, y1, d1), P(s0, y1, d0)], (-t[0], 0.0, -t[2])),
            "right": ([P(s1, y0, d1), P(s1, y0, d0), P(s1, y1, d0), P(s1, y1, d1)], t),
            "top": ([P(s0, y1, d1), P(s1, y1, d1), P(s1, y1, d0), P(s0, y1, d0)], (0.0, 1.0, 0.0)),
            "bottom": ([P(s0, y0, d0), P(s1, y0, d0), P(s1, y0, d1), P(s0, y0, d1)], (0.0, -1.0, 0.0)),
        }
        for k, (pts, fc) in F.items():
            if k in skip:
                continue
            self.poly(pts, mats.get(k, mat), facing=fc, **kw)

    def obox(self, M, sx, sy, sz, mat, skip=(), center_y=False, **kw):
        """Oriented box of size (sx,sy,sz) centred on local origin in x/z (y from 0 or centred),
        transformed by matrix M. UVs are planar in world space."""
        x0, x1 = -sx / 2, sx / 2
        z0, z1 = -sz / 2, sz / 2
        y0, y1 = (-sy / 2, sy / 2) if center_y else (0.0, sy)
        tmp = MB()
        tmp.box(x0, y0, z0, x1, y1, z1, mat, skip=skip)
        self.append(tmp, M, reuv=True, **kw)

    # cylinders / lathes (smooth sides)
    def lathe(self, profile, segs, mat, M=None, cap_top=True, cap_bottom=False, v_scale=None, u_repeat=1.0,
              smooth=True, cap_mat=None, angle0=0.0):
        """profile: list of (radius, y) from bottom to top. Revolves about local Y."""
        M = M if M is not None else M_identity()
        rings = []
        for (r, y) in profile:
            ring = []
            for k in range(segs + 1):
                a = angle0 + 2 * math.pi * k / segs
                ring.append(M_apply(M, (r * math.cos(a), y, -r * math.sin(a))))
            rings.append(ring)
        # arc length for v
        acc = [0.0]
        for i in range(1, len(profile)):
            acc.append(acc[-1] + math.hypot(profile[i][0] - profile[i - 1][0], profile[i][1] - profile[i - 1][1]))
        vs = v_scale or C.TEXEL[C.MATERIALS[mat]["texel"]][1]
        rmax = max(p[0] for p in profile) or 1.0
        su = C.TEXEL[C.MATERIALS[mat]["texel"]][0]
        ucirc = 2 * math.pi * rmax / su * u_repeat
        pts, faces, uvs = [], [], []
        idx = {}
        for i, ring in enumerate(rings):
            for k, p in enumerate(ring):
                idx[(i, k)] = len(pts)
                pts.append(p)
        for i in range(len(rings) - 1):
            if profile[i][0] < 1e-9 and profile[i + 1][0] < 1e-9:
                continue
            for k in range(segs):
                a, b, c, d = idx[(i, k)], idx[(i, k + 1)], idx[(i + 1, k + 1)], idx[(i + 1, k)]
                faces.append((a, b, c, d))
                u0, u1 = ucirc * k / segs, ucirc * (k + 1) / segs
                v0, v1 = acc[i] / vs, acc[i + 1] / vs
                uvs.append(((u0, v0), (u1, v0), (u1, v1), (u0, v1)))
        self.add_indexed(pts, faces, uvs, mat, smooth=smooth)
        cm = cap_mat or mat
        if cap_top and profile[-1][0] > 1e-9:
            r, y = profile[-1]
            ring = [M_apply(M, (r * math.cos(angle0 + 2 * math.pi * k / segs), y, -r * math.sin(angle0 + 2 * math.pi * k / segs))) for k in range(segs)]
            self.poly(ring, cm)
        if cap_bottom and profile[0][0] > 1e-9:
            r, y = profile[0]
            ring = [M_apply(M, (r * math.cos(angle0 + 2 * math.pi * k / segs), y, -r * math.sin(angle0 + 2 * math.pi * k / segs))) for k in range(segs)]
            self.poly(ring[::-1], cm)

    def cylinder(self, M, r, h, segs, mat, cap_top=True, cap_bottom=False, **kw):
        self.lathe([(r, 0.0), (r, h)], segs, mat, M=M, cap_top=cap_top, cap_bottom=cap_bottom, **kw)

    def tube(self, path, r, segs, mat, smooth=True, close_ends=True):
        """Sweep a circle of radius r along a polyline path (layout points)."""
        rings = []
        n = len(path)
        for i, p in enumerate(path):
            if i == 0:
                d = v_norm(v_sub(path[1], path[0]))
            elif i == n - 1:
                d = v_norm(v_sub(path[-1], path[-2]))
            else:
                d = v_norm(v_add(v_norm(v_sub(path[i], path[i - 1])), v_norm(v_sub(path[i + 1], path[i]))))
            ref = (0.0, 1.0, 0.0) if abs(d[1]) < 0.9 else (1.0, 0.0, 0.0)
            a = v_norm(v_cross(d, ref))
            b = v_norm(v_cross(d, a))
            ring = [v_add(p, v_add(v_mul(a, r * math.cos(2 * math.pi * k / segs)), v_mul(b, r * math.sin(2 * math.pi * k / segs)))) for k in range(segs + 1)]
            rings.append(ring)
        pts, faces, uvs = [], [], []
        acc = 0.0
        vv = [0.0]
        for i in range(1, n):
            acc += v_len(v_sub(path[i], path[i - 1]))
            vv.append(acc)
        su, sv = C.TEXEL[C.MATERIALS[mat]["texel"]]
        for ring in rings:
            pts.extend(ring)
        W = segs + 1
        for i in range(n - 1):
            for k in range(segs):
                a, b, c, d = i * W + k, i * W + k + 1, (i + 1) * W + k + 1, (i + 1) * W + k
                faces.append((a, b, c, d))
                u0, u1 = 2 * math.pi * r * k / segs / su, 2 * math.pi * r * (k + 1) / segs / su
                uvs.append(((u0, vv[i] / sv), (u1, vv[i] / sv), (u1, vv[i + 1] / sv), (u0, vv[i + 1] / sv)))
        self.add_indexed(pts, faces, uvs, mat, smooth=smooth)

    # merge
    def append(self, other: "MB", M=None, reuv=False, uv_off=(0.0, 0.0)):
        """Append another builder, transforming positions by M. reuv=True recomputes planar
        world UVs for non-atlas materials (keeps texel density consistent after transforms)."""
        base = len(self.P)
        if M is None:
            self.P.extend(other.P)
        else:
            self.P.extend(M_apply(M, p) for p in other.P)
        remap = [self.m(nm) for nm in other.mats]
        for f, uv, fm, sm in zip(other.F, other.UV, other.FM, other.SM):
            nf = tuple(base + i for i in f)
            mname = other.mats[fm]
            if reuv and C.MATERIALS[mname]["texel"] not in ("detail", "foliage", "banner", "ironwork", "puddle", "flat") and not sm:
                pts = [self.P[i] for i in nf]
                n = poly_normal(pts)
                t, b = planar_frame(n)
                su, sv = C.TEXEL[C.MATERIALS[mname]["texel"]]
                uv = tuple((v_dot(p, t) / su + uv_off[0], v_dot(p, b) / sv + uv_off[1]) for p in pts)
            self.F.append(nf)
            self.UV.append(uv)
            self.FM.append(remap[fm])
            self.SM.append(sm)

    def translated(self, dx, dy, dz):
        out = MB()
        out.append(self, M_translate(dx, dy, dz))
        return out

    def bounds(self):
        if not self.P:
            return None
        a = np.asarray(self.P)
        return a.min(axis=0), a.max(axis=0)


# ----------------------------------------------------------------------------- materials
_GLTF_GROUP = "glTF Material Output"


def _gltf_output_group():
    g = bpy.data.node_groups.get(_GLTF_GROUP)
    if g:
        return g
    g = bpy.data.node_groups.new(_GLTF_GROUP, "ShaderNodeTree")
    g.interface.new_socket("Occlusion", socket_type="NodeSocketFloat", in_out="INPUT")
    t = g.interface.new_socket("Thickness", socket_type="NodeSocketFloat", in_out="INPUT")
    t.default_value = 0.0
    g.nodes.new("NodeGroupOutput")
    g.nodes.new("NodeGroupInput")
    return g


def _image(stem, colorspace):
    path = os.path.join(C.TEX_DIR, stem + ".png")
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    im = bpy.data.images.get(stem)
    if im is None:
        im = bpy.data.images.load(path, check_existing=True)
        im.name = stem
    im.colorspace_settings.name = colorspace
    return im


def get_material(name):
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    spec = C.MATERIALS[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N.get("Principled BSDF")
    out = N.get("Material Output")
    bsdf.location = (300, 0)
    out.location = (600, 0)
    if spec["albedo"]:
        ta = N.new("ShaderNodeTexImage")
        ta.image = _image(spec["albedo"], "sRGB")
        ta.location = (-400, 300)
        L.new(ta.outputs["Color"], bsdf.inputs["Base Color"])
        if spec.get("alpha") == "clip":
            rnd = N.new("ShaderNodeMath")
            rnd.operation = "ROUND"
            rnd.location = (0, 150)
            L.new(ta.outputs["Alpha"], rnd.inputs[0])
            L.new(rnd.outputs[0], bsdf.inputs["Alpha"])
            mat.surface_render_method = "DITHERED"
        elif spec.get("alpha") == "blend":
            L.new(ta.outputs["Alpha"], bsdf.inputs["Alpha"])
            mat.surface_render_method = "BLENDED"
    else:
        c = spec.get("color", (0.8, 0.8, 0.8))
        bsdf.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
    if spec["normal"]:
        tn = N.new("ShaderNodeTexImage")
        tn.image = _image(spec["normal"], "Non-Color")
        tn.location = (-400, -300)
        nm = N.new("ShaderNodeNormalMap")
        nm.location = (0, -300)
        L.new(tn.outputs["Color"], nm.inputs["Color"])
        L.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if spec["orm"]:
        to = N.new("ShaderNodeTexImage")
        to.image = _image(spec["orm"], "Non-Color")
        to.location = (-400, 0)
        sep = N.new("ShaderNodeSeparateColor")
        sep.location = (-100, 0)
        L.new(to.outputs["Color"], sep.inputs["Color"])
        L.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        L.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
        grp = N.new("ShaderNodeGroup")
        grp.node_tree = _gltf_output_group()
        grp.location = (300, -400)
        L.new(sep.outputs["Red"], grp.inputs["Occlusion"])
    else:
        bsdf.inputs["Roughness"].default_value = spec.get("roughness", 0.7)
        bsdf.inputs["Metallic"].default_value = spec.get("metallic", 0.0)
    if spec.get("emission"):
        e = spec["emission"]
        bsdf.inputs["Emission Color"].default_value = (e[0], e[1], e[2], 1.0)
        bsdf.inputs["Emission Strength"].default_value = spec.get("strength", 5.0)
    mat.use_backface_culling = not spec.get("two_sided", False)
    return mat


# ----------------------------------------------------------------------------- objects
def to_mesh(mb: MB, name: str):
    me = bpy.data.meshes.new(name)
    nv = len(mb.P)
    if nv == 0:
        return me
    P = np.asarray(mb.P, dtype=np.float64)
    co = np.empty((nv, 3), dtype=np.float32)
    co[:, 0] = P[:, 0]
    co[:, 1] = -P[:, 2]
    co[:, 2] = P[:, 1]
    me.vertices.add(nv)
    me.vertices.foreach_set("co", co.ravel())
    loop_counts = np.fromiter((len(f) for f in mb.F), dtype=np.int32, count=len(mb.F))
    loop_starts = np.zeros_like(loop_counts)
    if len(loop_counts) > 1:
        loop_starts[1:] = np.cumsum(loop_counts)[:-1]
    nl = int(loop_counts.sum())
    verts = np.fromiter((i for f in mb.F for i in f), dtype=np.int32, count=nl)
    me.loops.add(nl)
    me.loops.foreach_set("vertex_index", verts)
    me.polygons.add(len(mb.F))
    me.polygons.foreach_set("loop_start", loop_starts)
    me.polygons.foreach_set("loop_total", loop_counts)
    me.polygons.foreach_set("material_index", np.asarray(mb.FM, dtype=np.int32))
    me.polygons.foreach_set("use_smooth", np.asarray(mb.SM, dtype=bool))
    uvl = me.uv_layers.new(name="UVMap")
    uv = np.fromiter((c for fu in mb.UV for p in fu for c in p), dtype=np.float32, count=nl * 2)
    uvl.data.foreach_set("uv", uv)
    for nm in mb.mats:
        me.materials.append(get_material(nm))
    me.update(calc_edges=True)
    me.validate(clean_customdata=False)
    return me


def get_collection(name, parent=None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def new_object(name, mesh, collection, loc=(0.0, 0.0, 0.0), yaw=0.0, scale=1.0, props=None):
    """loc in LAYOUT space; yaw radians about up (Godot convention)."""
    ob = bpy.data.objects.new(name, mesh)
    ob.location = (loc[0], -loc[2], loc[1])
    ob.rotation_euler = (0.0, 0.0, yaw)
    if isinstance(scale, (tuple, list)):
        ob.scale = (scale[0], scale[2], scale[1])
    else:
        ob.scale = (scale, scale, scale)
    collection.objects.link(ob)
    if props:
        for k, v in props.items():
            ob[k] = v
    return ob


def mesh_object(mb: MB, name, collection, props=None, loc=(0.0, 0.0, 0.0), yaw=0.0):
    if mb.empty():
        return None
    return new_object(name, to_mesh(mb, name), collection, loc=loc, yaw=yaw, props=props)


def empty_object(name, collection, loc, props=None):
    ob = bpy.data.objects.new(name, None)
    ob.location = (loc[0], -loc[2], loc[1])
    ob.empty_display_size = 0.5
    collection.objects.link(ob)
    if props:
        for k, v in props.items():
            ob[k] = v
    return ob


class Kit:
    """Registry of instanced kit meshes (linked duplicates -> shared glTF meshes)."""

    def __init__(self, collection):
        self.col = collection
        self.meshes = {}
        self.counts = {}

    def mesh(self, key, builder):
        me = self.meshes.get(key)
        if me is None:
            mb = builder() if callable(builder) else builder
            me = to_mesh(mb, key)
            self.meshes[key] = me
            proto = bpy.data.objects.new("KIT_" + key, me)
            self.col.objects.link(proto)
        return me

    def place(self, key, builder, collection, loc, yaw=0.0, scale=1.0, name=None, props=None):
        me = self.mesh(key, builder)
        self.counts[key] = self.counts.get(key, 0) + 1
        nm = name or f"{key}_{self.counts[key]:03d}"
        return new_object(nm, me, collection, loc=loc, yaw=yaw, scale=scale, props=props)
