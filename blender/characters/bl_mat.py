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
    # same formula as game/src/present/shaders/palette_cloth.gdshader:
    #   albedo = primary*m.r + secondary*m.g + accent*m.b + trim*(1-sum)  times  (0.35 + 0.65*detail)
    #   (mask and detail sampled as sRGB colour textures)
    mask = _tex(nt, _img(p(f"{fid}_cloth_mask.png"), "sRGB"), (-1300, 200))
    det = _tex(nt, _img(p(f"{fid}_cloth_detail.png"), "sRGB"), (-1300, -300))
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    sep.location = (-1050, 200)
    nt.links.new(mask.outputs["Color"], sep.inputs["Color"])
    cols = {}
    for i, key in enumerate(("primary", "secondary", "accent", "trim")):
        rgb = nt.nodes.new("ShaderNodeRGB")
        rgb.name = rgb.label = "palette_" + key
        rgb.outputs[0].default_value = hex_to_lin(palette[key])
        rgb.location = (-1050, -120 - 120 * i)
        cols[key] = rgb

    def scale(col_out, fac_out, loc):
        mm = nt.nodes.new("ShaderNodeMix")
        mm.data_type = "RGBA"
        mm.blend_type = "MULTIPLY"
        mm.location = loc
        mm.inputs["Factor"].default_value = 1.0
        nt.links.new(col_out, mm.inputs[6])
        cv = nt.nodes.new("ShaderNodeCombineColor")
        cv.location = (loc[0] - 150, loc[1] - 80)
        for ch in ("Red", "Green", "Blue"):
            nt.links.new(fac_out, cv.inputs[ch])
        nt.links.new(cv.outputs["Color"], mm.inputs[7])
        return mm.outputs[2]

    def addc(a, b, loc):
        mm = nt.nodes.new("ShaderNodeMix")
        mm.data_type = "RGBA"
        mm.blend_type = "ADD"
        mm.location = loc
        mm.inputs["Factor"].default_value = 1.0
        nt.links.new(a, mm.inputs[6])
        nt.links.new(b, mm.inputs[7])
        return mm.outputs[2]
    s1 = nt.nodes.new("ShaderNodeMath")
    s1.operation = "ADD"
    s1.location = (-850, 420)
    nt.links.new(sep.outputs["Red"], s1.inputs[0])
    nt.links.new(sep.outputs["Green"], s1.inputs[1])
    s2 = nt.nodes.new("ShaderNodeMath")
    s2.operation = "ADD"
    s2.location = (-700, 420)
    nt.links.new(s1.outputs[0], s2.inputs[0])
    nt.links.new(sep.outputs["Blue"], s2.inputs[1])
    tw = nt.nodes.new("ShaderNodeMath")
    tw.operation = "SUBTRACT"
    tw.use_clamp = True
    tw.location = (-550, 420)
    tw.inputs[0].default_value = 1.0
    nt.links.new(s2.outputs[0], tw.inputs[1])
    c_p = scale(cols["primary"].outputs[0], sep.outputs["Red"], (-600, 200))
    c_s = scale(cols["secondary"].outputs[0], sep.outputs["Green"], (-600, 50))
    c_a = scale(cols["accent"].outputs[0], sep.outputs["Blue"], (-600, -100))
    c_t = scale(cols["trim"].outputs[0], tw.outputs[0], (-600, -250))
    mix = addc(addc(c_p, c_s, (-350, 150)), addc(c_a, c_t, (-350, -150)), (-150, 0))
    sepd = nt.nodes.new("ShaderNodeSeparateColor")
    sepd.location = (-1050, -650)
    nt.links.new(det.outputs["Color"], sepd.inputs["Color"])
    dm = nt.nodes.new("ShaderNodeMath")
    dm.operation = "MULTIPLY_ADD"
    dm.location = (-850, -650)
    dm.inputs[1].default_value = 0.65
    dm.inputs[2].default_value = 0.35
    nt.links.new(sepd.outputs["Red"], dm.inputs[0])
    final = scale(mix, dm.outputs[0], (50, 0))
    nt.links.new(final, bsdf.inputs["Base Color"])
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
