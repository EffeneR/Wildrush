#!/usr/bin/env python3
"""Generate the canonical Briarport arena layout (game/data/arena/briarport_layout.json).

Spec §7 / D-007: 144 m (X, east-west) x 112 m (Z, north-south) footprint, Y up.
A = Canal Court (-42,0,0), B = Market Square (0,0,0), C = Loading Yard (42,0,0).
Team spawns mirrored at (0,0,-48) [team 0, north] and (0,0,+48) [team 1, south].

All gameplay geometry (floors, solids, ramps, blockers, perch ledges) is defined for the
NORTH half (z <= 0) plus centre-line features, then mirrored z -> -z, so both teams get
identical routes (the symmetric-spawn correction of REFERENCE_AUDIT A7). Decorative
dressing may differ between halves; it never has collision that changes routes.

Run: .venv/bin/python tools/arena/gen_layout.py  (idempotent; overwrites the JSON)
"""
from __future__ import annotations

import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "game", "data", "arena", "briarport_layout.json")

floors: list[dict] = []
ramps: list[dict] = []
solids: list[dict] = []
blockers: list[dict] = []
water: list[dict] = []
perches: list[dict] = []
decor: list[dict] = []
_ids: set[str] = set()


def _uid(base: str) -> str:
    i, name = 0, base
    while name in _ids:
        i += 1
        name = f"{base}_{i}"
    _ids.add(name)
    return name


def box(lst: list, id_: str, x0: float, x1: float, y0: float, y1: float, z0: float, z1: float, **kw) -> None:
    assert x0 < x1 and y0 < y1 and z0 < z1, (id_, x0, x1, y0, y1, z0, z1)
    d = {"id": _uid(id_), "min": [x0, y0, z0], "max": [x1, y1, z1]}
    d.update(kw)
    lst.append(d)


def floor(id_, x0, x1, z0, z1, y=0.0, surface="stone", district="", thickness=1.0, **kw):
    box(floors, id_, x0, x1, y - thickness, y, z0, z1, surface=surface, district=district, **kw)


def solid(id_, x0, x1, z0, z1, h, kind, y0=0.0, **kw):
    box(solids, id_, x0, x1, y0, y0 + h, z0, z1, kind=kind, **kw)


def blocker(id_, x0, x1, z0, z1, kind="water_edge", y0=-2.0, y1=4.5):
    box(blockers, id_, x0, x1, y0, y1, z0, z1, kind=kind)


def ramp(id_, a, b, width, surface="stone", kind="stairs"):
    """Straight ramp/stairs from point a=(x,y,z) (bottom) to b (top); width across."""
    ramps.append({"id": _uid(id_), "from": list(a), "to": list(b), "width": width, "surface": surface, "kind": kind})


def perch(id_, a, b, normal):
    """Designated Nyx ledge: top edge segment a->b (same height); normal points to the climb side."""
    perches.append({"id": _uid(id_), "a": list(a), "b": list(b), "normal": list(normal)})


def dec(kind, x, y, z, yaw=0.0, scale=1.0, **kw):
    d = {"kind": kind, "pos": [x, y, z], "yaw": yaw, "scale": scale}
    d.update(kw)
    decor.append(d)


# ---------------------------------------------------------------------------------------
# NORTH HALF (z <= 0). Mirrored afterwards. Centre-line (z-spanning) features are defined
# once with explicit full extents and flagged "centre": True so they are not mirrored.
# ---------------------------------------------------------------------------------------
H_BLD = 16.0   # collision height for buildings (roofs unreachable)
H_LOW = 1.1    # low cover walls (above max jump apex ~0.95 m)

# --- Spawn plaza (team 0 north) ---
floor("spawn_plaza", -12, 12, -56, -42, district="spawn")
solid("spawn_wall_w", -13, -12, -56, -42, H_BLD, "building", style="townhouse")
solid("spawn_wall_e", 12, 13, -56, -42, H_BLD, "building", style="townhouse")
solid("spawn_wall_n", -13, 13, -57, -56, H_BLD, "building", style="townhouse")
# south wall of the plaza with two separated exits x in [-9,-4] and [4,9]
solid("spawn_front_w", -13, -9, -42, -40, H_BLD, "building", style="gatehouse")
solid("spawn_front_c", -4, 4, -42, -40, H_BLD, "building", style="gatehouse")
solid("spawn_front_e", 9, 13, -42, -40, H_BLD, "building", style="gatehouse")
floor("spawn_exit_w", -9, -4, -42, -40, district="spawn")
floor("spawn_exit_e", 4, 9, -42, -40, district="spawn")
# cover inside the plaza (keeps line of sight from the exits broken)
solid("spawn_planter_w", -8, -5, -52, -50.5, 1.0, "planter")
solid("spawn_planter_e", 5, 8, -52, -50.5, 1.0, "planter")

