"""Minimal GLB (binary glTF 2.0) reader/writer + post-processing for the Briarport art export.

Pure Python + optional numpy/PIL (only for the pixel comparison). Runs inside Blender's Python
or the project venv.

* externalize_images(): replaces images embedded by the Blender exporter with relative URIs
  (``textures/<name>.png``) when the embedded pixels are identical to the shared texture file,
  then compacts the binary chunk. All chunks therefore reference ONE shared texture set in
  game/assets/arena/textures (one Godot texture resource per file instead of one per chunk).
* stats(): triangle / node / mesh / material counts (per node instance) for the manifest.
"""
from __future__ import annotations

import io
import json
import os
import struct

GLB_MAGIC = 0x46546C67
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942


def read_glb(path: str):
    with open(path, "rb") as fh:
        data = fh.read()
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC or version != 2:
        raise ValueError(f"{path}: not a GLB v2 file")
    off = 12
    js, bin_ = None, b""
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == CHUNK_JSON:
            js = json.loads(chunk.decode("utf-8"))
        elif ctype == CHUNK_BIN:
            bin_ = bytes(chunk)
        off += 8 + clen
    if js is None:
        raise ValueError(f"{path}: no JSON chunk")
    return js, bin_


def write_glb(path: str, js: dict, bin_: bytes) -> None:
    jbytes = json.dumps(js, separators=(",", ":")).encode("utf-8")
    jbytes += b" " * ((4 - len(jbytes) % 4) % 4)
    bbytes = bin_ + b"\x00" * ((4 - len(bin_) % 4) % 4)
    total = 12 + 8 + len(jbytes) + (8 + len(bbytes) if bbytes else 0)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", GLB_MAGIC, 2, total))
        fh.write(struct.pack("<II", len(jbytes), CHUNK_JSON))
        fh.write(jbytes)
        if bbytes:
            fh.write(struct.pack("<II", len(bbytes), CHUNK_BIN))
            fh.write(bbytes)


def _pixels_equal(png_bytes: bytes, file_path: str) -> bool:
    try:
        import numpy as np
        from PIL import Image
    except ImportError:  # Blender's Python has numpy but not PIL
        return _pixels_equal_blender(png_bytes, file_path)
    a = np.asarray(Image.open(io.BytesIO(png_bytes)))
    b = np.asarray(Image.open(file_path))
    return _cmp_arrays(a, b)


def _cmp_arrays(a, b) -> bool:
    import numpy as np
    if a.ndim == 2:
        a = a[..., None]
    if b.ndim == 2:
        b = b[..., None]
    if a.shape[:2] != b.shape[:2]:
        return False
    c = min(a.shape[2], b.shape[2])
    # the exporter may drop/add an opaque alpha channel; compare common channels
    return bool(np.array_equal(a[..., :c], b[..., :c]))


def _pixels_equal_blender(png_bytes: bytes, file_path: str) -> bool:
    """Fallback inside Blender: byte identity or decode both via bpy."""
    with open(file_path, "rb") as fh:
        if fh.read() == png_bytes:
            return True
    import tempfile
    import bpy  # noqa: F401
    import numpy as np
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.write(png_bytes)
    tmp.close()
    try:
        arrs = []
        for p in (tmp.name, file_path):
            im = bpy.data.images.load(p, check_existing=False)
            im.colorspace_settings.name = "Non-Color"
            w, h = im.size
            px = np.empty(w * h * 4, dtype=np.float32)
            im.pixels.foreach_get(px)
            arrs.append(np.round(px.reshape(h, w, 4) * 255).astype(np.uint8))
            bpy.data.images.remove(im)
        return _cmp_arrays(arrs[0][..., :3], arrs[1][..., :3])
    finally:
        os.unlink(tmp.name)


