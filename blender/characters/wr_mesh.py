"""WILDRUSH character pipeline - step 1 (venv): SDF -> meshes + rig spec.

usage: python wr_mesh.py <fighter_id> <work_dir> [--res 0.0025] [--cloth-res 0.0032]

Outputs in <work_dir>/<id>/:
  body_hi.npz     visible body mesh (faces hidden under clothing removed) + decimation weights
  body_full.npz   full closed body mesh (bone-heat weight source for body and clothing)
  cloth_hi.npz    clothing mesh + per-face garment index + per-vertex outer-surface flag
  rig.json        bones, eyes, claws, teeth, whiskers, landmarks, garments
"""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wr_sdf import mesh_sdf, eval_points, remove_faces, keep_largest_components  # noqa: E402
import wr_anatomy  # noqa: E402
import wr_clothing  # noqa: E402


def log(*a):
    print("[wr_mesh]", *a, flush=True)


def vertex_normals(V, F):
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, F[:, k], fn)
    n = np.linalg.norm(vn, axis=1, keepdims=True)
    return vn / np.maximum(n, 1e-12)


def body_protect_weights(F, V):
    """1 = keep detail (face, ears, hands, feet), lower elsewhere."""
    w = np.full(len(V), 0.0)
    hc = F.head_frame.o
    S = F.head_scale
    dh = np.linalg.norm(V - hc, axis=1)
    w = np.maximum(w, np.clip((0.16 * S - dh) / 0.04, 0, 1) * 0.8)
    for side in ("Left", "Right"):
        hf = F.hand_frames[side]
        c = hf["wrist"] + hf["a"] * 0.06
        d = np.linalg.norm(V - c, axis=1)
        w = np.maximum(w, np.clip((0.13 - d) / 0.03, 0, 1))
        ff = F.foot_frames[side]
        c = 0.5 * (ff["ball"] + ff["toe"])
        d = np.linalg.norm(V - c, axis=1)
        w = np.maximum(w, np.clip((0.10 - d) / 0.03, 0, 1) * 0.7)
        ef = F.ear_frames[side]
        pts = np.array(ef["bone_pts"])
        d = np.min(np.linalg.norm(V[:, None, :] - pts[None], axis=2), axis=1)
        w = np.maximum(w, np.clip((0.05 - d) / 0.03, 0, 1) * 0.8)
    for e in F.eyes:
        d = np.linalg.norm(V - np.array(e["center"]), axis=1)
        w = np.maximum(w, np.clip((0.05 - d) / 0.02, 0, 1))
    m = F.mouth
    d = np.linalg.norm(V - np.array(m["frame_o"]), axis=1)
    w = np.maximum(w, np.clip((0.06 - d) / 0.02, 0, 1))
    return w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fid")
    ap.add_argument("work")
    ap.add_argument("--res", type=float, default=0.0025)
    ap.add_argument("--cloth-res", type=float, default=0.0032)
    ap.add_argument("--no-cloth", action="store_true")
    ap.add_argument("--part", default=None, help="preview: mesh only this part (e.g. head)")
    args = ap.parse_args()
    out = os.path.join(args.work, args.fid)
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    F = wr_anatomy.fighter(args.fid)
    have_cloth = not args.no_cloth
    if have_cloth:
        wr_clothing.build(F)
    log(f"built SDF for {args.fid} in {time.time() - t0:.1f}s")

    t = time.time()
    body = F.body
    if args.part:
        body = F.parts[args.part]
        have_cloth = False
    V, Fc = mesh_sdf(body, body.lo, body.hi, args.res, block=24, verbose=True)
    V, Fc = keep_largest_components(V, Fc, min_faces=400)
    log(f"body mesh: {len(V)} verts {len(Fc)} faces ({time.time() - t:.1f}s)")
    if not args.part:
        np.savez_compressed(os.path.join(out, "body_full.npz"), V=V.astype(np.float32), F=Fc.astype(np.int32))
    if have_cloth:
        cov = F.covered(V)
        keep = ~(cov[Fc[:, 0]] & cov[Fc[:, 1]] & cov[Fc[:, 2]])
        V, Fc = remove_faces(V, Fc, keep)
        log(f"body visible after cover cull: {len(V)} verts {len(Fc)} faces")
    W = body_protect_weights(F, V) if not args.part else np.zeros(len(V))
    np.savez_compressed(os.path.join(out, "body_hi.npz"), V=V.astype(np.float32), F=Fc.astype(np.int32),
                        W=W.astype(np.float32))

    if have_cloth:
        allV, allF, allG = [], [], []
        nv = 0
        for gi, g in enumerate(F.garments):
            t = time.time()
            gv, gf = mesh_sdf(g["node"], g["node"].lo, g["node"].hi, g.get("res") or args.cloth_res, block=24)
            if len(gf) == 0:
                log(f"  garment {g['name']}: EMPTY")
                continue
            gv, gf = keep_largest_components(gv, gf, min_faces=60)
            allV.append(gv)
            allF.append(gf + nv)
            allG.append(np.full(len(gf), gi, dtype=np.int32))
            nv += len(gv)
            log(f"  garment {g['name']}: {len(gv)} verts {len(gf)} faces ({time.time() - t:.1f}s)")
        CV = np.concatenate(allV)
        CF = np.concatenate(allF)
        CG = np.concatenate(allG)
        # outer-surface flag: mesh normal agrees with the outward proxy gradient
        vn = vertex_normals(CV, CF)
        e = 0.002
        grad = np.zeros_like(CV)
        for k in range(3):
            dp = np.zeros(3)
            dp[k] = e
            grad[:, k] = (eval_points(F.proxy, CV + dp, cell=0.08, m=0.05) - eval_points(F.proxy, CV - dp, cell=0.08, m=0.05))
        grad /= np.maximum(np.linalg.norm(grad, axis=1, keepdims=True), 1e-9)
        outer = (np.einsum("ij,ij->i", vn, grad) > -0.2).astype(np.float32)
        np.savez_compressed(os.path.join(out, "cloth_hi.npz"), V=CV.astype(np.float32), F=CF.astype(np.int32),
                            G=CG, O=outer)
        log(f"cloth total: {len(CV)} verts {len(CF)} faces, outer frac {outer.mean():.2f}")
    rig = dict(
        fighter=args.fid, H=F.p["H"], species=F.p["species"], sex=F.p["sex"],
        bones=F.bones, eyes=F.eyes, claws=F.claws, teeth=F.teeth, whiskers=F.whiskers,
        landmarks=F.landmarks,
        joints={k: np.asarray(v).tolist() for k, v in F.J.items()},
        mouth={k: (np.asarray(v).tolist() if isinstance(v, np.ndarray) else v) for k, v in F.mouth.items()},
        garments=[dict(name=g["name"], index=i, kind=g.get("kind", "cloth")) for i, g in enumerate(getattr(F, "garments", []))],
        tail_pts=F.tail_pts.tolist(),
        hand_frames={s: dict(wrist=np.asarray(h["wrist"]).tolist(), a=np.asarray(h["a"]).tolist(),
                             n=np.asarray(h["n"]).tolist(), fwd=np.asarray(h["fwd"]).tolist())
                     for s, h in F.hand_frames.items()},
        foot_frames={s: dict(ankle=np.asarray(f["ankle"]).tolist(), ball=np.asarray(f["ball"]).tolist(),
                             toe=np.asarray(f["toe"]).tolist()) for s, f in F.foot_frames.items()},
        head_scale=F.head_scale,
        res=args.res,
    )
    with open(os.path.join(out, "rig.json"), "w") as f:
        json.dump(rig, f, indent=1)
    log(f"done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