# --- North Row (east-west street connecting everything; flank routes at both ends) ---
floor("north_row", -60, 60, -40, -34, district="north_row")
solid("north_row_bld_w", -61, -13, -56, -40, H_BLD, "building", style="townhouse")
solid("north_row_bld_e", 13, 61, -56, -40, H_BLD, "building", style="warehouse")
solid("west_edge_n", -61, -60, -40, -20, H_BLD, "building", style="townhouse")
solid("east_edge_n", 60, 61, -40, -20, H_BLD, "building", style="warehouse")

# --- North lanes band z in [-34,-20]: buildings cut by five N-S lanes ---
# lanes: A-N x[-45,-39] (6 m), Quay-N x[-27,-23] (4 m), Avenue-N x[-3,3] (6 m),
#        Loading-N x[23,27] (4 m), C-N x[39,45] (6 m)
floor("lane_a_n", -45, -39, -34, -20, district="A")
floor("lane_quay_n", -27, -23, -34, -20, district="quay")
floor("avenue_n", -3, 3, -34, -20, district="B")
floor("lane_load_n", 23, 27, -34, -20, surface="stone", district="lane")
floor("lane_c_n", 39, 45, -34, -20, surface="stone", district="C")
solid("blk_nw1", -60, -45, -34, -20, H_BLD, "building", style="canal_house")
solid("blk_nw2", -39, -27, -34, -29, H_BLD, "building", style="canal_house")
solid("blk_nw3", -39, -27, -25, -20, H_BLD, "building", style="canal_house")
floor("alley_w", -39, -27, -29, -25, district="alley")         # 4 m flank alley A-lane <-> quay
solid("blk_nmw", -23, -3, -34, -20, H_BLD, "building", style="market_hall")
solid("blk_nme", 3, 23, -34, -20, H_BLD, "building", style="market_hall")
solid("blk_ne2", 27, 39, -34, -29, H_BLD, "building", style="warehouse")
solid("blk_ne3", 27, 39, -25, -20, H_BLD, "building", style="warehouse")
floor("alley_e", 27, 39, -29, -25, surface="stone", district="alley")  # 4 m flank alley lane <-> C-lane
solid("blk_ne1", 45, 60, -34, -20, H_BLD, "building", style="warehouse")

