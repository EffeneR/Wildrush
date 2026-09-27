"""Deformation test: extreme poses on the rigged stage1 mesh, Workbench renders.

blender -b <work>/<id>/stage1.blend --gpu-backend vulkan --python bl_posetest.py -- <out.png>
"""
import sys
import os
import math
import numpy as np
import bpy
from mathutils import Euler, Vector, Quaternion

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bl_util import script_args

out = script_args()[0]
sc = bpy.context.scene
arm = [o for o in sc.objects if o.type == "ARMATURE"][0]
mesh = [o for o in sc.objects if o.type == "MESH" and o.name.endswith("_mesh")][0]
H = max(v.co.z for v in mesh.data.vertices)


def rot(bone, x=0, y=0, z=0):
    pb = arm.pose.bones[bone]
    pb.rotation_mode = "XYZ"
    pb.rotation_euler = Euler((math.radians(x), math.radians(y), math.radians(z)))


def reset():
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = Euler((0, 0, 0))
        pb.location = (0, 0, 0)


poses = []


def pose_a():
    reset()
    # arms raised overhead / forward, elbows bent, fists
    rot("LeftUpperArm", 20, 0, 70)
    rot("RightUpperArm", 70, 0, -10)
    rot("LeftLowerArm", 90, 0, 0)
    rot("RightLowerArm", 110, 0, 0)
    for s in ("Left", "Right"):
        for f in ("Index", "Middle", "Ring"):
            rot(f"{s}{f}1", 80)
            rot(f"{s}{f}2", 80)
        rot(f"{s}Thumb1", 30)
        rot(f"{s}Thumb2", 40)
    rot("Jaw", 25)
    rot("Head", 0, 0, 30)
    rot("Neck", 10, 0, 10)


def pose_b():
    reset()
    # deep lunge: left knee up, right leg back, hips twisted, tail curled
    rot("LeftUpperLeg", 95)
    rot("LeftLowerLeg", -110)
    rot("LeftFoot", 20)
    rot("RightUpperLeg", -35)
    rot("RightLowerLeg", -40)
    rot("Spine", 15, 0, 10)
    rot("Chest", 10, 0, 10)
    for i in range(1, 7):
        if ("Tail%d" % i) in arm.pose.bones:
            rot("Tail%d" % i, 25, 0, 10)
    rot("LeftEar1", -30)
    rot("RightEar1", -30)
    rot("LeftUpperArm", -40, 0, -35)
    rot("RightUpperArm", 0, 0, 40)


views = [("front", 0), ("q", 40), ("back", 180)]
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading
sh.light = "STUDIO"
sh.color_type = "MATERIAL"
sh.show_cavity = True
sc.render.resolution_x = 560
sc.render.resolution_y = 800
cam_d = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
cam_d.type = "ORTHO"
cam_d.ortho_scale = 2.3
target = Vector((0, 0, 0.95))
tiles = []
for pi, pf in enumerate((pose_a, pose_b)):
    pf()
    bpy.context.view_layer.update()
    for name, yaw in views:
        a = math.radians(yaw)
        cam.location = target + Vector((math.sin(a) * 6, -math.cos(a) * 6, 0.4))
        cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
        p = out.replace(".png", f"_{pi}{name}.png")
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        tiles.append(p)
imgs = [bpy.data.images.load(p) for p in tiles]
w, h = imgs[0].size
buf = np.zeros((h, w * len(imgs), 4), dtype=np.float32)
for i, im in enumerate(imgs):
    buf[:, i * w:(i + 1) * w] = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
img = bpy.data.images.new("st", w * len(imgs), h)
img.pixels = buf.ravel()
img.filepath_raw = out
img.file_format = "PNG"
img.save()
for p in tiles:
    os.remove(p)
print("posetest written", out)
