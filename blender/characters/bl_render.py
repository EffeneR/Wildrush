"""WILDRUSH character pipeline - step 5 (Blender, Eevee): evidence renders + UI portraits.

blender -b <id>.blend -t 2 --gpu-backend vulkan --python bl_render.py -- <id> <evidence_dir> <portrait_dir>

Writes  evidence/characters/<id>_turnaround.png  (front / back / left / right, idle frame 0)
        evidence/characters/<id>_skills.png      (key poses: Q, E, R, heavy, guard)
        evidence/characters/<id>_blender.png     (3/4 beauty shot)
        game/assets/ui/portraits/<id>.png        (512x512 RGBA head & shoulders)
        game/assets/ui/portraits/<id>_full.png   (768x1024 RGBA full body, stance)
Poses come from the baked clip actions with the IK control constraints muted (what the GLB carries).
"""
import os
import sys
import math
import numpy as np
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bl_util import script_args, log  # noqa: E402
import anim_lib as AL  # noqa: E402

KEY_POSES = {
    "nyx": [("Q Pounce", "skill_q_air", 0.25), ("E Crosscut", "skill_e", 0.20), ("R Slip", "skill_r_right", 0.20),
            ("Heavy Rake", "heavy", 0.51), ("Guard", "guard_hold", 0.0)],
    "bruno": [("Q Shoulder Rush", "skill_q_charge", 0.25), ("E Warning Bark", "skill_e", 0.45), ("R Stand Firm", "skill_r_hold", 0.5),
              ("Heavy Slam", "heavy", 0.51), ("Guard", "guard_hold", 0.0)],
    "vex": [("Q False Start", "skill_q_step_b", 0.18), ("E Sidewinder", "skill_e_strike", 0.08), ("R Tail Sweep", "skill_r", 0.40),
            ("Heavy Lunge", "heavy", 0.51), ("Guard", "guard_hold", 0.0)],
    "hops": [("Q Bound", "skill_q_air", 0.25), ("E Double Kick", "skill_e", 0.44), ("R Dropkick", "skill_r_flight", 0.20),
             ("Heavy Back Kick", "heavy", 0.51), ("Guard", "guard_hold", 0.0)],
    "scrap": [("Q Catch & Turn", "skill_q_stance", 0.15), ("E Leg Sweep", "skill_e", 0.27), ("R Turnabout", "skill_r_grapple", 0.20),
              ("Heavy Double Paw", "heavy", 0.51), ("Guard", "guard_hold", 0.0)],
}


def setup(sc, transparent):
    sc.render.engine = "BLENDER_EEVEE_NEXT"
    sc.eevee.taa_render_samples = 48
    sc.eevee.use_shadows = True
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.film_transparent = transparent
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    if sc.world is None:
        sc.world = bpy.data.worlds.new("world")
    w = sc.world
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.030, 0.034, 0.042, 1)
    bg.inputs[1].default_value = 1.0


def add_light(name, loc, energy, size, color):
    ld = bpy.data.lights.get(name) or bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.size = size
    ld.color = color
    lo = bpy.data.objects.get(name) or bpy.data.objects.new(name, ld)
    if lo.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(lo)
    lo.location = loc
    lo.rotation_euler = (Vector((0, 0, 1.0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return lo


def lights(H):
    add_light("key", (-2.4, -3.2, H * 1.9), 1100, 2.2, (1.0, 0.95, 0.88))
    add_light("fill", (3.0, -2.2, H * 1.1), 380, 3.0, (0.82, 0.88, 1.0))
    add_light("rim", (0.8, 3.6, H * 1.8), 900, 1.6, (0.88, 0.94, 1.0))


def floor(show):
    ob = bpy.data.objects.get("floor")
    if ob is None:
        bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, 0))
        ob = bpy.context.active_object
        ob.name = "floor"
        m = bpy.data.materials.new("floor_mat")
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.055, 0.058, 0.065, 1)
        b.inputs["Roughness"].default_value = 0.8
        ob.data.materials.append(m)
    ob.hide_render = not show
    return ob


def camera():
    cam = bpy.data.objects.get("render_cam")
    if cam is None:
        cd = bpy.data.cameras.new("render_cam")
        cam = bpy.data.objects.new("render_cam", cd)
        bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    return cam