# --- A: Canal Court (x in [-60,-28]) ---
# water channels (sunken, scenery): north canal z[-20,-15], west canal x[-60,-55], east canal x[-32,-28]
water.append({"id": "canal_n", "min": [-60, -20], "max": [-28, -15], "y": -1.0})
water.append({"id": "canal_w", "min": [-60, -15], "max": [-55, 0], "y": -1.0, "half": True})
water.append({"id": "canal_e", "min": [-32, -15], "max": [-28, 0], "y": -1.0, "half": True})
# canal beds (collision so anything that falls in is contained; blockers keep fighters out)
box(floors, "canal_bed_n", -60, -28, -3.0, -2.0, -20, -15, surface="water", district="canal")
box(floors, "canal_bed_w", -60, -55, -3.0, -2.0, -15, 0, surface="water", district="canal")
box(floors, "canal_bed_e", -32, -28, -3.0, -2.0, -15, 0, surface="water", district="canal")
# bridges
floor("bridge_a_n", -44.5, -39.5, -20, -15, surface="wood", district="A")
floor("bridge_a_e", -32, -28, -9, -5, surface="wood", district="A")
# deck (broad dry stone fighting deck)
floor("deck_a", -55, -32, -15, 0, district="A", zone="A")
# raised west terrace (1.0 m) with stairs at its north end; Nyx can perch onto it
floor("terrace_a", -55, -51, -11, 0, y=1.0, district="A", thickness=1.0)
ramp("terrace_a_stairs", (-53, 0.0, -14.4), (-53, 1.0, -11.0), 4.0, kind="stairs")
perch("perch_terrace_a", (-51, 1.0, -11), (-51, 1.0, 0), (1, 0, 0))
# low cover walls on the deck (outside the 9 m scoring radius edge, never filling it)
solid("deck_a_wall1", -50.5, -47.5, -11.5, -10.5, H_LOW, "wall_low", style="stone_ivy")
solid("deck_a_wall2", -37.5, -34.5, -12.5, -11.5, H_LOW, "wall_low", style="stone_ivy")
solid("deck_a_post_w", -46.6, -45.6, -14.4, -13.4, 3.6, "column", style="banner_post")
solid("deck_a_post_e", -38.4, -37.4, -14.4, -13.4, 3.6, "column", style="banner_post")
# canal edge blockers (invisible) + visual balustrades
blocker("blk_canal_n_edge_w", -60, -44.5, -15.3, -14.9)          # deck north edge (west of bridge)
blocker("blk_canal_n_edge_e", -39.5, -32, -15.3, -14.9)          # deck north edge (east of bridge)
blocker("blk_canal_n_rowside_w", -60, -45, -20.1, -19.7)         # building side (safety)
blocker("blk_canal_n_rowside_e", -39, -28, -20.1, -19.7)
blocker("blk_bridge_an_w", -44.9, -44.5, -20, -15)
blocker("blk_bridge_an_e", -39.5, -39.1, -20, -15)
blocker("blk_canal_w_edge", -55.3, -54.9, -15, 0)
blocker("blk_canal_e_edge_deck_n", -32.1, -31.7, -15, -9)
blocker("blk_canal_e_edge_deck_s", -32.1, -31.7, -5, 0)
blocker("blk_canal_e_edge_quay_n", -28.3, -27.9, -20, -9)
blocker("blk_canal_e_edge_quay_s", -28.3, -27.9, -5, 0)
blocker("blk_bridge_ae_n", -32, -28, -9.4, -9.0)
blocker("blk_bridge_ae_s", -32, -28, -5.0, -4.6)
for bx0, bx1, bz0, bz1 in [(-60, -44.5, -15.25, -14.95), (-39.5, -32, -15.25, -14.95),
                           (-55.25, -54.95, -15, 0), (-32.05, -31.75, -15, -9), (-32.05, -31.75, -5, 0),
                           (-28.25, -27.95, -15, -9), (-28.25, -27.95, -5, 0)]:
    solid("balustrade", bx0, bx1, bz0, bz1, 0.9, "balustrade", collide=False)
solid("west_edge_a", -61, -60, -20, 0, H_BLD, "building", style="canal_house")

# --- Quay (west N-S connector x in [-28,-22]) ---
floor("quay", -28, -22, -20, 0, district="quay")

# --- B: Market Square (x in [-22,22]) ---
floor("plaza_b", -22, 22, -20, 0, district="B", zone="B")
# arcade columns along the north edge (z=-18), avenue gap at x in [-3,3]
for cx in (-18.0, -12.0, -6.0, 6.0, 12.0, 18.0):
    solid("arcade_col", cx - 0.35, cx + 0.35, -18.35, -17.65, 5.0, "column", style="arcade")
# arcade columns on the square's west/east edges (partial separation from the quay / loading lane)
for cz in (-16.0, -10.0):
    for cx in (-21.6, 21.6):
        solid("edge_col", cx - 0.35, cx + 0.35, cz - 0.35, cz + 0.35, 5.0, "column", style="arcade")
# peripheral fixed stalls (red/green canopies) — outside the scoring radius
solid("stall_nw", -17, -12, -14.5, -11.5, 2.3, "stall", canopy="red")
solid("stall_ne", 12, 17, -14.5, -11.5, 2.3, "stall", canopy="green")
# planters with trees on the square's edges
solid("planter_nw", -21.5, -19.5, -9, -6, 1.0, "planter", tree=True)
solid("planter_ne", 19.5, 21.5, -9, -6, 1.0, "planter", tree=True)
solid("planter_n_w", -8.5, -6.5, -16.5, -14.5, 1.0, "planter", tree=True)
solid("planter_n_e", 6.5, 8.5, -16.5, -14.5, 1.0, "planter", tree=True)

# --- Loading lane (east N-S connector x in [22,28]) ---
floor("lane_load", 22, 28, -20, 0, district="lane")

