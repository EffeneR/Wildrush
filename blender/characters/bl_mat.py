"""Materials for WILDRUSH fighters (Blender).  CHARACTER_CONTRACT §4:
<id>_fur (albedo + normal), <id>_cloth (palette mask composite of palettes.default,
detail/AO, normal), <id>_eye, <id>_detail.  For glTF export the cloth base colour is
re-wired to the pre-composited <id>_cloth_basecolor.png (same textures, same palette)."""
import os
import bpy


def hex_to_lin(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c] + [1.0]


def _img(path, colorspace):
    name = os.path.basename(path)
    im = bpy.data.images.get(name)
    if im is None:
        im = bpy.data.images.load(path, check_existing=True)
    else:
        im.filepath = path
        im.reload()
    im.colorspace_settings.name = colorspace
    return im


def _clear(mat):
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return nt, bsdf


def _tex(nt, img, loc):
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = img
    t.location = loc
    t.interpolation = "Linear"
    return t


def _normal(nt, bsdf, img, strength=1.0):
    t = _tex(nt, img, (-500, -350))
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.location = (0, -350)
    nm.inputs["Strength"].default_value = strength
    nt.links.new(t.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])


def setup_materials(mesh, fid, texdir, palette, relpath_base=None):
    def p(n):
        return os.path.join(texdir, n)
    mats = {m.name: m for m in mesh.data.materials}
    # fur
    m = mats[fid + "_fur"]
    nt, bsdf = _clear(m)
    t = _tex(nt, _img(p(f"{fid}_fur_albedo.png"), "sRGB"), (-500, 100))
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    _normal(nt, bsdf, _img(p(f"{fid}_fur_normal.png"), "Non-Color"), 1.0)
    bsdf.inputs["Roughness"].default_value = 0.78
    bsdf.inputs["Specular IOR Level"].default_value = 0.30
    # cloth: palette composite (editable colours) -> base colour
    m = mats[fid + "_cloth"]
    nt, bsdf = _clear(m)
    mask = _tex(nt, _img(p(f"{fid}_cloth_mask.png"), "Non-Color"), (-1100, 200))
    det = _tex(nt, _img(p(f"{fid}_cloth_detail.png"), "Non-Color"), (-1100, -100))
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    sep.location = (-800, 200)
    nt.links.new(mask.outputs["Color"], sep.inputs["Color"])
    cols = {}
    for i, key in enumerate(("primary", "secondary", "accent", "trim")):
        rgb = nt.nodes.new("ShaderNodeRGB")
        rgb.name = rgb.label = "palette_" + key
        rgb.outputs[0].default_value = hex_to_lin(palette[key])
        rgb.location = (-800, -150 - 120 * i)
        cols[key] = rgb
    # trim -> primary (R) -> secondary (G) -> accent (B)
    m1 = nt.nodes.new("ShaderNodeMix")
    m1.data_type = "RGBA"
    m1.location = (-550, 150)
    nt.links.new(sep.outputs["Red"], m1.inputs["Factor"])
    nt.links.new(cols["trim"].outputs[0], m1.inputs[6])
    nt.links.new(cols["primary"].outputs[0], m1.inputs[7])
    m2 = nt.nodes.new("ShaderNodeMix")
    m2.data_type = "RGBA"
    m2.location = (-350, 150)
    nt.links.new(sep.outputs["Green"], m2.inputs["Factor"])
    nt.links.new(m1.outputs[2], m2.inputs[6])
    nt.links.new(cols["secondary"].outputs[0], m2.inputs[7])
    m3 = nt.nodes.new("ShaderNodeMix")
    m3.data_type = "RGBA"
    m3.location = (-150, 150)
    nt.links.new(sep.outputs["Blue"], m3.inputs["Factor"])
    nt.links.new(m2.outputs[2], m3.inputs[6])
    nt.links.new(cols["accent"].outputs[0], m3.inputs[7])
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.location = (50, 150)
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(m3.outputs[2], mul.inputs[6])
    gain = nt.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY"
    gain.inputs[1].default_value = 1.25
    gain.location = (-800, -650)
    sepd = nt.nodes.new("ShaderNodeSeparateColor")
    sepd.location = (-900, -500)
    nt.links.new(det.outputs["Color"], sepd.inputs["Color"])
    nt.links.new(sepd.outputs["Red"], gain.inputs[0])
    nt.links.new(gain.outputs[0], mul.inputs[7])
    nt.links.new(mul.outputs[2], bsdf.inputs["Base Color"])
    # pre-composited copy for export (not linked in the editable material)
    bc = _tex(nt, _img(p(f"{fid}_cloth_basecolor.png"), "sRGB"), (-500, 500))
    bc.name = bc.label = "export_basecolor"
    _normal(nt, bsdf, _img(p(f"{fid}_cloth_normal.png"), "Non-Color"), 0.8)
    bsdf.inputs["Roughness"].default_value = 0.72
    bsdf.inputs["Specular IOR Level"].default_value = 0.30
    # eye
    m = mats[fid + "_eye"]
    nt, bsdf = _clear(m)
    t = _tex(nt, _img(p(f"{fid}_eye.png"), "sRGB"), (-500, 100))
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.10
    bsdf.inputs["Specular IOR Level"].default_value = 0.6
    bsdf.inputs["Coat Weight"].default_value = 0.6
    # detail
    m = mats[fid + "_detail"]
    nt, bsdf = _clear(m)
    t = _tex(nt, _img(p(f"{fid}_detail.png"), "sRGB"), (-500, 100))
    t.interpolation = "Linear"
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.45


def cloth_to_export(mesh, fid):
    """Link the pre-composited palette texture straight into Base Color (glTF-exportable)."""
    m = bpy.data.materials[fid + "_cloth"]
    nt = m.node_tree
    bsdf = [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"][0]
    bc = nt.nodes["export_basecolor"]
    for l in list(bsdf.inputs["Base Color"].links):
        nt.links.remove(l)
    nt.links.new(bc.outputs["Color"], bsdf.inputs["Base Color"])