def aim(cam, target, yaw_deg, dist, height, lens):
    a = math.radians(yaw_deg)
    cam.data.lens = lens
    cam.location = Vector(target) + Vector((math.sin(a) * dist, -math.cos(a) * dist, height))
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()


def pose(arm, clip, t):
    act = bpy.data.actions.get(clip)
    if act is None:
        log(f"WARNING: clip {clip} missing for render")
        return False
    AL.set_constraints_enabled(arm, False)
    arm.animation_data_create()
    arm.animation_data.action = act
    f = t * 60.0
    bpy.context.scene.frame_set(int(math.floor(f)), subframe=f - math.floor(f))
    return True


def render(path, w, h):
    sc = bpy.context.scene
    sc.render.resolution_x = w
    sc.render.resolution_y = h
    sc.render.resolution_percentage = 100
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def stitch(paths, out):
    imgs = [bpy.data.images.load(p) for p in paths]
    w, h = imgs[0].size
    buf = np.zeros((h, w * len(imgs), 4), dtype=np.float32)
    for i, im in enumerate(imgs):
        buf[:, i * w:(i + 1) * w] = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
    img = bpy.data.images.new("stitch_" + os.path.basename(out), w * len(imgs), h, alpha=True)
    img.pixels = buf.ravel()
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()
    for im in imgs:
        bpy.data.images.remove(im)
    for p in paths:
        os.remove(p)


def main():
    fid, evd, pod = script_args()[:3]
    os.makedirs(evd, exist_ok=True)
    os.makedirs(pod, exist_ok=True)
    sc = bpy.context.scene
    arm = bpy.data.objects[fid + "_rig"]
    mesh = bpy.data.objects[fid + "_mesh"]
    src = bpy.data.objects.get(fid + "_wsrc")
    if src:
        src.hide_render = True
    co = np.zeros(len(mesh.data.vertices) * 3)
    mesh.data.vertices.foreach_get("co", co)
    H = float(co.reshape(-1, 3)[:, 2].max())
    setup(sc, False)
    lights(H)
    cam = camera()
    tmp = os.path.join(evd, "_tmp_" + fid)
    os.makedirs(tmp, exist_ok=True)
    # ---- turnaround (idle frame 0)
    floor(True)
    pose(arm, "idle", 0.0)
    paths = []
    for name, yaw in (("front", 0), ("back", 180), ("left", 90), ("right", -90)):
        aim(cam, (0, 0, H * 0.50), yaw, 4.6, 0.20, 50)
        p = os.path.join(tmp, f"turn_{name}.png")
        render(p, 600, 900)
        paths.append(p)
    stitch(paths, os.path.join(evd, f"{fid}_turnaround.png"))
    log("turnaround done")
    # ---- skills key poses
    paths = []
    for label, clip, t in KEY_POSES[fid]:
        pose(arm, clip, t)
        aim(cam, (0, -0.25, H * 0.48), 32, 4.4, 0.35, 45)
        p = os.path.join(tmp, f"skill_{clip}.png")
        render(p, 600, 800)
        paths.append(p)
    stitch(paths, os.path.join(evd, f"{fid}_skills.png"))
    log("skills done")
    # ---- beauty shot
    pose(arm, "idle", 0.0)
    aim(cam, (0, 0, H * 0.52), 28, 4.1, 0.30, 50)
    render(os.path.join(evd, f"{fid}_blender.png"), 1000, 1200)
    # ---- portraits (transparent)
    setup(sc, True)
    floor(False)
    pose(arm, "idle", 0.0)
    head = arm.pose.bones["Head"]
    hc = arm.matrix_world @ ((head.head + head.tail) * 0.5)
    extra = 0.06 if fid == "hops" else 0.0
    aim(cam, (hc.x, hc.y, hc.z - 0.02 + extra), 18, 2.05 + extra * 3, 0.0, 85)
    render(os.path.join(pod, f"{fid}.png"), 512, 512)
    aim(cam, (0, 0, H * 0.51), 20, 4.4, 0.15, 50)
    render(os.path.join(pod, f"{fid}_full.png"), 768, 1024)
    try:
        os.rmdir(tmp)
    except OSError:
        pass
    log("portraits done")


main()