# --- C: Loading Yard (x in [28,60]) ---
# warehouse wall between the loading lane and the yard, with two 6 m gates (z in [-10,-4] and [4,10])
solid("yard_wall_n", 28, 30, -20, -10, H_BLD, "building", style="warehouse_gate")
solid("yard_wall_c", 28, 30, -4, 0, H_BLD, "building", style="warehouse_gate")
floor("yard_gate", 28, 30, -10, -4, surface="stone", district="C")
floor("yard_c", 30, 52, -20, 0, surface="stone", district="C", zone="C")
floor("yard_c_east_pocket", 52, 60, -20, -14, surface="stone", district="C")
floor("platform_c", 52, 60, -14, 0, y=1.2, surface="metal", district="C", thickness=1.2)
ramp("platform_c_ramp", (47.0, 0.0, -12.25), (52.0, 1.2, -12.25), 3.5, surface="metal", kind="ramp")
perch("perch_platform_c", (52, 1.2, -10.5), (52, 1.2, 0), (-1, 0, 0))
# restrained cargo cover
solid("crates_c_nw", 34.5, 37.5, -11.5, -9.0, 2.4, "crate_stack", style="tarp")
solid("crates_c_ne", 46.5, 49.0, -11.0, -8.5, 1.2, "crate_stack", style="small")
solid("crate_c_in_n", 45.2, 46.6, -3.8, -2.4, 1.0, "crate_stack", style="single")
solid("containers_c_e", 57.5, 60, -12, -2, 2.6, "container", y0=1.2)
solid("barrier_c_n", 40.0, 44.0, -17.5, -16.7, 1.1, "wall_low", style="concrete_logo")
solid("east_edge_c", 60, 61, -20, 0, H_BLD, "building", style="warehouse")

# ---------------------------------------------------------------------------------------
# Centre-line features (span z<0 and z>0; NOT mirrored)
# ---------------------------------------------------------------------------------------
CENTRE_START = (len(floors), len(solids), len(ramps), len(blockers), len(water), len(perches))
floor("bridge_a_e_s_placeholder", -32, -28, 5, 9, surface="wood", district="A")  # replaced below by mirror of bridge_a_e
floors.pop(); _ids.discard("bridge_a_e_s_placeholder")
# fountain at the centre of B (modest; leaves the 9 m scoring area open)
solid("fountain_basin", -2.4, 2.4, -2.4, 2.4, 0.6, "fountain", centre=True, shape="cylinder", radius=2.4)
solid("fountain_statue", -0.6, 0.6, -0.6, 0.6, 2.6, "fountain_statue", centre=True, shape="cylinder", radius=0.6)
# crane: visual only, outside collision routes (east of the playable boundary)
dec("crane", 66.0, 0.0, -6.0, yaw=-100.0, scale=1.0)

# ---------------------------------------------------------------------------------------
# Mirror north half -> south half (z -> -z), except centre-flagged entries
# ---------------------------------------------------------------------------------------

def mirror_box(d: dict) -> dict:
    m = dict(d)
    m["id"] = _uid(d["id"] + "_s")
    m["min"] = [d["min"][0], d["min"][1], -d["max"][2]]
    m["max"] = [d["max"][0], d["max"][1], -d["min"][2]]
    return m


for lst in (floors, solids, blockers):
    for d in list(lst):
        if d.get("centre"):
            continue
        if d["min"][2] >= 0:  # already south
            continue
        lst.append(mirror_box(d))
for w in list(water):
    m = dict(w)
    m["id"] = w["id"] + "_s"
    m["min"] = [w["min"][0], -w["max"][1]]
    m["max"] = [w["max"][0], -w["min"][1]]
    water.append(m)
for r in list(ramps):
    m = dict(r)
    m["id"] = _uid(r["id"] + "_s")
    m["from"] = [r["from"][0], r["from"][1], -r["from"][2]]
    m["to"] = [r["to"][0], r["to"][1], -r["to"][2]]
    ramps.append(m)
for p in list(perches):
    m = dict(p)
    m["id"] = _uid(p["id"] + "_s")
    m["a"] = [p["a"][0], p["a"][1], -p["a"][2]]
    m["b"] = [p["b"][0], p["b"][1], -p["b"][2]]
    m["normal"] = [p["normal"][0], 0, -p["normal"][2]]
    perches.append(m)

