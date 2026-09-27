"""Shared (bpy-free) definitions for the Briarport art pipeline: paths, material table,
texel densities and layout queries. Importable from Blender's Python and the project venv.

Coordinate convention used by ALL generation code: layout / Godot space (X east, Y up,
Z south, metres). Conversion to Blender happens only when meshes/objects are created:
    bx = x, by = -z, bz = y        (a proper rotation; glTF export (+Y up) converts back)
"""
from __future__ import annotations

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LAYOUT_PATH = os.path.join(ROOT, "game", "data", "arena", "briarport_layout.json")
ASSET_DIR = os.path.join(ROOT, "game", "assets", "arena")
TEX_DIR = os.path.join(ASSET_DIR, "textures")
EVIDENCE_DIR = os.path.join(ROOT, "evidence", "arena")
BLEND_PATH = os.path.join(HERE, "briarport.blend")
MANIFEST_PATH = os.path.join(ASSET_DIR, "arena_art.json")

# metres covered by one UV tile (u, v) per texture family (must match gen_textures.py output)
TEXEL = {
    "brick": (2.0, 2.0), "plaster": (3.0, 3.0), "stone_ashlar": (3.0, 3.0), "stone_trim": (2.0, 2.0),
    "stone_canal": (4.0, 3.0), "roof_terracotta": (2.0, 2.0), "paving_flag": (5.0, 5.0),
    "paving_cobble": (4.0, 4.0), "paving_concrete": (8.0, 8.0), "wood_planks": (2.0, 2.0),
    "metal_deck": (1.5, 1.5), "iron": (1.0, 1.0), "paint_yellow": (2.0, 2.0), "container": (2.6, 2.6),
    "hazard": (1.0, 1.0), "canvas": (2.0, 2.0), "concrete": (2.0, 2.0), "soil": (1.0, 1.0),
    "bronze": (1.0, 1.0), "bark": (1.0, 2.0), "water": (6.0, 6.0), "skyline": (24.0, 48.0),
    "roof_metal": (2.0, 2.0), "banner": (1.0, 1.0), "puddle": (1.0, 1.0), "foliage": (1.0, 1.0),
    "detail": (1.0, 1.0), "ironwork": (1.0, 1.0), "flat": (1.0, 1.0),
}


def _m(albedo, normal=None, orm=None, texel="flat", **kw):
    d = {"albedo": albedo, "normal": normal, "orm": orm, "texel": texel}
    d.update(kw)
    return d


