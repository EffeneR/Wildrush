"""Props for Briarport: art for the non-building layout solids (arcade + loggia, edge arches,
stalls, planters + trees, fountain + statue, banner posts, low walls, crate stacks, containers)
and every `decor` entry (lamp posts, banners, boats, barrels, pallets, forklift, crane, chimney
smoke emitters). Small repeated props are Kit meshes (linked duplicates -> shared glTF meshes).

Layout solids: visual faces within +-0.15 m of the box up to 2.5 m (stalls: counter height).
Decor: never collides; positions that land on stairs/solids are nudged to the nearest free flat
spot (logged). Nothing hangs below 2.4 m over walkable floor outside solid footprints.
"""
from __future__ import annotations

import math
import random

import common as C
from bl_core import (MB, M_apply, M_chain, M_rotx, M_rotz, M_scale, M_translate, M_yaw, poly_normal, v_add,
                     v_cross, v_mul, v_norm, v_sub)
from bl_arch import Frame, Opening, hash_str, wall_with_openings
from common import Rect

UP = (0.0, 1.0, 0.0)
DOWN = (0.0, -1.0, 0.0)


def fb(mb, x0, y0, z0, x1, y1, z1, mat, **kw):
    mb.box(x0, y0, z0, x1, y1, z1, mat, **kw)


def atlas_rect_uv(atl, key, inset=2):
    return C.atlas_uv(atl, key, inset_px=inset)


# =============================================================================== kit builders
def kit_lamp_post():
    mb = MB()
    mb.lathe([(0.2, 0.0), (0.2, 0.12), (0.15, 0.2), (0.12, 0.45), (0.09, 0.55), (0.075, 0.62)], 8, "iron", cap_top=False)
    mb.lathe([(0.07, 0.62), (0.052, 3.1)], 8, "iron", cap_top=False)
    mb.lathe([(0.052, 3.1), (0.1, 3.15), (0.1, 3.22), (0.06, 3.28), (0.19, 3.3), (0.19, 3.34)], 8, "iron", cap_top=True)
    for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        fb(mb, sx * 0.15 - 0.015, 3.34, sz * 0.15 - 0.015, sx * 0.15 + 0.015, 3.78, sz * 0.15 + 0.015, "iron")
    mb.poly([(-0.21, 3.78, 0.21), (0.21, 3.78, 0.21), (0.0, 4.02, 0.0)], "iron")
    mb.poly([(0.21, 3.78, 0.21), (0.21, 3.78, -0.21), (0.0, 4.02, 0.0)], "iron")
    mb.poly([(0.21, 3.78, -0.21), (-0.21, 3.78, -0.21), (0.0, 4.02, 0.0)], "iron")
    mb.poly([(-0.21, 3.78, -0.21), (-0.21, 3.78, 0.21), (0.0, 4.02, 0.0)], "iron")
    mb.poly([(-0.21, 3.78, -0.21), (0.21, 3.78, -0.21), (0.21, 3.78, 0.21), (-0.21, 3.78, 0.21)], "iron", facing=DOWN)
    mb.lathe([(0.0, 4.0), (0.05, 4.05), (0.03, 4.15), (0.0, 4.2)], 6, "iron", cap_top=False)
    return mb


def kit_lamp_glass(y0=3.34, y1=3.78):
    mb = MB()
    fb(mb, -0.14, y0, -0.14, 0.14, y1, 0.14, "emissive_lamp", skip=("bottom", "top"))
    return mb


def kit_hanging_lantern(ceiling):
    mb = MB()
    top = ceiling
    lt = 3.75
    mb.tube([(0.0, top, 0.0), (0.0, lt + 0.3, 0.0)], 0.018, 4, "iron")
    mb.lathe([(0.0, lt + 0.3), (0.2, lt + 0.05), (0.2, lt)], 8, "iron", cap_top=False)
    for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        fb(mb, sx * 0.13 - 0.012, lt - 0.45, sz * 0.13 - 0.012, sx * 0.13 + 0.012, lt, sz * 0.13 + 0.012, "iron")
    fb(mb, -0.16, lt - 0.5, -0.16, 0.16, lt - 0.45, 0.16, "iron")
    return mb


def kit_barrel():
    mb = MB()
    prof = [(0.27, 0.0), (0.31, 0.2), (0.33, 0.44), (0.31, 0.68), (0.27, 0.88)]
    mb.lathe(prof, 12, "wood_planks", cap_top=True, cap_mat="wood_planks")
    # staves vertical: swap the uv axes of the side faces
    for i in range(len(mb.UV)):
        if mb.SM[i]:
            mb.UV[i] = tuple((v * 1.0, u * 1.0) for (u, v) in mb.UV[i])
    for y, r in ((0.08, 0.292), (0.26, 0.322), (0.62, 0.322), (0.8, 0.292)):
        mb.lathe([(r, y - 0.03), (r + 0.012, y), (r, y + 0.03)], 12, "iron", cap_top=False)
    return mb


def kit_barrel_group():
    mb = MB()
    b = kit_barrel()
    for (x, z, yaw) in ((0.0, 0.0, 0.0), (0.68, 0.12, 0.7), (0.3, -0.62, 1.4)):
        mb.append(b, M_chain(M_translate(x, 0.0, z), M_yaw(yaw)))
    # one barrel lying on its side
    mb.append(b, M_chain(M_translate(-0.62, 0.3, 0.45), M_yaw(0.5), M_rotz(math.pi / 2), M_translate(0.0, -0.44, 0.0)))
    return mb


def crate(mb, x0, y0, z0, w, h, d, M=None, brace=True):
    """Wooden crate with frame boards. Local box [x0,x0+w]x[y0,y0+h]x[z0,z0+d] then transform M."""
    tmp = MB()
    tmp.box(x0 + 0.02, y0, z0 + 0.02, x0 + w - 0.02, y0 + h - 0.02, z0 + d - 0.02, "wood_planks")
    t = 0.08
    for (a, b) in ((x0, x0 + t), (x0 + w - t, x0 + w)):
        for (c, e) in ((z0, z0 + t), (z0 + d - t, z0 + d)):
            tmp.box(a, y0, c, b, y0 + h, e, "wood_planks", skip=("bottom",))
    for yy in (y0, y0 + h - t):
        tmp.box(x0, yy, z0, x0 + w, yy + t, z0 + t, "wood_planks", skip=("bottom",))
        tmp.box(x0, yy, z0 + d - t, x0 + w, yy + t, z0 + d, "wood_planks", skip=("bottom",))
        tmp.box(x0, yy, z0, x0 + t, yy + t, z0 + d, "wood_planks", skip=("bottom",))
        tmp.box(x0 + w - t, yy, z0, x0 + w, yy + t, z0 + d, "wood_planks", skip=("bottom",))
    mb.append(tmp, M, reuv=M is not None)


def kit_crate_single():
    mb = MB()
    crate(mb, -0.69, 0.0, -0.69, 1.38, 1.0, 1.38)
    return mb


def kit_crates_small():
    mb = MB()
    for i, (x, z) in enumerate(((-1.24, -1.24), (0.0, -1.22), (-1.23, 0.0), (0.0, 0.0))):
        crate(mb, x, 0.0, z, 1.24 if x < 0 else 1.23, 1.2 if i != 2 else 1.1, 1.23)
    return mb


def kit_crates_tarp():
    mb = MB()
    for (x, z) in ((-1.5, -1.25), (0.0, -1.25), (-1.5, 0.0), (0.0, 0.0)):
        crate(mb, x, 0.0, z, 1.5, 1.19, 1.25)
    for (x, z) in ((-1.47, -1.22), (0.0, -1.22), (-1.47, 0.0), (0.0, 0.0)):
        crate(mb, x, 1.2, z, 1.47, 1.18, 1.22)
    # tarp draped over the top and down the front (+z) and east (+x) faces with slight sag
    nx, nz = 8, 6
    top = 2.42
    grid = []
    for j in range(nz + 1):
        row = []
        for i in range(nx + 1):
            x = -1.55 + 3.1 * i / nx
            z = -1.3 + 2.6 * j / nz
            sag = 0.05 * math.sin(math.pi * i / nx) * math.sin(math.pi * j / nz)
            row.append((x, top - sag, z))
        grid.append(row)
    for j in range(nz):
        for i in range(nx):
            mb.poly([grid[j + 1][i], grid[j + 1][i + 1], grid[j][i + 1], grid[j][i]], "canvas_green", facing=UP)
    for i in range(nx):
        x0, x1 = -1.55 + 3.1 * i / nx, -1.55 + 3.1 * (i + 1) / nx
        for k in range(3):
            y0, y1 = top - k * 0.45, top - (k + 1) * 0.45
            b0, b1 = 0.04 * math.sin(math.pi * k / 3), 0.04 * math.sin(math.pi * (k + 1) / 3)
            mb.poly([(x0, y1, 1.3 + b1), (x1, y1, 1.3 + b1), (x1, y0, 1.3 + b0), (x0, y0, 1.3 + b0)], "canvas_green", facing=(0, 0, 1))
    for j in range(nz):
        z0, z1 = -1.3 + 2.6 * j / nz, -1.3 + 2.6 * (j + 1) / nz
        for k in range(2):
            y0, y1 = top - k * 0.5, top - (k + 1) * 0.5
            mb.poly([(1.55, y1, z1), (1.55, y1, z0), (1.55, y0, z0), (1.55, y0, z1)], "canvas_green", facing=(1, 0, 0))
    # ropes
    for x in (-0.8, 0.8):
        mb.tube([(x, 0.3, 1.33), (x, top + 0.02, 1.33), (x, top + 0.02, -1.33), (x, 0.3, -1.33)], 0.02, 4, "canvas_cream")
    return mb