def externalize_images(glb_path: str, tex_dir_abs: str, tex_dir_rel: str = "textures") -> dict:
    """Rewrite embedded images as external URIs. Returns a report dict."""
    js, bin_ = read_glb(glb_path)
    images = js.get("images", [])
    report = {"externalized": [], "kept_embedded": []}
    if not images:
        return report
    views = js.get("bufferViews", [])
    for im in images:
        if "bufferView" not in im:
            continue
        name = im.get("name", "")
        fpath = os.path.join(tex_dir_abs, name + ".png")
        bv = views[im["bufferView"]]
        start = bv.get("byteOffset", 0)
        blob = bin_[start:start + bv["byteLength"]]
        if name and os.path.isfile(fpath) and _pixels_equal(blob, fpath):
            im["uri"] = f"{tex_dir_rel}/{name}.png"
            del im["bufferView"]
            im.pop("mimeType", None)
            report["externalized"].append(name)
        else:
            report["kept_embedded"].append(name)
    _compact(js, bin_, glb_path)
    return report


def _compact(js: dict, bin_: bytes, out_path: str) -> None:
    """Drop bufferViews no longer referenced and repack the BIN chunk."""
    views = js.get("bufferViews", [])
    used = set()
    for acc in js.get("accessors", []):
        if "bufferView" in acc:
            used.add(acc["bufferView"])
        sp = acc.get("sparse")
        if sp:
            used.add(sp["indices"]["bufferView"])
            used.add(sp["values"]["bufferView"])
    for im in js.get("images", []):
        if "bufferView" in im:
            used.add(im["bufferView"])
    for mesh in js.get("meshes", []):
        for prim in mesh.get("primitives", []):
            ext = prim.get("extensions", {}).get("KHR_draco_mesh_compression")
            if ext:
                used.add(ext["bufferView"])
    remap = {}
    new_views = []
    new_bin = bytearray()
    for i, bv in enumerate(views):
        if i not in used:
            continue
        start = bv.get("byteOffset", 0)
        blob = bin_[start:start + bv["byteLength"]]
        pad = (4 - len(new_bin) % 4) % 4
        new_bin += b"\x00" * pad
        nbv = dict(bv)
        nbv["byteOffset"] = len(new_bin)
        nbv["buffer"] = 0
        new_bin += blob
        remap[i] = len(new_views)
        new_views.append(nbv)
    for acc in js.get("accessors", []):
        if "bufferView" in acc:
            acc["bufferView"] = remap[acc["bufferView"]]
        sp = acc.get("sparse")
        if sp:
            sp["indices"]["bufferView"] = remap[sp["indices"]["bufferView"]]
            sp["values"]["bufferView"] = remap[sp["values"]["bufferView"]]
    for im in js.get("images", []):
        if "bufferView" in im:
            im["bufferView"] = remap[im["bufferView"]]
    js["bufferViews"] = new_views
    if js.get("buffers"):
        js["buffers"] = [{"byteLength": len(new_bin)}]
    write_glb(out_path, js, bytes(new_bin))


def stats(glb_path: str) -> dict:
    """Triangle count per node instance, node names, meshes/materials used."""
    js, _ = read_glb(glb_path)
    acc = js.get("accessors", [])
    meshes = js.get("meshes", [])
    mesh_tris = []
    for m in meshes:
        t = 0
        for p in m.get("primitives", []):
            mode = p.get("mode", 4)
            if mode != 4:
                continue
            if "indices" in p:
                t += acc[p["indices"]]["count"] // 3
            else:
                t += acc[p["attributes"]["POSITION"]]["count"] // 3
        mesh_tris.append(t)
    nodes = js.get("nodes", [])
    tri_total = 0
    mesh_users = {}
    for n in nodes:
        if "mesh" in n:
            tri_total += mesh_tris[n["mesh"]]
            mesh_users[n["mesh"]] = mesh_users.get(n["mesh"], 0) + 1
    shared = sum(1 for c in mesh_users.values() if c > 1)
    mats = [m.get("name", f"mat{i}") for i, m in enumerate(js.get("materials", []))]
    images = [{"name": im.get("name"), "uri": im.get("uri"), "embedded": "bufferView" in im} for im in js.get("images", [])]
    return {
        "triangles": tri_total,
        "triangles_unique_meshes": sum(mesh_tris),
        "nodes": len(nodes),
        "mesh_nodes": sum(1 for n in nodes if "mesh" in n),
        "meshes": len(meshes),
        "shared_meshes": shared,
        "materials": mats,
        "images": images,
        "node_names": [n.get("name", "") for n in nodes],
    }


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        s = stats(p)
        s.pop("node_names")
        print(p, json.dumps(s, indent=1))