# Material table (<= 40). Texture names are file stems in game/assets/arena/textures.
MATERIALS = {
    "brick_red": _m("brick_red_albedo", "brick_normal", "brick_orm", "brick"),
    "brick_brown": _m("brick_brown_albedo", "brick_normal", "brick_orm", "brick"),
    "plaster_cream": _m("plaster_cream_albedo", "plaster_normal", "plaster_orm", "plaster"),
    "plaster_ochre": _m("plaster_ochre_albedo", "plaster_normal", "plaster_orm", "plaster"),
    "plaster_rose": _m("plaster_rose_albedo", "plaster_normal", "plaster_orm", "plaster"),
    "plaster_white": _m("plaster_white_albedo", "plaster_normal", "plaster_orm", "plaster"),
    "stone_ashlar": _m("stone_ashlar_albedo", "stone_ashlar_normal", "stone_ashlar_orm", "stone_ashlar"),
    "stone_trim": _m("stone_trim_albedo", "stone_trim_normal", "stone_trim_orm", "stone_trim"),
    "stone_canal": _m("stone_canal_albedo", "stone_canal_normal", "stone_canal_orm", "stone_canal"),
    "roof_terracotta": _m("roof_terracotta_albedo", "roof_terracotta_normal", "roof_terracotta_orm", "roof_terracotta"),
    "roof_metal": _m("roof_metal_albedo", "roof_metal_normal", "roof_metal_orm", "roof_metal"),
    "paving_flag": _m("paving_flag_albedo", "paving_flag_normal", "paving_flag_orm", "paving_flag"),
    "paving_cobble": _m("paving_cobble_albedo", "paving_cobble_normal", "paving_cobble_orm", "paving_cobble"),
    "paving_concrete": _m("paving_concrete_albedo", "paving_concrete_normal", "paving_concrete_orm", "paving_concrete"),
    "wood_planks": _m("wood_planks_albedo", "wood_planks_normal", "wood_planks_orm", "wood_planks"),
    "metal_deck": _m("metal_deck_albedo", "metal_deck_normal", "metal_deck_orm", "metal_deck"),
    "iron": _m("iron_albedo", "iron_normal", "iron_orm", "iron"),
    "paint_yellow": _m("paint_yellow_albedo", "paint_yellow_normal", "paint_yellow_orm", "paint_yellow"),
    "container_blue": _m("container_blue_albedo", "container_normal", "container_orm", "container"),
    "container_red": _m("container_red_albedo", "container_normal", "container_orm", "container"),
    "container_green": _m("container_green_albedo", "container_normal", "container_orm", "container"),
    "hazard": _m("hazard_albedo", "hazard_normal", "hazard_orm", "hazard"),
    "canvas_red": _m("canvas_red_albedo", "canvas_normal", "canvas_orm", "canvas", two_sided=True),
    "canvas_green": _m("canvas_green_albedo", "canvas_normal", "canvas_orm", "canvas", two_sided=True),
    "canvas_cream": _m("canvas_cream_albedo", "canvas_normal", "canvas_orm", "canvas", two_sided=True),
    "banner": _m("banner_albedo", "banner_normal", None, "banner", alpha="clip", two_sided=True, roughness=0.9),
    "foliage": _m("foliage_albedo", "foliage_normal", None, "foliage", alpha="clip", two_sided=True, roughness=0.8),
    "bark": _m("bark_albedo", "bark_normal", "bark_orm", "bark"),
    "water": _m("water_albedo", "water_normal", "water_orm", "water"),
    "puddle": _m("puddle_albedo", "puddle_normal", "puddle_orm", "puddle", alpha="blend"),
    "concrete": _m("concrete_albedo", "concrete_normal", "concrete_orm", "concrete"),
    "soil": _m("soil_albedo", "soil_normal", "soil_orm", "soil"),
    "bronze": _m("bronze_albedo", "bronze_normal", "bronze_orm", "bronze"),
    "skyline": _m("skyline_albedo", None, "skyline_orm", "skyline"),
    "ironwork": _m("ironwork_albedo", None, None, "ironwork", alpha="clip", two_sided=True, roughness=0.5, metallic=0.4),
    "detail": _m("detail_albedo", "detail_normal", "detail_orm", "detail"),
    "emissive_lamp": _m(None, None, None, "flat", color=(1.0, 0.86, 0.62), emission=(1.0, 0.78, 0.45), strength=6.0,
                        roughness=0.2),
}

# which exported mesh-name prefixes Godot post-processes (ENVIRONMENT_CONTRACT.md)
SPECIAL_PREFIXES = ("water_", "puddle_", "foliage_", "emissive_", "banner_", "emit_smoke_")
CHUNKS = ("A", "B", "C", "north", "south", "skyline")


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def atlas(name: str):
    """Pixel rects of a texture atlas written by gen_textures (top-left origin)."""
    return load_json(os.path.join(HERE, f"atlas_{name}.json"))


def atlas_uv(atl: dict, key: str, inset_px: float = 1.0):
    """Return (u0, v0, u1, v1) in Blender UV convention (v up) for an atlas rect."""
    W, H = atl["size"]
    x, y, w, h = atl["rects"][key]
    u0 = (x + inset_px) / W
    u1 = (x + w - inset_px) / W
    v1 = 1.0 - (y + inset_px) / H
    v0 = 1.0 - (y + h - inset_px) / H
    return (u0, v0, u1, v1)


# ----------------------------------------------------------------------------- layout queries
class Rect:
    __slots__ = ("x0", "x1", "z0", "z1")

    def __init__(self, x0, x1, z0, z1):
        self.x0, self.x1, self.z0, self.z1 = float(x0), float(x1), float(z0), float(z1)

    def contains(self, x, z, eps=0.0):
        return self.x0 - eps <= x <= self.x1 + eps and self.z0 - eps <= z <= self.z1 + eps

    def inside(self, x, z, eps=1e-6):
        return self.x0 + eps < x < self.x1 - eps and self.z0 + eps < z < self.z1 - eps

    @property
    def w(self):
        return self.x1 - self.x0

    @property
    def d(self):
        return self.z1 - self.z0

    @property
    def cx(self):
        return 0.5 * (self.x0 + self.x1)

    @property
    def cz(self):
        return 0.5 * (self.z0 + self.z1)

    def __repr__(self):
        return f"Rect({self.x0},{self.x1},{self.z0},{self.z1})"