def kit_pallet():
    mb = MB()
    L, W = 1.2, 1.0
    for i in range(5):
        z = -W / 2 + 0.05 + i * (W - 0.1) / 4
        fb(mb, -L / 2, 0.12, z - 0.05, L / 2, 0.145, z + 0.05, "wood_planks", skip=("bottom",))
    for x in (-L / 2 + 0.05, 0.0, L / 2 - 0.05):
        fb(mb, x - 0.05, 0.022, -W / 2, x + 0.05, 0.12, W / 2, "wood_planks", skip=("bottom",))
    for z in (-W / 2 + 0.05, 0.0, W / 2 - 0.05):
        fb(mb, -L / 2, 0.0, z - 0.05, L / 2, 0.022, z + 0.05, "wood_planks", skip=("bottom",))
    return mb


def kit_pallet_stack():
    mb = MB()
    p = kit_pallet()
    y = 0.0
    for i in range(5):
        mb.append(p, M_chain(M_translate(0.02 * (i % 2), y, -0.03 * (i % 3)), M_yaw(0.03 * (i - 2))))
        y += 0.145
    # sacks / wrapped goods on top
    fb(mb, -0.5, y, -0.4, 0.1, y + 0.35, 0.1, "canvas_cream", skip=("bottom",))
    fb(mb, 0.15, y, -0.35, 0.55, y + 0.3, 0.4, "canvas_cream", skip=("bottom",))
    crate(mb, -0.5, y, 0.12, 0.6, 0.45, 0.38)
    return mb


def kit_forklift():
    mb = MB()
    Y = "paint_yellow"
    # chassis + counterweight (rear = +z), front (forks) = -z
    fb(mb, -0.55, 0.25, -0.7, 0.55, 0.95, 1.0, Y)
    fb(mb, -0.6, 0.25, 0.75, 0.6, 1.25, 1.2, Y)
    fb(mb, -0.35, 0.95, 0.2, 0.35, 1.05, 0.7, "iron")                      # seat base
    fb(mb, -0.3, 1.05, 0.35, 0.3, 1.15, 0.7, "canvas_cream")
    fb(mb, -0.3, 1.05, 0.62, 0.3, 1.55, 0.72, "iron")
    # overhead guard
    for x in (-0.52, 0.52):
        for z in (-0.35, 0.95):
            fb(mb, x - 0.035, 0.95, z - 0.035, x + 0.035, 2.1, z + 0.035, "iron")
    fb(mb, -0.56, 2.1, -0.4, 0.56, 2.16, 1.0, "iron")
    # steering column + wheel
    mb.tube([(0.0, 0.95, -0.25), (0.0, 1.35, -0.05)], 0.03, 4, "iron")
    mb.lathe([(0.17, 1.33), (0.17, 1.37)], 10, "iron", M=M_chain(M_translate(0.0, 0.0, -0.05)), cap_top=True)
    # mast + carriage + forks
    for x in (-0.38, 0.38):
        fb(mb, x - 0.06, 0.1, -0.86, x + 0.06, 2.3, -0.74, "iron")
    fb(mb, -0.45, 0.2, -0.95, 0.45, 0.7, -0.88, "iron")
    for x in (-0.28, 0.28):
        fb(mb, x - 0.06, 0.08, -2.05, x + 0.06, 0.13, -0.88, "iron")
        fb(mb, x - 0.06, 0.08, -0.95, x + 0.06, 0.8, -0.88, "iron")
    # wheels
    for (x, z, r) in ((-0.6, -0.45, 0.3), (0.6, -0.45, 0.3), (-0.58, 0.85, 0.25), (0.58, 0.85, 0.25)):
        mb.lathe([(r, -0.1), (r, 0.1)], 10, "iron", M=M_chain(M_translate(x, r, z), M_rotz(math.pi / 2)), cap_top=True, cap_bottom=True)
    return mb


def kit_boat(L=5.2, W=1.7, D=0.75, seed=1):
    """Clinker-style rowboat, origin at the waterline centre, bow toward -z."""
    mb = MB()
    st = 12
    pts_outer = []
    ring_n = 7
    for i in range(st + 1):
        t = i / st
        z = -L / 2 + L * t
        half = W / 2 * math.sin(math.pi * min(1.0, max(0.0, 0.08 + 0.92 * t))) ** 0.55
        half = max(0.02, half)
        sheer = 0.28 * ((2 * t - 1) ** 2) + 0.3
        keel = -D * (1.0 - 0.35 * (2 * t - 1) ** 6) + 0.3
        ring = []
        for k in range(ring_n + 1):
            a = math.pi * k / ring_n
            x = -half * math.cos(a)
            yb = keel + (sheer - keel) * (1 - math.sin(a)) ** 0.0 if False else None
            y = sheer - (sheer - keel) * math.sin(a) ** 1.6
            ring.append((x, y, z))
        pts_outer.append(ring)
    # outer hull (smooth), UVs along length
    su, sv = C.TEXEL["wood_planks"]
    verts, faces, uvs = [], [], []
    for i in range(st + 1):
        verts.extend(pts_outer[i])
    Wr = ring_n + 1
    for i in range(st):
        for k in range(ring_n):
            a, b, c, d = i * Wr + k, i * Wr + k + 1, (i + 1) * Wr + k + 1, (i + 1) * Wr + k
            faces.append((a, d, c, b))
            u0, u1 = pts_outer[i][k][2] / su, pts_outer[i + 1][k][2] / su
            v0, v1 = k / ring_n * 1.3, (k + 1) / ring_n * 1.3
            uvs.append(((u0, v0), (u1, v0), (u1, v1), (u0, v1)))
    mb.add_indexed(verts, faces, uvs, "wood_planks", smooth=True)
    # inner hull (slightly smaller, flipped)
    inner = [[(x * 0.92, y + 0.04 if y < 0.25 else y, z) for (x, y, z) in ring] for ring in pts_outer]
    verts, faces, uvs = [], [], []
    for i in range(st + 1):
        verts.extend(inner[i])
    for i in range(st):
        for k in range(ring_n):
            a, b, c, d = i * Wr + k, i * Wr + k + 1, (i + 1) * Wr + k + 1, (i + 1) * Wr + k
            faces.append((a, b, c, d))
            uvs.append(((0, 0), (0.3, 0), (0.3, 0.3), (0, 0.3)))
    mb.add_indexed(verts, faces, uvs, "wood_planks", smooth=True)
    # gunwale rim
    for side in (0, ring_n):
        path = [pts_outer[i][side] for i in range(st + 1)]
        mb.tube([(x, y + 0.02, z) for x, y, z in path], 0.04, 4, "wood_planks")
    # thwarts
    for zt in (-L * 0.22, 0.0, L * 0.25):
        i = int(round((zt + L / 2) / L * st))
        half = abs(pts_outer[i][0][0]) * 0.9
        fb(mb, -half, 0.2, zt - 0.14, half, 0.25, zt + 0.14, "wood_planks")
    # oars resting across
    r = random.Random(seed)
    oa = r.uniform(-0.3, 0.3)
    mb.tube([(-1.3, 0.34, -0.3 + oa), (1.2, 0.3, 0.4 + oa)], 0.028, 4, "wood_planks")
    out = MB()
    out.append(mb, M_yaw(math.pi / 2))          # hull length along local X (bow toward -x)
    return out


def kit_banner_cloth(w, h, sway=0.05, cols=3, rows=6):
    """Hanging cloth quad, top edge at y=0, facing -z (north) at yaw 0; two-sided material."""
    mb = MB()
    grid = []
    for j in range(rows + 1):
        row = []
        for i in range(cols + 1):
            x = -w / 2 + w * i / cols
            y = -h * j / rows
            z = -sway * math.sin(math.pi * i / cols * 1.0 + j * 0.35) * (j / rows)
            row.append((x, y, z))
        grid.append(row)
    for j in range(rows):
        for i in range(cols):
            p = [grid[j + 1][i + 1], grid[j + 1][i], grid[j][i], grid[j][i + 1]]
            uv = [(1 - (i + 1) / cols, 1 - (j + 1) / rows), (1 - i / cols, 1 - (j + 1) / rows), (1 - i / cols, 1 - j / rows),
                  (1 - (i + 1) / cols, 1 - j / rows)]
            mb.poly(p, "banner", uv=uv, facing=(0, 0, -1))
    return mb