# Merge mirrored half-floors that meet at z=0 into single slabs (cleaner collision/nav):
merged: list[dict] = []
by_key: dict = {}
for f in floors:
    key = (f["min"][0], f["max"][0], f["min"][1], f["max"][1], f.get("surface"), f.get("district"))
    if f["max"][2] == 0 or f["min"][2] == 0:
        if key in by_key:
            o = by_key[key]
            o["min"][2] = min(o["min"][2], f["min"][2])
            o["max"][2] = max(o["max"][2], f["max"][2])
            continue
        by_key[key] = f
    merged.append(f)
floors[:] = merged
for lst in (solids, blockers):
    merged = []
    by_key = {}
    for d in lst:
        key = (d["min"][0], d["max"][0], d["min"][1], d["max"][1], d.get("kind"), d.get("style"))
        if (d["max"][2] == 0 or d["min"][2] == 0) and not d.get("centre"):
            if key in by_key:
                o = by_key[key]
                o["min"][2] = min(o["min"][2], d["min"][2])
                o["max"][2] = max(o["max"][2], d["max"][2])
                continue
            by_key[key] = d
        merged.append(d)
    lst[:] = merged
merged_w = []
wkey: dict = {}
for w in water:
    if w.get("half"):
        k = (w["min"][0], w["max"][0])
        if k in wkey:
            o = wkey[k]
            o["min"][1] = min(o["min"][1], w["min"][1])
            o["max"][1] = max(o["max"][1], w["max"][1])
            o.pop("half", None)
            continue
        wkey[k] = w
    merged_w.append(w)
water[:] = merged_w
for w in water:
    w.pop("half", None)

# ---------------------------------------------------------------------------------------
# Perimeter blockers (footprint 144 x 112 m; playable interior within the building ring)
# ---------------------------------------------------------------------------------------
blocker("boundary_w", -72, -71, -56, 56, kind="boundary", y0=-3, y1=30)
blocker("boundary_e", 71, 72, -56, 56, kind="boundary", y0=-3, y1=30)
blocker("boundary_n", -72, 72, -57, -56, kind="boundary", y0=-3, y1=30)
blocker("boundary_s", -72, 72, 56, 57, kind="boundary", y0=-3, y1=30)
blocker("ceiling", -72, 72, 30, 31, kind="boundary", y0=0, y1=1)  # placeholder removed below
blockers.pop()

# ---------------------------------------------------------------------------------------
# Decorative dressing (no route-changing collision). Halves differ slightly on purpose.
# ---------------------------------------------------------------------------------------
for x in (-50.0, -34.0):
    dec("lamp_post", x, 0.0, -14.4)
    dec("lamp_post", x, 0.0, 14.4)
for x in (-16.0, -8.0, 8.0, 16.0):
    dec("lamp_post", x, 0.0, -19.4)
    dec("lamp_post", x, 0.0, 19.4)
for z in (-30.0, -24.0, 24.0, 30.0):
    dec("lamp_post", -2.6, 0.0, z)
    dec("lamp_post", 2.6, 0.0, z)
dec("banner_on_post", -46.1, 0.0, -13.9, yaw=0.0)
dec("banner_on_post", -37.9, 0.0, -13.9, yaw=0.0)
dec("banner_on_post", -46.1, 0.0, 13.9, yaw=180.0)
dec("banner_on_post", -37.9, 0.0, 13.9, yaw=180.0)
dec("banner_wall", 0.0, 9.0, -33.9, yaw=0.0)
dec("banner_wall", 0.0, 9.0, 33.9, yaw=180.0)
dec("banner_wall", -20.0, 8.0, -33.9, yaw=0.0)
dec("banner_wall", 20.0, 8.0, 33.9, yaw=180.0)
for (x, z) in [(-58.0, -8.0), (-58.5, 5.0), (-30.0, 12.0)]:
    dec("boat", x, -1.0, z, yaw=90.0 if x < -50 else 0.0)
dec("boat", -50.0, -1.0, -17.5, yaw=0.0)
dec("boat", -36.0, -1.0, 17.6, yaw=180.0)
for (x, z) in [(-53.5, -13.5), (-36.0, 13.8), (-24.5, -19.0), (26.5, 19.0), (-11.0, 4.0)]:
    dec("barrel_group", x, 0.0, z)
for (x, z) in [(31.0, -18.5), (58.5, -16.0), (31.0, 18.5), (35.0, 16.0)]:
    dec("pallet_stack", x, 0.0, z)
