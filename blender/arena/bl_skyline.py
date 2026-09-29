"""Skyline chunk: landmarks from the layout decor (clock tower, cathedrals, tower) plus a ring
of low-detail city blocks, ground and harbour water outside the 144 x 112 m footprint.
Everything here is outside playable space (except the clock tower rising out of a roof)."""
from __future__ import annotations

import math
import random

import common as C
from bl_core import MB, M_translate, M_yaw, M_chain
from bl_arch import hash_str
from common import Rect

UP = (0.0, 1.0, 0.0)


def band_uv(band, u0, u1, h):
    """UVs on the skyline facade texture: 4 bands of 12 m stacked vertically (v)."""
    v0 = 1.0 - (band + 1) * 0.25
    return v0, v0 + 0.25 * min(1.0, h / 12.0)


class Skyline:
    def __init__(self, lay: C.Layout, out, buildings=None):
        self.L = lay
        self.out = out
        self.bld = buildings
        self.atl = C.atlas("detail")
        self.occupied = []

    def mb(self, key):
        return self.out.mb("skyline", key)

    # ------------------------------------------------------------------ landmarks
    def landmarks(self):
        for d in self.L.decor:
            k = d["kind"]
            x, _, z = d["pos"]
            if k == "skyline_clock_tower":
                self.clock_tower(x, z)
            elif k == "skyline_cathedral":
                self.cathedral(x, z)
            elif k == "skyline_tower":
                self.round_tower(x, z)

    def clock_tower(self, x, z):
        mb = self.mb("landmarks")
        w = 5.6
        h = 30.0
        x0, x1, z0, z1 = x - w / 2, x + w / 2, z - w / 2, z + w / 2
        base = 6.0          # hidden inside the block below its roofs
        mb.box(x0, base, z0, x1, h, z1, "brick_red", skip=("bottom", "top"))
        for y in (14.0, 22.0, h - 0.4):
            mb.box(x0 - 0.2, y, z0 - 0.2, x1 + 0.2, y + 0.45, z1 + 0.2, "stone_trim", skip=())
        for sx in (x0, x1 - 0.5):
            for sz in (z0, z1 - 0.5):
                mb.box(sx - 0.03, base, sz - 0.03, sx + 0.53, h, sz + 0.53, "stone_ashlar", skip=("bottom", "top"))
        # clock faces + belfry openings on all four sides
        u0, v0, u1, v1 = C.atlas_uv(self.atl, "clock", 3)
        b0, c0, b1, c1 = C.atlas_uv(self.atl, "win_arch", 3)
        for (px, pz, tx, tz, nx, nz) in ((x, z1 + 0.21, 1, 0, 0, 1), (x, z0 - 0.21, -1, 0, 0, -1),
                                         (x1 + 0.21, z, 0, -1, 1, 0), (x0 - 0.21, z, 0, 1, -1, 0)):
            r = 1.5
            yc = 18.2
            mb.poly([(px - tx * r, yc - r, pz - tz * r), (px + tx * r, yc - r, pz + tz * r), (px + tx * r, yc + r, pz + tz * r),
                     (px - tx * r, yc + r, pz - tz * r)], "detail", uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)], facing=(nx, 0, nz))
            for off in (-1.1, 1.1):
                cx, cz = px + tx * off - nx * 0.2, pz + tz * off - nz * 0.2
                mb.poly([(cx - tx * 0.6, 23.5, cz - tz * 0.6), (cx + tx * 0.6, 23.5, cz + tz * 0.6), (cx + tx * 0.6, 27.8, cz + tz * 0.6),
                         (cx - tx * 0.6, 27.8, cz - tz * 0.6)], "detail", uv=[(b0, c0), (b1, c0), (b1, c1), (b0, c1)], facing=(nx, 0, nz))
        # spire
        top = h + 9.5
        o = 0.35
        pts = [(x0 - o, h, z1 + o), (x1 + o, h, z1 + o), (x1 + o, h, z0 - o), (x0 - o, h, z0 - o)]
        for i in range(4):
            a, b = pts[i], pts[(i + 1) % 4]
            mb.poly([a, b, (x, top, z)], "roof_metal")
        mb.lathe([(0.15, top - 0.3), (0.3, top), (0.08, top + 1.2), (0.0, top + 2.2)], 8, "bronze", M=M_translate(x, 0.0, z), cap_top=False)
        self.occupied.append(Rect(x0 - 1, x1 + 1, z0 - 1, z1 + 1))

    def cathedral(self, x, z):
        """Nave + aisles + twin-tower west front facing the arena, crossing dome."""
        mb = self.mb("landmarks")
        facing = -1 if z > 0 else 1          # +1: facade faces +z (south) toward the arena (north cathedral)
        zf = z - 4.0 * facing                 # facade plane
        L = 38.0
        z_far = zf - facing * L
        za, zb = sorted((zf, z_far))
        nave_w, nave_h = 13.0, 20.0
        aisle_w, aisle_h = 5.5, 11.0
        # aisles
        for sx in (-1, 1):
            xa, xb = sorted((x + sx * nave_w / 2, x + sx * (nave_w / 2 + aisle_w)))
            mb.box(xa, 0.0, za, xb, aisle_h, zb, "stone_ashlar", skip=("bottom",))
            # lean-to roof
            xi = x + sx * nave_w / 2
            xo = x + sx * (nave_w / 2 + aisle_w + 0.4)
            p = [(xo, aisle_h, zb), (xo, aisle_h, za), (xi, aisle_h + 3.0, za), (xi, aisle_h + 3.0, zb)]
            mb.poly(p, "roof_metal", facing=(sx, 1.5, 0))
            # buttresses
            for k in range(6):
                zz = za + 3 + k * (zb - za - 6) / 5
                bx = x + sx * (nave_w / 2 + aisle_w)
                mb.box(min(bx, bx + sx * 1.0), 0.0, zz - 0.5, max(bx, bx + sx * 1.0), aisle_h - 1.0, zz + 0.5, "stone_ashlar", skip=("bottom",))
        # nave
        mb.box(x - nave_w / 2, 0.0, za, x + nave_w / 2, nave_h, zb, "stone_ashlar", skip=("bottom",))
        tp = math.tan(math.radians(40))
        ridge = nave_h + nave_w / 2 * tp
        for sx in (-1, 1):
            e = x + sx * (nave_w / 2 + 0.4)
            p = [(e, nave_h - 0.3, za), (e, nave_h - 0.3, zb), (x, ridge, zb), (x, ridge, za)]
            mb.poly(p, "roof_metal", facing=(sx, 1.2, 0))
        for zz in (za, zb):
            mb.poly([(x - nave_w / 2, nave_h, zz), (x + nave_w / 2, nave_h, zz), (x, ridge, zz)], "stone_ashlar",
                    facing=(0, 0, 1 if zz == zb else -1))
        # clerestory windows
        b0, c0, b1, c1 = C.atlas_uv(self.atl, "win_hall", 3)
        for sx in (-1, 1):
            xf = x + sx * (nave_w / 2 + 0.02)
            for k in range(7):
                zz = za + 4 + k * (zb - za - 8) / 6
                p = [(xf, 13.0, zz - 0.9), (xf, 13.0, zz + 0.9), (xf, 18.5, zz + 0.9), (xf, 18.5, zz - 0.9)]
                mb.poly(p, "detail", uv=[(b0, c0), (b1, c0), (b1, c1), (b0, c1)], facing=(sx, 0, 0))
        # twin towers at the facade
        tw = 6.5
        for sx in (-1, 1):
            cx = x + sx * (nave_w / 2 + aisle_w - tw / 2 + 0.5)
            z0_, z1_ = sorted((zf, zf - facing * tw))
            mb.box(cx - tw / 2, 0.0, z0_, cx + tw / 2, 33.0, z1_, "stone_ashlar", skip=("bottom",))
            mb.box(cx - tw / 2 - 0.3, 33.0, z0_ - 0.3, cx + tw / 2 + 0.3, 33.6, z1_ + 0.3, "stone_trim", skip=())
            czc = 0.5 * (z0_ + z1_)
            for i in range(8):
                a0 = 2 * math.pi * i / 8
                a1 = 2 * math.pi * (i + 1) / 8
                r_ = tw * 0.55
                mb.poly([(cx + math.cos(a0) * r_, 33.6, czc - math.sin(a0) * r_), (cx + math.cos(a1) * r_, 33.6, czc - math.sin(a1) * r_),
                         (cx, 46.0, czc)], "roof_metal")
            mb.lathe([(0.2, 45.5), (0.35, 46.2), (0.0, 48.0)], 8, "bronze", M=M_translate(cx, 0.0, czc), cap_top=False)
            for k in range(3):
                yy = 12 + k * 7.0
                zfc = (z1_ if facing > 0 else z0_) + facing * 0.02
                mb.poly([(cx - 0.8, yy, zfc), (cx + 0.8, yy, zfc), (cx + 0.8, yy + 4.5, zfc), (cx - 0.8, yy + 4.5, zfc)], "detail",
                        uv=[(b0, c0), (b1, c0), (b1, c1), (b0, c1)], facing=(0, 0, facing))
        # rose window + portal on the facade
        r0, s0, r1, s1 = C.atlas_uv(self.atl, "win_round", 3)
        d0, e0, d1, e1 = C.atlas_uv(self.atl, "door_arch", 3)
        zfc = zf + facing * 0.03
        mb.poly([(x - 2.8, 12.0, zfc), (x + 2.8, 12.0, zfc), (x + 2.8, 17.6, zfc), (x - 2.8, 17.6, zfc)], "detail",
                uv=[(r0, s0), (r1, s0), (r1, s1), (r0, s1)], facing=(0, 0, facing))
        mb.poly([(x - 2.0, 0.0, zfc), (x + 2.0, 0.0, zfc), (x + 2.0, 6.5, zfc), (x - 2.0, 6.5, zfc)], "detail",
                uv=[(d0, e0), (d1, e0), (d1, e1), (d0, e1)], facing=(0, 0, facing))
        # crossing dome
        zc = zf - facing * L * 0.62
        M = M_translate(x, ridge - 1.0, zc)
        mb.lathe([(5.0, 0.0), (5.0, 4.0), (5.4, 4.3)], 16, "stone_ashlar", M=M, cap_top=False)
        prof = [(5.4, 4.3)] + [(5.4 * math.cos(a) + 0.01, 4.3 + 5.8 * math.sin(a)) for a in (i * math.pi / 2 / 8 for i in range(1, 9))]
        mb.lathe(prof, 16, "bronze", M=M, cap_top=False)
        mb.lathe([(0.9, 10.1), (0.9, 11.8), (0.0, 13.8)], 8, "bronze", M=M, cap_top=False)
        self.occupied.append(Rect(x - nave_w / 2 - aisle_w - 2, x + nave_w / 2 + aisle_w + 2, za - 2, zb + 2))

    def round_tower(self, x, z):
        mb = self.mb("landmarks")
        M = M_translate(x, 0.0, z)
        R = 3.8
        mb.lathe([(R + 0.3, 0.0), (R, 1.5), (R, 22.0), (R + 0.4, 22.3), (R + 0.4, 23.2)], 20, "stone_ashlar", M=M, cap_top=False)
        mb.lathe([(R + 0.4, 23.2), (R - 0.3, 23.2)], 20, "stone_trim", M=M, cap_top=False)
        for i in range(12):
            a0 = 2 * math.pi * i / 12
            a1 = a0 + 2 * math.pi / 12 * 0.55
            p0 = (x + math.cos(a0) * (R + 0.4), z - math.sin(a0) * (R + 0.4))
            p1 = (x + math.cos(a1) * (R + 0.4), z - math.sin(a1) * (R + 0.4))
            mb.poly([(p0[0], 23.2, p0[1]), (p1[0], 23.2, p1[1]), (p1[0], 24.2, p1[1]), (p0[0], 24.2, p0[1])], "stone_ashlar",
                    facing=(math.cos((a0 + a1) / 2), 0, -math.sin((a0 + a1) / 2)))
        prof = [(R - 0.2, 23.4), (0.0, 31.0)]
        mb.lathe(prof, 20, "roof_terracotta", M=M, cap_top=False)
        b0, c0, b1, c1 = C.atlas_uv(self.atl, "win_arch", 3)
        for k in range(4):
            a = k * math.pi / 2 + 0.4
            nx, nz = math.cos(a), -math.sin(a)
            tx, tz = -nz, nx
            for yy in (8.0, 15.0):
                cx, cz = x + nx * (R + 0.02), z + nz * (R + 0.02)
                mb.poly([(cx - tx * 0.5, yy, cz - tz * 0.5), (cx + tx * 0.5, yy, cz + tz * 0.5), (cx + tx * 0.5, yy + 2.0, cz + tz * 0.5),
                         (cx - tx * 0.5, yy + 2.0, cz - tz * 0.5)], "detail", uv=[(b0, c0), (b1, c0), (b1, c1), (b0, c1)], facing=(nx, 0, nz))
        self.occupied.append(Rect(x - R - 1.5, x + R + 1.5, z - R - 1.5, z + R + 1.5))

    # ------------------------------------------------------------------ city ring
    def city(self):
        """Rows of simple houses around the arena (outside the footprint), harbour to the east."""
        rng = random.Random(4242)
        mb = self.mb("city")
        blocks = []
        # north band
        for zc in (-78.0, -104.0):
            blocks += self.row(-150, 70, zc, 18.0, "x", rng)
        # south band
        for zc in (72.0, 98.0):
            blocks += self.row(-150, 30, zc, 18.0, "x", rng)
        # west band
        for xc in (-86.0, -112.0, -138.0):
            blocks += self.row(-60, 60, xc, 18.0, "z", rng)
        for b in blocks:
            self.house(mb, *b)
        # ground plane (streets) outside the footprint, excluding the harbour
        g = self.mb("city_ground")
        y = -0.02
        for (x0, x1, z0, z1) in ((-170.0, 76.0, -130.0, -56.5), (-170.0, 76.0, 56.5, 130.0),
                                 (-170.0, -60.5, -56.5, 56.5), (60.5, 76.0, -56.5, 56.5)):
            g.quad((x0, y, z1), (x1, y, z1), (x1, y, z0), (x0, y, z0), "paving_cobble", texel=(6.0, 6.0), facing=UP)
        # harbour water east of the arena + quay wall
        w = MB()
        w.quad((76.0, -1.0, 130.0), (240.0, -1.0, 130.0), (240.0, -1.0, -130.0), (76.0, -1.0, -130.0), "water", facing=UP)
        self.out.special("skyline", "water_harbour", w, {"wr_cat": "water", "water_y": -1.0})
        q = self.mb("city_quay")
        q.quad((76.0, -3.0, -130.0), (76.0, -3.0, 130.0), (76.0, 0.0, 130.0), (76.0, 0.0, -130.0), "stone_canal", facing=(1, 0, 0))
        # far shore warehouses across the harbour
        for i in range(9):
            zc = -120 + i * 30 + rng.uniform(-4, 4)
            self.house(mb, 200.0, zc, 22.0, 26.0, rng.uniform(10, 16), "x", 2, "brick", True)

    def row(self, a0, a1, c, depth, axis, rng):
        out = []
        a = a0
        while a < a1:
            w = rng.uniform(7.0, 12.0)
            h = rng.uniform(9.0, 17.0)
            band = rng.choice([0, 1, 2, 3, 0, 1])
            if axis == "x":
                cx, cz = a + w / 2, c
                wx, wz = w, depth * rng.uniform(0.75, 1.0)
            else:
                cx, cz = c, a + w / 2
                wx, wz = depth * rng.uniform(0.75, 1.0), w
            r = Rect(cx - wx / 2, cx + wx / 2, cz - wz / 2, cz + wz / 2)
            ok = not any(r.x0 < o.x1 and r.x1 > o.x0 and r.z0 < o.z1 and r.z1 > o.z0 for o in self.occupied)
            if ok and not (r.x1 > -72.5 and r.x0 < 72.5 and r.z1 > -58.5 and r.z0 < 58.5):
                out.append((cx, cz, wx, wz, h, axis, band, "plaster", False))
            a += w + rng.uniform(0.0, 0.6) + (rng.uniform(5.0, 8.0) if rng.random() < 0.18 else 0.0)
        return out

    def house(self, mb, cx, cz, wx, wz, h, axis, band, kind, flat):
        x0, x1, z0, z1 = cx - wx / 2, cx + wx / 2, cz - wz / 2, cz + wz / 2
        faces = [((x0, z1), (x1, z1), (0, 0, 1)), ((x1, z1), (x1, z0), (1, 0, 0)), ((x1, z0), (x0, z0), (0, 0, -1)), ((x0, z0), (x0, z1), (-1, 0, 0))]
        u_off = (hash_str(f"{cx:.1f}{cz:.1f}") % 97) / 97.0
        for (a, b, n) in faces:
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            v0, v1 = band_uv(band, 0, 1, h)
            u0 = u_off
            u1 = u_off + L / 24.0
            mb.poly([(a[0], 0.0, a[1]), (b[0], 0.0, b[1]), (b[0], h, b[1]), (a[0], h, a[1])], "skyline",
                    uv=[(u0, v0), (u1, v0), (u1, v0 + (v1 - v0)), (u0, v1)], facing=n)
        if flat:
            mb.quad((x0, h, z1), (x1, h, z1), (x1, h, z0), (x0, h, z0), "roof_metal", facing=UP)
            return
        tp = math.tan(math.radians(33))
        o = 0.4
        if wx >= wz:
            rise = wz / 2 * tp
            mb.poly([(x0 - o, h - o * tp, z1 + o), (x1 + o, h - o * tp, z1 + o), (x1 + o, h + rise, cz), (x0 - o, h + rise, cz)], "roof_terracotta", facing=(0, 1, tp))
            mb.poly([(x1 + o, h - o * tp, z0 - o), (x0 - o, h - o * tp, z0 - o), (x0 - o, h + rise, cz), (x1 + o, h + rise, cz)], "roof_terracotta", facing=(0, 1, -tp))
            for xx, sg in ((x0, -1), (x1, 1)):
                mb.poly([(xx, h, z0), (xx, h, z1), (xx, h + rise, cz)], "plaster_cream" if band != 2 else "brick_red", facing=(sg, 0, 0))
        else:
            rise = wx / 2 * tp
            mb.poly([(x1 + o, h - o * tp, z1 + o), (x1 + o, h - o * tp, z0 - o), (cx, h + rise, z0 - o), (cx, h + rise, z1 + o)], "roof_terracotta", facing=(tp, 1, 0))
            mb.poly([(x0 - o, h - o * tp, z0 - o), (x0 - o, h - o * tp, z1 + o), (cx, h + rise, z1 + o), (cx, h + rise, z0 - o)], "roof_terracotta", facing=(-tp, 1, 0))
            for zz, sg in ((z0, -1), (z1, 1)):
                mb.poly([(x0, h, zz), (x1, h, zz), (cx, h + rise, zz)], "plaster_cream" if band != 2 else "brick_red", facing=(0, 0, sg))

    def build(self):
        self.landmarks()
        self.city()