# =============================================================================== props manager
class Props:
    def __init__(self, lay: C.Layout, out, kit, cols, buildings=None):
        self.L = lay
        self.out = out
        self.kit = kit
        self.cols = cols
        self.bld = buildings
        self.atl = C.atlas("detail")
        self.fol = C.atlas("foliage")
        self.moved = []
        self.lamp_under_roof = []
        self.loggia_rects = []

    def place(self, key, builder, loc, yaw=0.0, name=None, props=None, scale=1.0):
        ch = C.chunk_of(loc[0], loc[2])
        p = {"wr_cat": "prop", "kit": key}
        if props:
            p.update(props)
        return self.kit.place(key, builder, self.cols[ch], loc, yaw=yaw, name=name, props=p, scale=scale)

    # ------------------------------------------------------------------ layout solids
    def solids(self):
        L = self.L
        groups = {}
        for s in L.solids:
            k = s["kind"]
            if k == "building" or k == "balustrade":
                continue
            groups.setdefault(k, []).append(s)
        for s in groups.get("planter", []):
            self.planter(s)
        for s in groups.get("wall_low", []):
            self.wall_low(s)
        for s in groups.get("stall", []):
            self.stall(s)
        for s in groups.get("crate_stack", []):
            self.crate_stack(s)
        for s in groups.get("container", []):
            self.container(s)
        cols = groups.get("column", [])
        for s in cols:
            if s.get("style") == "banner_post":
                self.banner_pillar(s)
        self.arcades([s for s in cols if s.get("style") == "arcade"])
        fb_ = [s for s in groups.get("fountain", [])]
        st_ = [s for s in groups.get("fountain_statue", [])]
        for s in fb_:
            self.fountain(s, st_)

    # planters ----------------------------------------------------------------------------
    def planter(self, s):
        r = s["rect"]
        h = s["y1"] - s["y0"]
        tree = bool(s.get("tree"))
        key = f"planter_{r.w:.1f}x{r.d:.1f}"

        def build(w=r.w, d=r.d, h=h):
            mb = MB()
            x0, x1, z0, z1 = -w / 2, w / 2, -d / 2, d / 2
            fb(mb, x0 - 0.03, 0.0, z0 - 0.03, x1 + 0.03, 0.18, z1 + 0.03, "stone_ashlar", skip=("bottom",))
            fb(mb, x0, 0.18, z0, x1, h - 0.14, z1, "stone_ashlar", skip=("bottom", "top"))
            t = 0.16
            fb(mb, x0 - 0.05, h - 0.14, z0 - 0.05, x1 + 0.05, h, z0 + t, "stone_trim", skip=("bottom",))
            fb(mb, x0 - 0.05, h - 0.14, z1 - t, x1 + 0.05, h, z1 + 0.05, "stone_trim", skip=("bottom",))
            fb(mb, x0 - 0.05, h - 0.14, z0 + t, x0 + t, h, z1 - t, "stone_trim", skip=("bottom",))
            fb(mb, x1 - t, h - 0.14, z0 + t, x1 + 0.05, h, z1 - t, "stone_trim", skip=("bottom",))
            mb.quad((x0 + t, h - 0.1, z1 - t), (x1 - t, h - 0.1, z1 - t), (x1 - t, h - 0.1, z0 + t), (x0 + t, h - 0.1, z0 + t), "soil")
            for (xa, za, xb, zb) in ((x0 + t, z0 + t, x1 - t, z0 + t), (x1 - t, z0 + t, x1 - t, z1 - t),
                                     (x1 - t, z1 - t, x0 + t, z1 - t), (x0 + t, z1 - t, x0 + t, z0 + t)):
                mb.poly([(xa, h - 0.14, za), (xb, h - 0.14, zb), (xb, h, zb), (xa, h, za)], "stone_trim",
                        facing=((xa + xb) / -2.0, 0, (za + zb) / -2.0))
            return mb
        loc = (r.cx, s["y0"], r.cz)
        self.place(key, build, loc, name=f"planter_{s['id']}")
        ch = C.chunk_of(r.cx, r.cz)
        fm = self.out.mb(ch, "foliage_planters")
        rng = random.Random(hash_str(s["id"]))
        if tree:
            self.tree(r.cx, h - 0.1, r.cz, rng, ch)
            self.shrubs(fm, r, h - 0.1, rng, height=(0.35, 0.6), count=3)
        else:
            self.shrubs(fm, r, h - 0.1, rng, height=(0.6, 0.95), count=5)

    def shrubs(self, fm, r, y, rng, height, count):
        u0, v0, u1, v1 = C.atlas_uv(self.fol, "shrub", inset_px=4)
        f0, g0, f1, g1 = C.atlas_uv(self.fol, "flowers", inset_px=4)
        for i in range(count):
            cx = r.x0 + 0.3 + (r.w - 0.6) * (i + 0.5) / count
            cz = r.cz + rng.uniform(-0.15, 0.15) * r.d
            hh = rng.uniform(*height)
            ww = min(r.w / count + 0.35, 1.3)
            for a in (0.0, math.pi / 2):
                ca, sa = math.cos(a + rng.uniform(-0.3, 0.3)), math.sin(a)
                dx, dz = ca * ww / 2, sa * ww / 2
                dz = max(-r.d / 2 + 0.15, min(r.d / 2 - 0.15, dz))
                p = [(cx - dx, y, cz - dz), (cx + dx, y, cz + dz), (cx + dx, y + hh, cz + dz), (cx - dx, y + hh, cz - dz)]
                if rng.random() < 0.35:
                    fm.poly(p, "foliage", uv=[(f0, g0), (f1, g0), (f1, g1), (f0, g1)])
                else:
                    fm.poly(p, "foliage", uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)])

    def tree(self, x, y, z, rng, ch):
        mb = self.out.mb(ch, "trees")
        top = y + 2.1
        mb.lathe([(0.13, 0.0), (0.1, 1.2), (0.08, 2.1), (0.05, 2.5)], 7, "bark", M=M_translate(x, y, z), cap_top=False)
        for k in range(4):
            a = rng.uniform(0, 2 * math.pi) + k * math.pi / 2
            ln = rng.uniform(0.6, 1.0)
            y0 = y + rng.uniform(1.7, 2.2)
            mb.tube([(x, y0, z), (x + math.cos(a) * ln, y0 + 0.55, z - math.sin(a) * ln)], 0.04, 4, "bark")
        fm = self.out.mb(ch, "foliage_trees")
        u0, v0, u1, v1 = C.atlas_uv(self.fol, rng.choice(["canopy_a", "canopy_b"]), inset_px=6)
        clumps = [(0.0, top + 1.1, 0.0, 1.35)] + [(math.cos(a) * 0.55, top + rng.uniform(0.6, 1.4), -math.sin(a) * 0.55, rng.uniform(0.8, 1.05))
                                                 for a in (rng.uniform(0, 6.28) + k * 2.1 for k in range(3))]
        for (cx, cy, cz, rad) in clumps:
            cx, cz = x + cx, z + cz
            cy = max(cy, 2.55 + rad)
            for a in (0.0, math.pi / 3, 2 * math.pi / 3):
                dx, dz = math.cos(a) * rad, -math.sin(a) * rad
                fm.poly([(cx - dx, cy - rad, cz - dz), (cx + dx, cy - rad, cz + dz), (cx + dx, cy + rad, cz + dz), (cx - dx, cy + rad, cz - dz)],
                        "foliage", uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
            fm.poly([(cx - rad, cy, cz + rad), (cx + rad, cy, cz + rad), (cx + rad, cy, cz - rad), (cx - rad, cy, cz - rad)],
                    "foliage", uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)])

    # low walls -----------------------------------------------------------------------------
    def wall_low(self, s):
        r = s["rect"]
        h = s["y1"] - s["y0"]
        ch = C.chunk_of(r.cx, r.cz)
        mb = self.out.mb(ch, "walls_low")
        rng = random.Random(hash_str(s["id"]))
        if s.get("style") == "concrete_logo":
            fb(mb, r.x0, 0.0, r.z0, r.x1, 0.35, r.z1, "concrete", skip=("bottom",))
            inset = 0.12
            along_x = r.w >= r.d
            if along_x:
                pts_lo = [(r.x0, 0.35, r.z1), (r.x1, 0.35, r.z1), (r.x1, h, r.z1 - inset), (r.x0, h, r.z1 - inset)]
                mb.poly(pts_lo, "concrete", facing=(0, 0.3, 1))
                mb.poly([(r.x1, 0.35, r.z0), (r.x0, 0.35, r.z0), (r.x0, h, r.z0 + inset), (r.x1, h, r.z0 + inset)], "concrete", facing=(0, 0.3, -1))
                mb.quad((r.x0, h, r.z1 - inset), (r.x1, h, r.z1 - inset), (r.x1, h, r.z0 + inset), (r.x0, h, r.z0 + inset), "concrete", facing=UP)
                for x in (r.x0, r.x1):
                    mb.poly([(x, 0.35, r.z0), (x, 0.35, r.z1), (x, h, r.z1 - inset), (x, h, r.z0 + inset)], "concrete",
                            facing=(1 if x == r.x1 else -1, 0, 0))
                u0, v0, u1, v1 = C.atlas_uv(self.atl, "stencil_logo", 4)
                cx = r.cx
                for zf, sgn in ((r.z1 + 0.012, 1), (r.z0 - 0.012, -1)):
                    p = [(cx - 0.45 * sgn, 0.12, zf), (cx + 0.45 * sgn, 0.12, zf), (cx + 0.45 * sgn, 0.9, zf - sgn * 0.1), (cx - 0.45 * sgn, 0.9, zf - sgn * 0.1)]
                    mb.poly(p, "detail", uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)], facing=(0, 0.1, sgn))
                for x0, x1 in ((r.x0, r.x0 + 0.5), (r.x1 - 0.5, r.x1)):
                    for zf, sgn in ((r.z1 + 0.006, 1), (r.z0 - 0.006, -1)):
                        mb.poly([(x0, 0.02, zf), (x1, 0.02, zf), (x1, 0.33, zf), (x0, 0.33, zf)], "hazard", facing=(0, 0, sgn))
            return
        # stone wall with coping + ivy
        fb(mb, r.x0, 0.0, r.z0, r.x1, h - 0.14, r.z1, "stone_ashlar", skip=("bottom",))
        fb(mb, r.x0 - 0.04, h - 0.14, r.z0 - 0.04, r.x1 + 0.04, h, r.z1 + 0.04, "stone_trim", skip=())
        fm = self.out.mb(ch, "foliage_ivy")
        u0, v0, u1, v1 = C.atlas_uv(self.fol, "moss_patch", inset_px=4)
        along_x = r.w >= r.d
        for sgn in (-1, 1):
            if along_x:
                zf = (r.z1 + 0.03) if sgn > 0 else (r.z0 - 0.03)
                a = rng.uniform(r.x0, r.cx - 0.3)
                b = min(r.x1, a + rng.uniform(1.5, 2.1))
                p = [(a, 0.0, zf), (b, 0.0, zf), (b, h - 0.05, zf), (a, h - 0.05, zf)]
                if sgn < 0:
                    p = [p[1], p[0], p[3], p[2]]
                fm.poly(p, "foliage", uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
            else:
                xf = (r.x1 + 0.03) if sgn > 0 else (r.x0 - 0.03)
                a = rng.uniform(r.z0, r.cz - 0.3)
                b = min(r.z1, a + rng.uniform(1.5, 2.1))
                p = [(xf, 0.0, b), (xf, 0.0, a), (xf, h - 0.05, a), (xf, h - 0.05, b)]
                fm.poly(p, "foliage", uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
        # weeds along the base
        w0, x0_, w1, x1_ = C.atlas_uv(self.fol, "weeds", inset_px=4)
        fw = self.out.mb(ch, "foliage_weeds")
        for sgn in (-1, 1):
            if along_x:
                zf = (r.z1 + 0.02) if sgn > 0 else (r.z0 - 0.02)
                fw.poly([(r.x0 + 0.2, 0.0, zf), (r.x1 - 0.2, 0.0, zf), (r.x1 - 0.2, 0.25, zf + 0.06 * sgn), (r.x0 + 0.2, 0.25, zf + 0.06 * sgn)],
                        "foliage", uv=[(w0, x0_), (w1, x0_), (w1, x1_), (w0, x1_)])

    # stalls -----------------------------------------------------------------------------------
    def stall(self, s):
        r = s["rect"]
        canopy = "canvas_red" if s.get("canopy") == "red" else "canvas_green"
        facing_south = r.cz < 0         # front faces the plaza centre
        yaw = 0.0 if facing_south else math.pi
        w, d = r.w, r.d
        key = f"stall_{canopy}_{w:.1f}x{d:.1f}"
        atl = self.atl

        def build():
            mb = MB()
            hw, hd = w / 2, d / 2
            ct = 1.0
            # counter (front = +z)
            fb(mb, -hw, 0.0, hd - 0.85, hw, ct, hd, "wood_planks", skip=("bottom",))
            fb(mb, -hw - 0.03, ct, hd - 0.9, hw + 0.03, ct + 0.06, hd + 0.04, "wood_planks", skip=("bottom",))
            # lower side + back panels
            fb(mb, -hw, 0.0, -hd, -hw + 0.06, ct, hd - 0.85, "wood_planks", skip=("bottom",))
            fb(mb, hw - 0.06, 0.0, -hd, hw, ct, hd - 0.85, "wood_planks", skip=("bottom",))
            fb(mb, -hw, 0.0, -hd, hw, 1.6, -hd + 0.06, "wood_planks", skip=("bottom",))
            # posts
            for x in (-hw + 0.06, hw - 0.06):
                fb(mb, x - 0.05, ct, hd - 0.1, x + 0.05, 2.52, hd, "wood_planks")
                fb(mb, x - 0.05, 1.6, -hd, x + 0.05, 3.05, -hd + 0.1, "wood_planks")
            # cloth sides and back (upper)
            for x, fc in ((-hw + 0.01, (-1, 0, 0)), (hw - 0.01, (1, 0, 0))):
                mb.poly([(x, ct, hd - 0.1), (x, ct, -hd), (x, 3.0, -hd), (x, 2.5, hd - 0.1)] if fc[0] < 0 else
                        [(x, ct, -hd), (x, ct, hd - 0.1), (x, 2.5, hd - 0.1), (x, 3.0, -hd)], canopy, facing=fc)
            mb.poly([(hw, 1.6, -hd - 0.01), (-hw, 1.6, -hd - 0.01), (-hw, 3.0, -hd - 0.01), (hw, 3.0, -hd - 0.01)], canopy, facing=(0, 0, -1))
            # canopy roof: back 3.05 -> front 2.55 at the footprint edge, valance inside the footprint
            mb.poly([(-hw - 0.05, 2.55, hd), (hw + 0.05, 2.55, hd), (hw + 0.05, 3.08, -hd - 0.05), (-hw - 0.05, 3.08, -hd - 0.05)], canopy, facing=UP)
            nv = 10
            for i in range(nv):
                xa = -hw - 0.05 + (w + 0.1) * i / nv
                xb = -hw - 0.05 + (w + 0.1) * (i + 1) / nv
                mb.poly([(xa, 2.55, hd - 0.01), (xb, 2.55, hd - 0.01), (0.5 * (xa + xb), 2.2, hd - 0.01)], canopy, facing=(0, 0, 1))
                mb.poly([(xa, 2.55, hd - 0.01), (0.5 * (xa + xb), 2.2, hd - 0.01), (xb, 2.55, hd - 0.01)], canopy, facing=(0, 0, 1))
            # goods on the counter + shelf behind
            u0, v0, u1, v1 = C.atlas_uv(atl, "goods_fruit", 3)
            for i in range(4):
                x0 = -hw + 0.25 + i * (w - 0.5) / 4
                x1 = x0 + (w - 0.5) / 4 - 0.1
                fb(mb, x0, ct + 0.06, hd - 0.75, x1, ct + 0.28, hd - 0.1, "wood_planks", skip=("bottom", "top"))
                mb.poly([(x0, ct + 0.3, hd - 0.1), (x1, ct + 0.3, hd - 0.1), (x1, ct + 0.3, hd - 0.75), (x0, ct + 0.3, hd - 0.75)], "detail",
                        uv=[(u0 + (u1 - u0) * i / 4, v0), (u0 + (u1 - u0) * (i + 1) / 4, v0), (u0 + (u1 - u0) * (i + 1) / 4, v1), (u0 + (u1 - u0) * i / 4, v1)], facing=UP)
            fb(mb, -hw + 0.1, 1.2, -hd + 0.06, hw - 0.1, 1.26, -hd + 0.5, "wood_planks")
            g0, h0, g1, h1 = C.atlas_uv(atl, "goods_crates", 3)
            mb.poly([(-hw + 0.1, 1.26, -hd + 0.07), (hw - 0.1, 1.26, -hd + 0.07), (hw - 0.1, 1.58, -hd + 0.07), (-hw + 0.1, 1.58, -hd + 0.07)], "detail",
                    uv=[(g0, h0), (g1, h0), (g1, h1), (g0, h1)], facing=(0, 0, 1))
            # hanging sign board on the front post
            s0, t0, s1, t1 = C.atlas_uv(atl, random.Random(int(w * 100 + d)).choice(["shop_fish", "shop_bread", "shop_key"]), 3)
            mb.poly([(-0.35, 2.62, hd + 0.005), (0.35, 2.62, hd + 0.005), (0.35, 2.98, hd - 0.12), (-0.35, 2.98, hd - 0.12)], "detail",
                    uv=[(s0, t0), (s1, t0), (s1, t1), (s0, t1)], facing=(0, 0.3, 1))
            return mb
        self.place(key, build, (r.cx, 0.0, r.cz), yaw=yaw, name=f"stall_{s['id']}")

    # crates / containers ------------------------------------------------------------------------
    def crate_stack(self, s):
        r = s["rect"]
        st = s.get("style", "single")
        builders = {"tarp": kit_crates_tarp, "small": kit_crates_small, "single": kit_crate_single}
        yaw = 0.0 if r.cz < 0 else math.pi
        self.place("crates_" + st, builders.get(st, kit_crate_single), (r.cx, s["y0"], r.cz), yaw=yaw, name=f"crates_{s['id']}")

    def container(self, s):
        r = s["rect"]
        mat = "container_blue" if r.cz < 0 else "container_red"
        along_z = r.d >= r.w
        Lc, Wc, Hc = (r.d, r.w, s["y1"] - s["y0"]) if along_z else (r.w, r.d, s["y1"] - s["y0"])
        key = f"container_{mat}_{Lc:.1f}"

        def build():
            mb = MB()
            hl, hw = Lc / 2, Wc / 2
            # body along local z (length), width along x
            for x, fc in ((-hw, (-1, 0, 0)), (hw, (1, 0, 0))):
                p = [(x, 0.12, hl), (x, 0.12, -hl), (x, Hc - 0.1, -hl), (x, Hc - 0.1, hl)]
                if fc[0] > 0:
                    p = [(x, 0.12, -hl), (x, 0.12, hl), (x, Hc - 0.1, hl), (x, Hc - 0.1, -hl)]
                mb.poly(p, mat, facing=fc, texel=(2.6, 2.6))
            mb.quad((-hw, Hc - 0.02, hl), (hw, Hc - 0.02, hl), (hw, Hc - 0.02, -hl), (-hw, Hc - 0.02, -hl), mat, facing=UP)
            for z, fc in ((hl, (0, 0, 1)), (-hl, (0, 0, -1))):
                mb.poly([(-hw, 0.12, z), (hw, 0.12, z), (hw, Hc - 0.1, z), (-hw, Hc - 0.1, z)], mat, facing=fc)
                # door locking bars
                if z > 0:
                    for x in (-0.75, -0.3, 0.3, 0.75):
                        mb.tube([(x, 0.25, z + 0.04), (x, Hc - 0.25, z + 0.04)], 0.025, 4, "iron")
            # frame rails + corner posts
            for y0, y1 in ((0.0, 0.14), (Hc - 0.14, Hc)):
                for x0, x1 in ((-hw - 0.01, -hw + 0.12), (hw - 0.12, hw + 0.01)):
                    fb(mb, x0, y0, -hl - 0.01, x1, y1, hl + 0.01, "iron")
                for z0, z1 in ((-hl - 0.01, -hl + 0.12), (hl - 0.12, hl + 0.01)):
                    fb(mb, -hw - 0.01, y0, z0, hw + 0.01, y1, z1, "iron")
            for x in (-hw + 0.06, hw - 0.06):
                for z in (-hl + 0.06, hl - 0.06):
                    fb(mb, x - 0.08, 0.0, z - 0.08, x + 0.08, Hc, z + 0.08, "iron")
            return mb
        self.place(key, build, (r.cx, s["y0"], r.cz), yaw=0.0 if along_z else math.pi / 2, name=f"container_{s['id']}")

    # banner posts -------------------------------------------------------------------------------
    def banner_pillar(self, s):
        r = s["rect"]
        w, d = r.w, r.d

        def build():
            mb = MB()
            hw, hd = w / 2, d / 2
            fb(mb, -hw, 0.0, -hd, hw, 0.35, hd, "stone_ashlar", skip=("bottom",))
            fb(mb, -hw + 0.06, 0.35, -hd + 0.06, hw - 0.06, 2.3, hd - 0.06, "stone_ashlar", skip=("bottom", "top"))
            fb(mb, -hw - 0.03, 2.3, -hd - 0.03, hw + 0.03, 2.62, hd + 0.03, "stone_trim", skip=("bottom",))
            mb.lathe([(0.16, 2.62), (0.12, 2.8), (0.08, 2.9), (0.07, 6.3), (0.1, 6.35), (0.0, 6.55)], 8, "iron", cap_top=False)
            mb.lathe([(0.0, 6.45), (0.09, 6.55), (0.0, 6.7)], 8, "bronze", cap_top=False)
            # crossbar with finials (along x)
            mb.tube([(-1.05, 6.0, 0.0), (1.05, 6.0, 0.0)], 0.035, 5, "iron")
            for x in (-1.05, 1.05):
                mb.lathe([(0.0, -0.06), (0.06, 0.0), (0.0, 0.06)], 6, "bronze", M=M_translate(x, 6.0, 0.0), cap_top=False)
            # emblem plaque on the pillar faces
            u0, v0, u1, v1 = C.atlas_uv(self.atl, "sign_emblem", 3)
            for z, fc in ((hd - 0.05, (0, 0, 1)), (-hd + 0.05, (0, 0, -1))):
                p = [(-0.3, 1.1, z + 0.01 * fc[2]), (0.3, 1.1, z + 0.01 * fc[2]), (0.3, 1.7, z + 0.01 * fc[2]), (-0.3, 1.7, z + 0.01 * fc[2])]
                if fc[2] < 0:
                    p = [p[1], p[0], p[3], p[2]]
                mb.poly(p, "detail", uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)], facing=fc)
            return mb
        self.place(f"banner_pillar_{w:.1f}", build, (r.cx, 0.0, r.cz), name=f"bannerpost_{s['id']}")

    # arcades --------------------------------------------------------------------------------------
    def arcades(self, cols):
        if not cols:
            return
        rows = {}
        for s in cols:
            r = s["rect"]
            rows.setdefault(("z", round(r.cz, 2)), []).append(s)
            rows.setdefault(("x", round(r.cx, 2)), []).append(s)
        used = set()
        for (axis, v), ss in sorted(rows.items(), key=lambda kv: -len(kv[1])):
            ss = [s for s in ss]
            if len(ss) < 2:
                continue
            key = (lambda s: s["rect"].cx) if axis == "z" else (lambda s: s["rect"].cz)
            ss.sort(key=key)
            # split into runs of ~6 m spacing
            run = [ss[0]]
            runs_ = []
            for a, b in zip(ss[:-1], ss[1:]):
                if abs(key(b) - key(a) - 6.0) < 0.6:
                    run.append(b)
                else:
                    runs_.append(run)
                    run = [b]
            runs_.append(run)
            for run in runs_:
                if len(run) < 2 or any(id(s) in used for s in run):
                    continue
                for s in run:
                    used.add(id(s))
                self.arcade_run(run, axis)
        for s in cols:
            if id(s) not in used:
                self.column(s)
                used.add(id(s))

    def column(self, s, capital_top=3.2):
        r = s["rect"]
        key = f"column_{r.w:.2f}"

        def build():
            mb = MB()
            hw = r.w / 2
            fb(mb, -hw - 0.05, 0.0, -hw - 0.05, hw + 0.05, 0.3, hw + 0.05, "stone_trim", skip=("bottom",))
            mb.lathe([(hw + 0.03, 0.3), (hw + 0.03, 0.36), (hw, 0.44)], 16, "stone_trim", cap_top=False)
            mb.lathe([(hw, 0.44), (hw * 0.97, capital_top - 0.45)], 16, "stone_trim", cap_top=False)
            mb.lathe([(hw * 0.97, capital_top - 0.45), (hw + 0.03, capital_top - 0.4), (hw * 0.97, capital_top - 0.35),
                      (hw + 0.08, capital_top - 0.18)], 16, "stone_trim", cap_top=False)
            fb(mb, -hw - 0.12, capital_top - 0.18, -hw - 0.12, hw + 0.12, capital_top, hw + 0.12, "stone_trim")
            return mb
        self.place(key, build, (r.cx, 0.0, r.cz), name=f"column_{s['id']}")

    def arcade_run(self, run, axis):
        """Columns + semicircular arches + attic wall + cornice + balustrade; a loggia roof back
        to the building face when one stands within 3 m behind the run."""
        for s in run:
            self.column(s)
        r0, r1 = run[0]["rect"], run[-1]["rect"]
        hw = r0.w / 2
        spring = 3.2
        top = 6.3
        if axis == "z":
            zc = r0.cz
            s0, s1 = r0.x0 - 0.12, r1.x1 + 0.12
            # which side is the building?
            back = None
            for sgn in (-1, 1):
                if self.L.building_at(r0.cx + 0.1, zc + sgn * 2.2):
                    back = sgn
            ch = C.chunk_of(0.5 * (s0 + s1), zc)
            mb = self.out.mb(ch, "arcade")
            faces = []
            for sgn in (-1, 1):
                d = zc + sgn * hw
                if sgn > 0:
                    fr = Frame(s0, d, (1.0, 0.0), (0.0, 1.0), s1 - s0)
                else:
                    fr = Frame(s1, d, (-1.0, 0.0), (0.0, -1.0), s1 - s0)
                faces.append((fr, sgn))
            spans = [(a["rect"].x1 + 0.12, b["rect"].x0 - 0.12) for a, b in zip(run[:-1], run[1:])]
        else:
            xc = r0.cx
            s0, s1 = r0.z0 - 0.12, r1.z1 + 0.12
            back = None
            for sgn in (-1, 1):
                if self.L.building_at(xc + sgn * 2.2, r0.cz + 0.1):
                    back = sgn
            ch = C.chunk_of(xc, 0.5 * (s0 + s1))
            mb = self.out.mb(ch, "arcade")
            faces = []
            for sgn in (-1, 1):
                d = xc + sgn * hw
                if sgn > 0:
                    fr = Frame(d, s1, (0.0, -1.0), (1.0, 0.0), s1 - s0)
                else:
                    fr = Frame(d, s0, (0.0, 1.0), (-1.0, 0.0), s1 - s0)
                faces.append((fr, sgn))
            spans = [(a["rect"].z1 + 0.12, b["rect"].z0 - 0.12) for a, b in zip(run[:-1], run[1:])]
        thick = 2 * hw
        for fr, sgn in faces:
            ops = []
            for a, b in spans:
                # convert absolute span coords into this frame's s
                if axis == "z":
                    sa, sb = (a - s0, b - s0) if sgn > 0 else (s1 - b, s1 - a)
                else:
                    sa, sb = (s1 - b, s1 - a) if sgn > 0 else (a - s0, b - s0)
                rad = (sb - sa) / 2
                ops.append(Opening(sa, sb, 0.0, spring + rad, arch=rad, depth=hw, through=True, kind="passage"))
            wall_with_openings(mb, fr, spring - 0.001, top, ops, [(0.0, 99.0, "stone_ashlar")])
            L = fr.L
            mb.fbox(fr.O, fr.t, fr.n, -0.05, L + 0.05, top - 0.02, top + 0.18, 0.0, 0.14, "stone_trim", skip=("back",))
            mb.fbox(fr.O, fr.t, fr.n, -0.02, L + 0.02, spring + 2.75, spring + 2.95, 0.0, 0.06, "stone_trim", skip=("back",))
            for o in ops:
                cs = 0.5 * (o.s0 + o.s1)
                rad = 0.5 * (o.s1 - o.s0)
                n = 12
                for k in range(n):
                    a0, a1 = math.pi * k / n, math.pi * (k + 1) / n
                    pa = [(cs - rad * math.cos(a0), spring + rad * math.sin(a0)), (cs - rad * math.cos(a1), spring + rad * math.sin(a1)),
                          (cs - (rad + 0.28) * math.cos(a1), spring + (rad + 0.28) * math.sin(a1)),
                          (cs - (rad + 0.28) * math.cos(a0), spring + (rad + 0.28) * math.sin(a0))]
                    mb.poly([fr.P(s_, y_, 0.04) for s_, y_ in pa], "stone_trim", facing=fr.n)
                mb.fbox(fr.O, fr.t, fr.n, cs - 0.16, cs + 0.16, spring + rad - 0.05, spring + rad + 0.38, 0.0, 0.08, "stone_trim", skip=("back",))
        # ends + top of the attic wall
        if axis == "z":
            for x, fc in ((s0, (-1, 0, 0)), (s1, (1, 0, 0))):
                mb.poly([(x, spring, zc - hw), (x, spring, zc + hw), (x, top, zc + hw), (x, top, zc - hw)], "stone_ashlar", facing=fc)
            mb.quad((s0, top, zc + hw), (s1, top, zc + hw), (s1, top, zc - hw), (s0, top, zc - hw), "stone_trim", facing=UP)
        else:
            for z, fc in ((s0, (0, 0, -1)), (s1, (0, 0, 1))):
                mb.poly([(xc - hw, spring, z), (xc + hw, spring, z), (xc + hw, top, z), (xc - hw, top, z)], "stone_ashlar", facing=fc)
            mb.quad((xc - hw, top, s1), (xc + hw, top, s1), (xc + hw, top, s0), (xc - hw, top, s0), "stone_trim", facing=UP)
        # balustrade on top of the attic
        import bl_ground as G
        gb = G.Ground(self.L, self.out)
        if axis == "z":
            gb.balustrade_run((s0 + 0.1, zc), (s1 - 0.1, zc), [(0.0, top + 0.16), (s1 - s0 - 0.2, top + 0.16)], 1, True, "arcade")
        else:
            gb.balustrade_run((xc, s0 + 0.1), (xc, s1 - 0.1), [(0.0, top + 0.16), (s1 - s0 - 0.2, top + 0.16)], 1, False, "arcade")
        # loggia roof back to the building
        if back is not None and axis == "z":
            face_z = zc + back * 2.0 if back else None
            b_z = None
            for dz in [i * 0.05 for i in range(1, 80)]:
                if self.L.building_at(r0.cx + 0.1, zc + back * dz):
                    b_z = zc + back * dz
                    break
            if b_z is not None:
                ceil = spring + (spans[0][1] - spans[0][0]) / 2 + 0.15
                za, zb = sorted((zc + back * hw, b_z))
                mb.quad((s0, ceil, za), (s1, ceil, za), (s1, ceil, zb), (s0, ceil, zb), "stone_trim", facing=DOWN)
                mb.quad((s0, top, zb), (s1, top, zb), (s1, top, za), (s0, top, za), "stone_trim", facing=UP)
                for x, fc in ((s0, (-1, 0, 0)), (s1, (1, 0, 0))):
                    mb.poly([(x, ceil, za), (x, ceil, zb), (x, top, zb), (x, top, za)] if fc[0] < 0 else
                            [(x, ceil, zb), (x, ceil, za), (x, top, za), (x, top, zb)], "stone_ashlar", facing=fc)
                self.loggia_rects.append((Rect(s0, s1, za, zb), ceil))

    # fountain -------------------------------------------------------------------------------------------
    def fountain(self, s, statues):
        r = s["rect"]
        R = s.get("radius", r.w / 2)
        h = s["y1"] - s["y0"]
        ch = C.chunk_of(r.cx, r.cz)
        mb = self.out.mb(ch, "fountain")
        M = M_translate(r.cx, 0.0, r.cz)
        rim_in = R - 0.32
        wl = h - 0.07
        mb.lathe([(R + 0.06, 0.0), (R + 0.06, 0.12), (R, 0.16), (R, h - 0.08), (R + 0.05, h - 0.06), (R + 0.05, h),
                  (rim_in, h), (rim_in, h - 0.05), (rim_in - 0.02, wl - 0.02)], 40, "stone_trim", M=M, cap_top=False, smooth=True)
        wm = MB()
        wm.lathe([(rim_in - 0.02, wl), (0.0, wl)], 40, "water", M=M, cap_top=False, smooth=False)
        # facing up: lathe profile from outer to centre produces top faces
        self.out.special(ch, "water_fountain", wm, {"wr_cat": "water", "water_y": wl})
        for st in statues:
            sr = st.get("radius", st["rect"].w / 2)
            Ms = M_translate(st["rect"].cx, 0.0, st["rect"].cz)
            # pedestal: radius within [sr-0.1, sr+0.1] up to 2.5 m (matches the statue collider)
            mb.lathe([(sr + 0.02, wl - 0.05), (sr, 0.75), (sr - 0.08, 0.85), (sr - 0.06, 1.55), (sr + 0.06, 1.65),
                      (sr + 0.06, 1.75), (sr - 0.05, 1.85), (sr - 0.05, 2.35), (sr + 0.05, 2.45), (sr + 0.02, 2.55)],
                     12, "stone_trim", M=Ms, cap_top=False)
            # upper bowl entirely above 2.5 m
            mb.lathe([(sr + 0.02, 2.55), (0.75, 2.6), (1.05, 2.72), (1.12, 2.84), (1.0, 2.84), (0.4, 2.78)], 24, "stone_trim",
                     M=Ms, cap_top=False)
            bw = MB()
            bw.lathe([(0.98, 2.81), (0.0, 2.81)], 24, "water", M=Ms, cap_top=False)
            self.out.special(ch, "water_fountain_bowl", bw, {"wr_cat": "water", "water_y": 2.81})
            mb.lathe([(0.3, 2.78), (0.26, 3.1), (0.34, 3.2), (0.34, 3.3)], 8, "stone_trim", M=Ms, cap_top=True)
            self.claw_sculpture(mb, st["rect"].cx, 3.3, st["rect"].cz)
            # four lion-head spouts replaced by simple bronze spout pipes feeding the basin
            for k in range(4):
                a_ = k * math.pi / 2 + math.pi / 4
                px, pz = st["rect"].cx + math.cos(a_) * (sr - 0.02), st["rect"].cz - math.sin(a_) * (sr - 0.02)
                qx, qz = st["rect"].cx + math.cos(a_) * (sr + 0.12), st["rect"].cz - math.sin(a_) * (sr + 0.12)
                mb.tube([(px, 1.2, pz), (qx, 1.18, qz)], 0.035, 6, "bronze")

    def claw_sculpture(self, mb, x, y, z):
        """Original three-claw bronze sculpture (the Briarport emblem in the round)."""
        mb.lathe([(0.0, 0.0), (0.26, 0.05), (0.3, 0.2), (0.22, 0.34), (0.0, 0.38)], 10, "bronze", M=M_translate(x, y, z), cap_top=False)
        for k, (ang, lean, ht) in enumerate(((-0.55, 0.55, 1.45), (0.0, 0.12, 1.8), (0.55, 0.55, 1.45))):
            pts = []
            n = 8
            for i in range(n + 1):
                t = i / n
                lx = math.sin(ang) * lean * (t ** 1.5) * 1.1
                lz = math.cos(ang) * 0.0
                pts.append((x + lx, y + 0.3 + ht * t, z + lz + 0.08 * math.sin(math.pi * t)))
            for i in range(n):
                ra = 0.12 * (1 - i / n) + 0.01
                rb = 0.12 * (1 - (i + 1) / n) + 0.01
                seg = MB()
                seg.lathe([(ra, 0.0), (rb, 1.0)], 6, "bronze", cap_top=False)
                a, b = pts[i], pts[i + 1]
                dv = v_sub(b, a)
                ln = math.sqrt(dv[0] ** 2 + dv[1] ** 2 + dv[2] ** 2)
                # orient local +y along dv
                ax = math.atan2(dv[0], dv[1])
                mb.append(seg, M_chain(M_translate(*a), M_rotz(-ax), M_scale(1.0, ln, 1.0)))

    # ------------------------------------------------------------------ decor
    def decor(self):
        n_lamp = 0
        for d in self.L.decor:
            k = d["kind"]
            x, y, z = d["pos"]
            yaw_deg = d.get("yaw", 0.0)
            if k == "lamp_post":
                n_lamp += 1
                self.lamp(x, z, n_lamp)
            elif k == "banner_on_post":
                self.post_banners(x, z, math.radians(yaw_deg))
            elif k == "banner_wall":
                self.wall_banner(x, y, z, math.radians(yaw_deg))
            elif k == "boat":
                self.boat(x, y, z, yaw_deg)
            elif k == "barrel_group":
                x, z = self.resolve(x, z, 0.9, "barrel_group")
                self.place("barrel_group", kit_barrel_group, (x, self.L.ground_at(x, z) or 0.0, z),
                           yaw=(hash_str(f"{x}{z}") % 628) / 100.0)
            elif k == "pallet_stack":
                x, z = self.resolve(x, z, 0.8, "pallet_stack")
                self.place("pallet_stack", kit_pallet_stack, (x, self.L.ground_at(x, z) or 0.0, z), yaw=(hash_str(f"{x}{z}") % 314) / 100.0)
            elif k == "forklift":
                x, z = self.resolve(x, z, 1.4, "forklift")
                self.place("forklift", kit_forklift, (x, self.L.ground_at(x, z) or 0.0, z), yaw=math.radians(yaw_deg))
            elif k == "crane":
                self.crane(x, y, z, yaw_deg)
            elif k == "chimney_smoke":
                self.smoke(x, y, z)

    def resolve(self, x, z, rad, what):
        """Nudge decor off stairs/ramps/solids to the nearest flat floor spot (visual only)."""
        def ok(px, pz):
            g = self.L.ground_at(px, pz)
            if g is None:
                return False
            for a in range(8):
                qx, qz = px + math.cos(a * math.pi / 4) * rad, pz + math.sin(a * math.pi / 4) * rad
                g2 = self.L.ground_at(qx, qz)
                if g2 is None or abs(g2 - g) > 0.01 or self.L.solid_at(qx, qz, y=g + 0.3) is not None:
                    return False
                for r_ in self.L.ramps:
                    if self.L.ramp_height(r_, qx, qz) is not None:
                        return False
            if self.L.solid_at(px, pz, y=g + 0.3) is not None:
                return False
            if self.L.zone_distance(px, pz) < 9.0 + rad:
                return False
            return True
        if ok(x, z):
            return x, z
        for ring in range(1, 40):
            rr = ring * 0.25
            for a in range(max(8, ring * 6)):
                ang = 2 * math.pi * a / max(8, ring * 6)
                px, pz = x + math.cos(ang) * rr, z + math.sin(ang) * rr
                if ok(px, pz):
                    self.moved.append({"decor": what, "from": [x, z], "to": [round(px, 2), round(pz, 2)]})
                    return px, pz
        return x, z

    def lamp(self, x, z, n):
        ch = C.chunk_of(x, z)
        # under a loggia roof -> hanging lantern from the ceiling
        for rect, ceil in self.loggia_rects:
            if rect.contains(x, z):
                self.kit.place(f"lantern_hang_{ceil:.2f}", lambda c=ceil: kit_hanging_lantern(c), self.cols[ch], (x, 0.0, z),
                               name=f"lantern_{n:03d}", props={"wr_cat": "decor"})
                self.kit.place("emissive_lantern_glass", lambda: kit_lamp_glass(3.25, 3.75), self.cols[ch], (x, 0.0, z),
                               name=f"emissive_lantern_{n:03d}", props={"wr_cat": "decor"})
                return
        g = self.L.ground_at(x, z) or 0.0
        self.kit.place("lamp_post", kit_lamp_post, self.cols[ch], (x, g, z), name=f"lamp_post_{n:03d}", props={"wr_cat": "decor"})
        self.kit.place("emissive_lamp_glass", kit_lamp_glass, self.cols[ch], (x, g, z), name=f"emissive_lamp_{n:03d}",
                       props={"wr_cat": "decor"})

    def post_banners(self, x, z, yaw):
        ch = C.chunk_of(x, z)
        cloth = lambda: kit_banner_cloth(0.82, 1.64, sway=0.04)
        for i, side in enumerate((-0.55, 0.55)):
            ox = side * math.cos(yaw)
            oz = -side * math.sin(yaw)
            self.kit.place("banner_cloth_post", cloth, self.cols[ch], (x + ox, 5.96, z + oz), yaw=yaw,
                           name=f"banner_post_{hash_str(f'{x}{z}') % 997:03d}_{i}", props={"wr_cat": "banner"})

    def wall_banner(self, x, y, z, yaw):
        """Banner on a wall bracket (or strung across a street when no wall is at the anchor)."""
        ch = C.chunk_of(x, z)
        fwd = (-math.sin(yaw), -math.cos(yaw))       # facing direction
        # find the wall behind the banner (opposite to facing)
        wall_d = None
        for i in range(1, 40):
            dd = i * 0.05 - 0.5
            px, pz = x - fwd[0] * dd, z - fwd[1] * dd
            if self.L.building_at(px, pz):
                wall_d = dd
                break
        mb = self.out.mb(ch, "banner_hardware")
        w, h = 1.5, 3.0
        top = y + h / 2 + 0.2
        if wall_d is not None and wall_d <= 0.3:
            # face of the wall is at anchor - fwd*wall_d -> hang 0.25 m in front of it
            fx, fz = x - fwd[0] * wall_d + fwd[0] * 0.25, z - fwd[1] * wall_d + fwd[1] * 0.25
            wx, wz = x - fwd[0] * wall_d, z - fwd[1] * wall_d
            mb.tube([(wx, top + 0.25, wz), (fx + fwd[0] * 0.05, top + 0.05, fz + fwd[1] * 0.05)], 0.03, 5, "iron")
            tx, tz = math.cos(yaw), -math.sin(yaw)
            mb.tube([(fx - tx * (w / 2 + 0.12), top, fz - tz * (w / 2 + 0.12)), (fx + tx * (w / 2 + 0.12), top, fz + tz * (w / 2 + 0.12))], 0.03, 5, "iron")
            loc = (fx, top - 0.02, fz)
        else:
            # strung across the street between the two building faces along the banner plane
            tx, tz = math.cos(yaw), -math.sin(yaw)
            a = b = None
            for i in range(1, 200):
                px, pz = x - tx * i * 0.05, z - tz * i * 0.05
                if a is None and self.L.building_at(px, pz):
                    a = (px, pz)
                qx, qz = x + tx * i * 0.05, z + tz * i * 0.05
                if b is None and self.L.building_at(qx, qz):
                    b = (qx, qz)
            if a and b:
                mb.tube([(a[0], top + 0.1, a[1]), (b[0], top + 0.1, b[1])], 0.02, 4, "iron")
            mb.tube([(x - tx * (w / 2 + 0.1), top, z - tz * (w / 2 + 0.1)), (x + tx * (w / 2 + 0.1), top, z + tz * (w / 2 + 0.1))], 0.03, 5, "iron")
            loc = (x, top - 0.02, z)
        self.kit.place("banner_cloth_wall", lambda: kit_banner_cloth(w, h, sway=0.06, cols=3, rows=6), self.cols[ch], loc, yaw=yaw,
                       name=f"banner_wall_{hash_str(f'{x}{z}') % 997:03d}", props={"wr_cat": "banner"})

    def boat(self, x, y, z, yaw_deg):
        w = self.L.water_at(x, z)
        L_ = 5.2
        yaw = math.radians(yaw_deg)
        if w is not None:
            wr = w["rect"]
            # hull length along local x -> world direction (cos yaw, -sin yaw)
            along_x = abs(math.cos(yaw)) > abs(math.sin(yaw))
            room = wr.w if along_x else wr.d
            if room < L_ + 1.0:
                # would sit crosswise in a narrow canal: align with the canal's long axis
                yaw = 0.0 if wr.w > wr.d else math.pi / 2
                self.moved.append({"decor": "boat", "at": [x, z], "yaw_from": yaw_deg, "yaw_to": round(math.degrees(yaw), 1)})
            # keep hull clear of canal walls and bridges along the length
            along_x = abs(math.cos(yaw)) > abs(math.sin(yaw))
            L_eff = L_
            for bf in self.L.floors:
                if bf["surface"] != "wood":
                    continue
                br = bf["rect"]
                if along_x and br.z0 - 0.5 < z < br.z1 + 0.5:
                    gap = min(abs(x - (br.x0 - 0.5)), abs(x - (br.x1 + 0.5)))
                    L_eff = min(L_eff, 2 * gap - 0.3)
                if not along_x and br.x0 - 0.5 < x < br.x1 + 0.5:
                    gap = min(abs(z - (br.z0 - 0.5)), abs(z - (br.z1 + 0.5)))
                    L_eff = min(L_eff, 2 * gap - 0.3)
            L_ = max(3.6, min(L_, L_eff))
        ch = C.chunk_of(x, z)
        key = f"boat_{L_:.1f}"
        self.kit.place(key, lambda L=L_: kit_boat(L=L, W=1.55 if L < 4.5 else 1.7, seed=int(L * 10)), self.cols[ch], (x, y, z),
                       yaw=yaw, name=f"boat_{hash_str(f'{x}{z}') % 997:03d}", props={"wr_cat": "decor"})

    def smoke(self, x, y, z):
        """Chimney reaching the layout emitter height + emit_smoke_* empty at its top."""
        import bl_core as B
        ch = C.chunk_of(x, z)
        roof = self.bld.roof_height_at(x, z) if self.bld else None
        top = y - 0.45                       # pots end exactly at the layout emitter height
        if roof is not None and roof > top - 0.8:
            top = roof + 0.9
        base = (roof - 1.0) if roof is not None else top - 3.0
        mb = self.out.mb(ch, "chimneys_smoke")
        w, d = 1.1, 0.7
        fb(mb, x - w / 2, base, z - d / 2, x + w / 2, top - 0.14, z + d / 2, "brick_brown", skip=("bottom",))
        fb(mb, x - w / 2 - 0.08, top - 0.14, z - d / 2 - 0.08, x + w / 2 + 0.08, top, z + d / 2 + 0.08, "stone_trim", skip=("bottom",))
        for k in (-1, 1):
            mb.cylinder(M_translate(x + k * 0.25, top, z), 0.12, 0.45, 8, "roof_terracotta")
        self.n_smoke = getattr(self, "n_smoke", 0) + 1
        name = f"emit_smoke_{self.n_smoke:02d}"
        B.empty_object(name, self.cols[ch], (x, top + 0.45, z), props={"wr_cat": "emit_smoke", "layout_pos": [x, y, z]})

    # crane -------------------------------------------------------------------------------------------------
    def crane(self, x, y, z, yaw_deg):
        """Portal jib crane outside the playable boundary. Layout yaw read as a compass bearing:
        forward (jib) direction = (sin(b), -cos(b)) in (x, z)."""
        b = math.radians(yaw_deg)
        fdx, fdz = math.sin(b), -math.cos(b)
        yaw = math.atan2(-fdx, -fdz)                  # Godot yaw whose forward (-Z) = (fdx, fdz)
        ch = C.chunk_of(x, z)
        mb = MB()
        Y = "paint_yellow"
        # portal: 4 legs + girders
        for lx in (-3.0, 3.0):
            for lz in (-3.0, 3.0):
                fb(mb, lx - 0.3, 0.0, lz - 0.3, lx + 0.3, 8.0, lz + 0.3, Y)
                fb(mb, lx - 0.45, 0.0, lz - 0.45, lx + 0.45, 0.4, lz + 0.45, "concrete")
        for lz in (-3.0, 3.0):
            fb(mb, -3.3, 7.3, lz - 0.35, 3.3, 8.2, lz + 0.35, Y)
        for lx in (-3.0, 3.0):
            fb(mb, lx - 0.35, 7.3, -3.3, lx + 0.35, 8.2, 3.3, Y)
        for lx in (-3.0, 3.0):
            mb.tube([(lx, 0.5, -3.0), (lx, 7.2, 3.0)], 0.12, 5, Y)
            mb.tube([(lx, 0.5, 3.0), (lx, 7.2, -3.0)], 0.12, 5, Y)
        mb.lathe([(2.2, 8.2), (2.2, 8.7)], 16, "iron", cap_top=True)
        # machinery house (rear) + cab (front)
        fb(mb, -1.8, 8.7, -1.2, 1.8, 12.2, 3.6, Y)
        fb(mb, -1.9, 12.2, -1.3, 1.9, 12.4, 3.7, "iron")
        fb(mb, -1.6, 8.7, 3.6, 1.6, 11.2, 4.6, "concrete")              # counterweight
        fb(mb, -1.4, 9.4, -2.9, 0.4, 11.6, -1.2, Y)                      # cab
        u0, v0, u1, v1 = C.atlas_uv(self.atl, "win_industrial", 3)
        mb.poly([(-1.35, 10.1, -2.92), (0.35, 10.1, -2.92), (0.35, 11.4, -2.92), (-1.35, 11.4, -2.92)], "detail",
                uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)], facing=(0, 0, -1))
        u0, v0, u1, v1 = C.atlas_uv(self.atl, "sign_briarport", 3)
        for xs, fc in ((1.81, (1, 0, 0)), (-1.81, (-1, 0, 0))):
            p = [(xs, 10.6, 3.2), (xs, 10.6, 0.2), (xs, 11.7, 0.2), (xs, 11.7, 3.2)] if fc[0] > 0 else \
                [(xs, 10.6, 0.2), (xs, 10.6, 3.2), (xs, 11.7, 3.2), (xs, 11.7, 0.2)]
            mb.poly(p, "detail", uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)], facing=fc)
        # A-frame
        for lx in (-1.2, 1.2):
            mb.tube([(lx, 12.4, 2.8), (0.0, 16.5, 1.0)], 0.12, 6, Y)
            mb.tube([(lx, 12.4, -0.6), (0.0, 16.5, 1.0)], 0.12, 6, Y)
        # lattice jib: pivot at (0, 11.0, -1.3), elevation 36 deg, length 17 m toward -z
        el = math.radians(36.0)
        Lj = 17.0
        piv = (0.0, 11.0, -1.3)
        tip = (0.0, piv[1] + Lj * math.sin(el), piv[2] - Lj * math.cos(el))
        chords = []
        for ox, oy in ((-0.55, -0.4), (0.55, -0.4), (-0.3, 0.35), (0.3, 0.35)):
            taper = 0.35
            a = (piv[0] + ox, piv[1] + oy, piv[2])
            bb = (tip[0] + ox * taper, tip[1] + oy * taper, tip[2])
            chords.append((a, bb))
            mb.tube([a, bb], 0.08, 5, Y)
        nb = 9
        for i in range(nb):
            t0, t1 = i / nb, (i + 1) / nb
            for (a0, b0), (a1, b1) in ((chords[0], chords[2]), (chords[1], chords[3]), (chords[0], chords[1]), (chords[2], chords[3])):
                p0 = v_add(a0, v_mul(v_sub(b0, a0), t0))
                p1 = v_add(a1, v_mul(v_sub(b1, a1), t1))
                mb.tube([p0, p1], 0.045, 4, Y)
        # luffing ties from the A-frame apex to the jib tip
        mb.tube([(0.0, 16.5, 1.0), (0.0, tip[1] + 0.3, tip[2] + 0.2)], 0.04, 4, "iron")
        # hoist rope + hook block + load (a pallet of crates) hanging to ~11.5 m
        hook_y = 13.2
        mb.tube([(0.0, tip[1] - 0.3, tip[2]), (0.0, hook_y + 0.4, tip[2])], 0.03, 4, "iron")
        fb(mb, -0.25, hook_y, tip[2] - 0.2, 0.25, hook_y + 0.5, tip[2] + 0.2, Y)
        for sx in (-0.6, 0.6):
            for sz in (-0.5, 0.5):
                mb.tube([(0.0, hook_y, tip[2]), (sx, hook_y - 1.2, tip[2] + sz)], 0.015, 3, "iron")
        crate(mb, -0.62, hook_y - 2.3, tip[2] - 0.52, 1.24, 1.1, 1.04)
        mb2 = MB()
        mb2.append(mb, M_chain(M_translate(x, y, z), M_yaw(yaw)))
        self.out.special(ch, "crane_yard", mb2, {"wr_cat": "decor", "yaw_compass_deg": yaw_deg})
        wx, wz = M_apply(M_chain(M_translate(x, y, z), M_yaw(yaw)), (0.0, 0.0, tip[2]))[0::2]
        self.crane_hook = (wx, hook_y - 2.3, wz)
