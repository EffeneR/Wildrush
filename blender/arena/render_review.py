"""Review renders of the built Briarport arena (Blender, background, Eevee).

    blender -b blender/arena/briarport.blend -t 2 --python blender/arena/render_review.py -- \
        [--views overview,topdown,A,B,C,north,south] [--out DIR] [--res 1600x900] [--samples 32]

Writes <out>/blender_<view>.png (default out = evidence/arena). Lighting: warm clear afternoon
sun from the south-west + physical sky (review only; the game lights the scene itself).
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import common as C  # noqa: E402

# camera presets in LAYOUT space: (eye, target, lens_mm) ; player-height views ~2.6-3.2 m
VIEWS = {
    "overview": ((-18.0, 92.0, 118.0), (2.0, 0.0, 2.0), 30.0),
    "topdown": None,
    "A": ((-30.5, 3.0, 11.0), (-46.0, 0.8, -3.5), 24.0),
    "B": ((1.5, 3.2, 17.5), (-1.0, 3.0, -10.0), 22.0),
    "C": ((33.0, 3.0, 13.5), (50.0, 1.8, -2.0), 22.0),
    "north": ((0.0, 3.0, -53.5), (0.0, 2.2, -38.0), 22.0),
    "south": ((-52.0, 3.0, 37.0), (-20.0, 2.0, 37.0), 22.0),
}


def L2B(p):
    return Vector((p[0], -p[2], p[1]))


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--views", default="overview,topdown,A,B,C,north,south")
    ap.add_argument("--out", default=C.EVIDENCE_DIR)
    ap.add_argument("--res", default="1600x900")
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--prefix", default="blender_")
    ap.add_argument("--custom", default="", help="eye_x,eye_y,eye_z,tgt_x,tgt_y,tgt_z,lens for view 'custom'")
    return ap.parse_args(argv)


def setup_world(sc):
    w = bpy.data.worlds.get("ReviewSky") or bpy.data.worlds.new("ReviewSky")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    sky = nt.nodes.new("ShaderNodeTexSky")
    try:
        sky.sky_type = "NISHITA"
        sky.sun_disc = False
        sky.sun_elevation = math.radians(38.0)
        sky.sun_rotation = math.radians(135.0)
        sky.air_density = 1.0
        sky.dust_density = 1.5
    except Exception:
        pass
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 0.22
    outn = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], outn.inputs["Surface"])


def setup_sun(sc):
    ob = bpy.data.objects.get("ReviewSun")
    if ob is None:
        ld = bpy.data.lights.new("ReviewSun", "SUN")
        ob = bpy.data.objects.new("ReviewSun", ld)
        sc.collection.objects.link(ob)
    ld = ob.data
    ld.energy = 4.2
    ld.color = (1.0, 0.9, 0.76)
    ld.angle = math.radians(1.2)
    az, el = math.radians(225.0), math.radians(38.0)
    to_sun = Vector((math.sin(az) * math.cos(el), math.sin(el), -math.cos(az) * math.cos(el)))
    d = -L2B(to_sun)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    try:
        ld.use_shadow = True
        ld.shadow_cascade_max_distance = 160.0
    except Exception:
        pass


def setup_render(sc, res, samples):
    sc.render.engine = "BLENDER_EEVEE_NEXT"
    w, h = (int(v) for v in res.split("x"))
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.film_transparent = False
    e = sc.eevee
    for k, v in (("taa_render_samples", samples), ("use_shadows", True), ("shadow_ray_count", 1),
                 ("shadow_step_count", 6), ("use_raytracing", True), ("ray_tracing_method", "SCREEN"),
                 ("use_gtao", True), ("gtao_distance", 1.5), ("fast_gi_method", "GLOBAL_ILLUMINATION"),
                 ("use_volumetric_shadows", False), ("shadow_resolution_scale", 1.0)):
        try:
            setattr(e, k, v)
        except Exception:
            pass
    try:
        e.ray_tracing_options.resolution_scale = "2"
    except Exception:
        pass
    vs = sc.view_settings
    try:
        vs.view_transform = "AgX"
        vs.look = "AgX - Medium High Contrast"
    except Exception:
        try:
            vs.look = "None"
        except Exception:
            pass
    vs.exposure = 0.35
    vs.gamma = 1.0
    sc.render.use_simplify = False


def place_camera(sc, name, eye, tgt, lens, ortho=None):
    cam = bpy.data.objects.get("ReviewCam")
    if cam is None:
        cd = bpy.data.cameras.new("ReviewCam")
        cam = bpy.data.objects.new("ReviewCam", cd)
        sc.collection.objects.link(cam)
    cd = cam.data
    cd.clip_start = 0.1
    cd.clip_end = 1500.0
    if ortho:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
    else:
        cd.type = "PERSP"
        cd.lens = lens
        cd.sensor_width = 36.0
    e, t = L2B(eye), L2B(tgt)
    cam.location = e
    cam.rotation_euler = (t - e).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam


def main():
    a = parse()
    sc = bpy.context.scene
    kit = bpy.data.collections.get("KIT")
    if kit:
        kit.hide_render = True
    setup_world(sc)
    setup_sun(sc)
    setup_render(sc, a.res, a.samples)
    os.makedirs(a.out, exist_ok=True)
    views = [v for v in a.views.split(",") if v]
    for v in views:
        t0 = time.time()
        if v == "topdown":
            place_camera(sc, v, (0.0, 300.0, 0.0001), (0.0, 0.0, 0.0), 50.0, ortho=160.0)
            sc.render.resolution_x, sc.render.resolution_y = 1440, 1120
        elif v == "custom":
            vals = [float(s) for s in a.custom.split(",")]
            place_camera(sc, v, vals[0:3], vals[3:6], vals[6])
        else:
            eye, tgt, lens = VIEWS[v]
            place_camera(sc, v, eye, tgt, lens)
            w, h = (int(q) for q in a.res.split("x"))
            sc.render.resolution_x, sc.render.resolution_y = w, h
        path = os.path.join(a.out, f"{a.prefix}{v}.png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        print(f"[render] {v} -> {path} ({time.time() - t0:.1f}s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