dec("forklift", 49.5, 0.0, 15.5, yaw=30.0)
for (x, z) in [(-40.0, -45.0), (40.0, 45.0), (-30.0, 45.0), (30.0, -45.0)]:
    dec("chimney_smoke", x, 16.0, z)
for (x, z, n) in [(-45.0, -50.0, "clock_tower"), (0.0, -60.0, "cathedral"), (50.0, 62.0, "cathedral"), (-66.0, 40.0, "tower")]:
    dec("skyline_" + n, x, 0.0, z)
# puddles (cosmetic; wet footstep surface) — listed so visuals and footstep audio agree
puddles = [(-45.0, -4.0, 2.2), (-38.0, 6.0, 1.6), (-4.0, 7.0, 1.8), (6.5, -9.0, 1.4), (38.5, -6.0, 2.0),
           (47.0, 5.0, 1.5), (0.0, -27.0, 1.2), (-42.0, -37.0, 1.6), (42.0, 37.0, 1.6), (-25.0, 10.0, 1.1)]
for (x, z, r) in puddles:
    dec("puddle", x, 0.0, z, scale=r)

# ---------------------------------------------------------------------------------------
# Zones, spawns, nav parameters
# ---------------------------------------------------------------------------------------
zones = [
    {"id": "A", "name": "Canal Court", "center": [-42.0, 0.0, 0.0], "floor_y": 0.0, "radius": 9.0},
    {"id": "B", "name": "Market Square", "center": [0.0, 0.0, 0.0], "floor_y": 0.0, "radius": 9.0},
    {"id": "C", "name": "Loading Yard", "center": [42.0, 0.0, 0.0], "floor_y": 0.0, "radius": 9.0},
]


def spawn_points(zc: float, facing_yaw: float) -> list:
    pts = []
    for i, x in enumerate((-6.0, -3.0, 0.0, 3.0, 6.0)):
        pts.append([x, 0.0, zc + (0.0 if i % 2 == 0 else 1.5 * (1 if zc < 0 else -1)), facing_yaw])
    return pts


# yaw 0 faces north (-Z); team 0 (north) faces south => yaw = pi
spawns = [
    {"team": 0, "name": "North", "points": spawn_points(-48.0, math.pi),
     "protect": {"min": [-12.0, -1.0, -56.0], "max": [12.0, 8.0, -40.0]},
     "barriers": [{"min": [-9.0, -1.0, -40.4], "max": [-4.0, 8.0, -40.0]},
                  {"min": [4.0, -1.0, -40.4], "max": [9.0, 8.0, -40.0]}],
     "exits": [[-6.5, 0.0, -39.0], [6.5, 0.0, -39.0]]},
    {"team": 1, "name": "South", "points": spawn_points(48.0, 0.0),
     "protect": {"min": [-12.0, -1.0, 40.0], "max": [12.0, 8.0, 56.0]},
     "barriers": [{"min": [-9.0, -1.0, 40.0], "max": [-4.0, 8.0, 40.4]},
                  {"min": [4.0, -1.0, 40.0], "max": [9.0, 8.0, 40.4]}],
     "exits": [[-6.5, 0.0, 39.0], [6.5, 0.0, 39.0]]},
]

layout = {
    "name": "Briarport",
    "version": 1,
    "_doc": "Generated by tools/arena/gen_layout.py — do not edit by hand. Units metres, Y up, X east, Z south.",
    "footprint": {"x": [-72.0, 72.0], "z": [-56.0, 56.0]},
    "playable_bounds": {"min": [-60.0, -3.0, -56.0], "max": [60.0, 12.0, 56.0]},
    "fall_recovery_y": -12.0,
    "zones": zones,
    "spawns": spawns,
    "floors": floors,
    "ramps": ramps,
    "solids": solids,
    "blockers": blockers,
    "water": water,
    "perch_ledges": perches,
    "decor": decor,
    "nav": {"cell_size": 0.25, "cell_height": 0.1, "agent_radius": 0.5, "agent_height": 1.8,
            "agent_max_climb": 0.3, "agent_max_slope": 46.0},
}

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(layout, fh, indent=1)
print(f"wrote {OUT}: floors={len(floors)} ramps={len(ramps)} solids={len(solids)} blockers={len(blockers)} "
      f"water={len(water)} perches={len(perches)} decor={len(decor)}")
sys.exit(0)