class Layout:
    def __init__(self, path: str = LAYOUT_PATH):
        self.path = path
        self.data = load_json(path)
        d = self.data
        self.floors = []
        for f in d["floors"]:
            r = Rect(f["min"][0], f["max"][0], f["min"][2], f["max"][2])
            self.floors.append({"id": f["id"], "rect": r, "top": f["max"][1], "bottom": f["min"][1],
                                "surface": f.get("surface", "stone"), "district": f.get("district", ""),
                                "zone": f.get("zone"), "is_bed": f.get("surface") == "water"})
        self.ramps = d["ramps"]
        self.solids = []
        for s in d["solids"]:
            r = Rect(s["min"][0], s["max"][0], s["min"][2], s["max"][2])
            e = dict(s)
            e["rect"] = r
            e["y0"] = s["min"][1]
            e["y1"] = s["max"][1]
            e["collide"] = s.get("collide", True)
            self.solids.append(e)
        self.blockers = []
        for b in d["blockers"]:
            self.blockers.append({"id": b["id"], "kind": b["kind"], "rect": Rect(b["min"][0], b["max"][0], b["min"][2], b["max"][2]),
                                  "y0": b["min"][1], "y1": b["max"][1]})
        self.water = [{"id": w["id"], "rect": Rect(w["min"][0], w["max"][0], w["min"][1], w["max"][1]), "y": w["y"]} for w in d["water"]]
        self.decor = d["decor"]
        self.zones = d["zones"]
        self.spawns = d["spawns"]
        self.perches = d["perch_ledges"]
        self.footprint = d["footprint"]

    # --- point queries (x, z in layout space) ---
    def ramp_height(self, r, x, z):
        """Height of ramp r at (x,z) if inside its footprint, else None."""
        ax, ay, az = r["from"]
        bx, by, bz = r["to"]
        dx, dz = bx - ax, bz - az
        L = math.hypot(dx, dz)
        ux, uz = dx / L, dz / L
        t = (x - ax) * ux + (z - az) * uz
        s = -(x - ax) * uz + (z - az) * ux
        if t < -1e-6 or t > L + 1e-6 or abs(s) > r["width"] / 2 + 1e-6:
            return None
        return ay + (by - ay) * (t / L)

    def ground_at(self, x, z, include_beds=False):
        """Walkable top at (x,z): max over floors/ramps containing the point (None if none)."""
        best = None
        for f in self.floors:
            if f["is_bed"] and not include_beds:
                continue
            if f["rect"].contains(x, z):
                best = f["top"] if best is None else max(best, f["top"])
        for r in self.ramps:
            h = self.ramp_height(r, x, z)
            if h is not None:
                best = h if best is None else max(best, h)
        return best

    def solid_at(self, x, z, y=0.5, collide_only=True, kinds=None):
        for s in self.solids:
            if collide_only and not s["collide"]:
                continue
            if kinds and s["kind"] not in kinds:
                continue
            if s["rect"].inside(x, z) and s["y0"] - 1e-6 <= y <= s["y1"] + 1e-6:
                return s
        return None

    def building_at(self, x, z):
        return self.solid_at(x, z, y=5.0, kinds=("building",))

    def water_at(self, x, z):
        for w in self.water:
            if w["rect"].inside(x, z):
                return w
        return None

    def classify(self, x, z):
        """What occupies ground level at (x,z): ('building', solid) | ('water', w) | ('floor', top) | ('void', None)."""
        b = self.building_at(x, z)
        if b is not None:
            return ("building", b)
        g = self.ground_at(x, z)
        if g is not None:
            return ("floor", g)
        w = self.water_at(x, z)
        if w is not None:
            return ("water", w)
        return ("void", None)

    def in_footprint(self, x, z):
        fx, fz = self.footprint["x"], self.footprint["z"]
        return fx[0] <= x <= fx[1] and fz[0] <= z <= fz[1]

    def zone_distance(self, x, z):
        return min(math.hypot(x - zz["center"][0], z - zz["center"][2]) for zz in self.zones)


def chunk_of(x: float, z: float) -> str:
    """District chunk for a layout-space point (content is assigned by its centre)."""
    if z < -20.0:
        return "north"
    if z > 20.0:
        return "south"
    if x < -24.5:
        return "A"
    if x > 24.5:
        return "C"
    return "B"
