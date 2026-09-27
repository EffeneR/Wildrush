"""WILDRUSH character pipeline - signed distance field sculpting kernel (runs in the venv).

Primitives (exact or bounded SDFs), smooth CSG operators, displacement, and a
block-sparse marching-cubes mesher.  Every node knows a conservative bounding box,
so evaluation over a spatial block only touches the primitives that can influence it.

Coordinates: Blender object space, metres, Z up, character faces -Y (D-003).
"""
import numpy as np

BIG = 1.0e3


# ----------------------------------------------------------------------------- helpers
def v3(*a):
    if len(a) == 1:
        return np.asarray(a[0], dtype=np.float64)
    return np.asarray(a, dtype=np.float64)


def normalize(v):
    v = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def dot_rows(a, b):
    return np.einsum("ij,ij->i", a, b)


def frame_from_axis(axis, up_hint=(0.0, 0.0, 1.0)):
    """Rotation matrix whose columns are (x, y, z) with local z = axis."""
    z = normalize(axis)
    up = np.asarray(up_hint, dtype=np.float64)
    if abs(np.dot(up, z)) > 0.95:
        up = np.array([0.0, 1.0, 0.0]) if abs(z[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    x = normalize(np.cross(up, z))
    y = np.cross(z, x)
    return np.stack([x, y, z], axis=1)


def rot_x(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float64)


def rot_y(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float64)


def rot_z(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)


def smin(a, b, k):
    if k <= 0.0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smax(a, b, k):
    return -smin(-a, -b, k)


def boxes_overlap(lo1, hi1, lo2, hi2, margin):
    return bool(np.all(lo1 - margin <= hi2) and np.all(hi1 + margin >= lo2))


# ----------------------------------------------------------------------------- noise
_PERM_CACHE = {}


def _perm(seed):
    if seed not in _PERM_CACHE:
        rng = np.random.RandomState(seed & 0x7FFFFFFF)
        p = rng.permutation(256).astype(np.int64)
        _PERM_CACHE[seed] = np.concatenate([p, p])
    return _PERM_CACHE[seed]


_GRAD = np.array([[1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0], [1, 0, 1], [-1, 0, 1],
                  [1, 0, -1], [-1, 0, -1], [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1],
                  [1, 1, 0], [-1, 1, 0], [0, -1, 1], [0, -1, -1]], dtype=np.float64)


def perlin3(P, freq=1.0, seed=0):
    """Classic gradient noise, vectorised. P (N,3). Returns roughly [-1, 1]."""
    p = _perm(seed)
    Q = np.asarray(P, dtype=np.float64) * freq
    Qi = np.floor(Q)
    f = Q - Qi
    Qi = Qi.astype(np.int64) & 255
    u = f * f * f * (f * (f * 6 - 15) + 10)
    X, Y, Z = Qi[:, 0], Qi[:, 1], Qi[:, 2]
    res = 0.0
    acc = []
    for dz in (0, 1):
        for dy in (0, 1):
            for dx in (0, 1):
                h = p[p[p[X + dx] + Y + dy] + Z + dz] & 15
                g = _GRAD[h]
                val = g[:, 0] * (f[:, 0] - dx) + g[:, 1] * (f[:, 1] - dy) + g[:, 2] * (f[:, 2] - dz)
                acc.append(val)
    x00 = acc[0] + u[:, 0] * (acc[1] - acc[0])
    x10 = acc[2] + u[:, 0] * (acc[3] - acc[2])
    x01 = acc[4] + u[:, 0] * (acc[5] - acc[4])
    x11 = acc[6] + u[:, 0] * (acc[7] - acc[6])
    y0 = x00 + u[:, 1] * (x10 - x00)
    y1 = x01 + u[:, 1] * (x11 - x01)
    res = y0 + u[:, 2] * (y1 - y0)
    return res * 1.1


def fbm3(P, freq=1.0, octaves=4, seed=0, lac=2.0, gain=0.5):
    total = 0.0
    amp = 1.0
    norm = 0.0
    f = freq
    for o in range(octaves):
        total = total + amp * perlin3(P, f, seed + 17 * o)
        norm += amp
        amp *= gain
        f *= lac
    return total / norm


# ----------------------------------------------------------------------------- nodes
class Node:
    lo = None
    hi = None
    tag = None

    def ev(self, P, blo, bhi, m):
        raise NotImplementedError

    def __call__(self, P):
        P = np.asarray(P, dtype=np.float64)
        return self.ev(P, P.min(axis=0), P.max(axis=0), 0.0)


class Sphere(Node):
    def __init__(self, c, r, tag=None):
        self.c = v3(c)
        self.r = float(r)
        self.lo = self.c - r
        self.hi = self.c + r
        self.tag = tag

    def ev(self, P, blo, bhi, m):
        D = P - self.c
        return np.sqrt(dot_rows(D, D)) - self.r


class Ellipsoid(Node):
    """Bounded ellipsoid SDF (iq). R columns = local axes in world space."""

    def __init__(self, c, r, R=None, tag=None):
        self.c = v3(c)
        self.r = v3(r)
        self.R = np.eye(3) if R is None else np.asarray(R, dtype=np.float64)
        ext = np.sqrt(((self.R * self.r[None, :]) ** 2).sum(axis=1))
        self.lo = self.c - ext
        self.hi = self.c + ext
        self.tag = tag

    def ev(self, P, blo, bhi, m):
        q = (P - self.c) @ self.R
        a = q / self.r
        b = q / (self.r * self.r)
        k0 = np.sqrt(dot_rows(a, a))
        k1 = np.sqrt(dot_rows(b, b))
        return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


class RoundCone(Node):
    """Capsule with different radii at the ends (exact, iq)."""

    def __init__(self, a, b, ra, rb, tag=None):
        self.a = v3(a)
        self.b = v3(b)
        self.ra = float(ra)
        self.rb = float(rb)
        ba = self.b - self.a
        self.ba = ba
        self.l2 = float(ba @ ba)
        self.rr = self.ra - self.rb
        self.a2 = self.l2 - self.rr * self.rr
        self.il2 = 1.0 / max(self.l2, 1e-12)
        self.degenerate = self.a2 <= 1e-10
        self.lo = np.minimum(self.a - self.ra, self.b - self.rb)
        self.hi = np.maximum(self.a + self.ra, self.b + self.rb)
        self.tag = tag

    def ev(self, P, blo, bhi, m):
        if self.degenerate:
            if self.ra >= self.rb:
                D = P - self.a
                return np.sqrt(dot_rows(D, D)) - self.ra
            D = P - self.b
            return np.sqrt(dot_rows(D, D)) - self.rb
        pa = P - self.a
        y = pa @ self.ba
        z = y - self.l2
        q = pa * self.l2 - y[:, None] * self.ba[None, :]
        x2 = dot_rows(q, q)
        y2 = y * y * self.l2
        z2 = z * z * self.l2
        k = np.sign(self.rr) * self.rr * self.rr * x2
        d1 = np.sqrt(x2 + z2) * self.il2 - self.rb
        d2 = np.sqrt(x2 + y2) * self.il2 - self.ra
        d3 = (np.sqrt(np.maximum(x2 * self.a2 * self.il2, 0.0)) + y * self.rr) * self.il2 - self.ra
        return np.where(np.sign(z) * self.a2 * z2 > k, d1, np.where(np.sign(y) * self.a2 * y2 < k, d2, d3))


def Capsule(a, b, r, tag=None):
    return RoundCone(a, b, r, r, tag)


class RoundBox(Node):
    def __init__(self, c, half, R=None, rnd=0.0, tag=None):
        self.c = v3(c)
        self.half = v3(half)
        self.R = np.eye(3) if R is None else np.asarray(R, dtype=np.float64)
        self.rnd = float(rnd)
        ext = np.abs(self.R) @ self.half
        self.lo = self.c - ext
        self.hi = self.c + ext
        self.tag = tag

    def ev(self, P, blo, bhi, m):
        q = np.abs((P - self.c) @ self.R) - (self.half - self.rnd)
        qa = np.maximum(q, 0.0)
        return np.sqrt(dot_rows(qa, qa)) + np.minimum(q.max(axis=1), 0.0) - self.rnd


class Torus(Node):
    """Torus in the local XY plane (axis = local z)."""

    def __init__(self, c, R, major, minor, tag=None):
        self.c = v3(c)
        self.R = np.asarray(R, dtype=np.float64)
        self.major = float(major)
        self.minor = float(minor)
        e = major + minor
        ext = np.abs(self.R) @ np.array([e, e, minor])
        self.lo = self.c - ext
        self.hi = self.c + ext
        self.tag = tag

    def ev(self, P, blo, bhi, m):
        q = (P - self.c) @ self.R
        qx = np.sqrt(q[:, 0] ** 2 + q[:, 1] ** 2) - self.major
        return np.sqrt(qx * qx + q[:, 2] ** 2) - self.minor


class HalfSpace(Node):
    """d = dot(P - p0, n)  (inside where negative).  Unbounded."""

    def __init__(self, p0, n, tag=None):
        self.p0 = v3(p0)
        self.n = normalize(n)
        self.lo = np.full(3, -BIG)
        self.hi = np.full(3, BIG)
        self.tag = tag

    def ev(self, P, blo, bhi, m):
        return (P - self.p0) @ self.n


class Func(Node):
    """Arbitrary field function fn(P) with a user bbox."""

    def __init__(self, fn, lo, hi, tag=None):
        self.fn = fn
        self.lo = v3(lo)
        self.hi = v3(hi)
        self.tag = tag

    def ev(self, P, blo, bhi, m):
        return self.fn(P)


class Union(Node):
    def __init__(self, children, k=0.0, tag=None):
        self.children = [c for c in children if c is not None]
        self.k = float(k)
        self.lo = np.min([c.lo for c in self.children], axis=0)
        self.hi = np.max([c.hi for c in self.children], axis=0)
        self.tag = tag

    def ev(self, P, blo, bhi, m):
        d = None
        mm = m + self.k
        for c in self.children:
            if not boxes_overlap(c.lo, c.hi, blo, bhi, mm):
                continue
            dc = c.ev(P, blo, bhi, mm)
            d = dc if d is None else smin(d, dc, self.k)
        if d is None:
            return np.full(P.shape[0], BIG)
        return d


class Subtract(Node):
    """a minus b (smooth)."""

    def __init__(self, a, b, k=0.0, tag=None):
        self.a = a
        self.b = b
        self.k = float(k)
        self.lo = a.lo
        self.hi = a.hi
        self.tag = tag

    def ev(self, P, blo, bhi, m):
        if not boxes_overlap(self.a.lo, self.a.hi, blo, bhi, m):
            return np.full(P.shape[0], BIG)
        da = self.a.ev(P, blo, bhi, m + self.k)
        if not boxes_overlap(self.b.lo, self.b.hi, blo, bhi, m + self.k):
            return da
        db = self.b.ev(P, blo, bhi, m + self.k)
        return smax(da, -db, self.k)


class Intersect(Node):
    def __init__(self, a, b, k=0.0, tag=None):
        self.a = a
        self.b = b
        self.k = float(k)
        self.lo = np.maximum(a.lo, b.lo)
        self.hi = np.minimum(a.hi, b.hi)
        self.tag = tag

    def ev(self, P, blo, bhi, m):
        if not boxes_overlap(self.lo, self.hi, blo, bhi, m + self.k):
            return np.full(P.shape[0], BIG)
        da = self.a.ev(P, blo, bhi, m + self.k)
        db = self.b.ev(P, blo, bhi, m + self.k)
        return smax(da, db, self.k)


class Shell(Node):
    """Hollow shell around child's iso-level `offset`, half thickness `half`."""

    def __init__(self, child, offset, half, tag=None):
        self.child = child
        self.offset = float(offset)
        self.half = float(half)
        e = max(self.offset + self.half, 0.0)
        self.lo = child.lo - e
        self.hi = child.hi + e
        self.tag = tag

    def ev(self, P, blo, bhi, m):
        e = abs(self.offset) + self.half
        d = self.child.ev(P, blo, bhi, m + e)
        return np.abs(d - self.offset) - self.half


class Offset(Node):
    def __init__(self, child, r, tag=None):
        self.child = child
        self.r = float(r)
        self.lo = child.lo - max(r, 0.0)
        self.hi = child.hi + max(r, 0.0)
        self.tag = tag

    def ev(self, P, blo, bhi, m):
        return self.child.ev(P, blo, bhi, m + abs(self.r)) - self.r


class Displace(Node):
    """d - fn(P);  fn returns an outward displacement in metres, |fn| <= amp."""

    def __init__(self, child, fn, amp, tag=None):
        self.child = child
        self.fn = fn
        self.amp = float(amp)
        self.lo = child.lo - amp
        self.hi = child.hi + amp
        self.tag = tag

    def ev(self, P, blo, bhi, m):
        d = self.child.ev(P, blo, bhi, m + self.amp)
        near = np.abs(d) < (self.amp * 3.0 + m + 0.01)
        if np.any(near):
            d = d.copy()
            d[near] = d[near] - self.fn(P[near])
        return d


class Scale(Node):
    """Evaluate child in a warped space: P' = c + (P - c) / s  (non-uniform s allowed).
    Distances are scaled by min(s) (bound)."""

    def __init__(self, child, c, s, tag=None):
        self.child = child
        self.c = v3(c)
        self.s = v3(s)
        self.lo = self.c + (child.lo - self.c) * self.s
        self.hi = self.c + (child.hi - self.c) * self.s
        lo = np.minimum(self.lo, self.hi)
        hi = np.maximum(self.lo, self.hi)
        self.lo, self.hi = lo, hi
        self.tag = tag

    def ev(self, P, blo, bhi, m):
        Q = self.c + (P - self.c) / self.s
        ql = self.c + (blo - self.c) / self.s
        qh = self.c + (bhi - self.c) / self.s
        return self.child.ev(Q, np.minimum(ql, qh), np.maximum(ql, qh), m / self.s.min()) * self.s.min()


# ----------------------------------------------------------------------------- evaluation
def eval_points(node, P, cell=0.06, m=0.0):
    """Evaluate node at arbitrary points, grouping them spatially for culling."""
    P = np.asarray(P, dtype=np.float64)
    out = np.empty(P.shape[0], dtype=np.float64)
    if P.shape[0] == 0:
        return out
    key = np.floor(P / cell).astype(np.int64)
    key -= key.min(axis=0)
    dims = key.max(axis=0) + 1
    lin = (key[:, 0] * dims[1] + key[:, 1]) * dims[2] + key[:, 2]
    order = np.argsort(lin, kind="stable")
    lin_s = lin[order]
    bounds = np.flatnonzero(np.diff(lin_s)) + 1
    starts = np.concatenate([[0], bounds])
    ends = np.concatenate([bounds, [len(lin_s)]])
    for s, e in zip(starts, ends):
        idx = order[s:e]
        Q = P[idx]
        out[idx] = node.ev(Q, Q.min(axis=0), Q.max(axis=0), m)
    return out


def mesh_sdf(node, lo, hi, h, block=24, band=1.6, verbose=False):
    """Block-sparse marching cubes.  Returns (verts float64 (V,3), faces int64 (F,3))."""
    from skimage.measure import marching_cubes

    lo = np.floor(v3(lo) / h) * h - 2 * h
    hi = np.ceil(v3(hi) / h) * h + 2 * h
    n = np.ceil((hi - lo) / h).astype(int) + 1
    nb = np.ceil((n - 1) / block).astype(int)
    # coarse classification at block centres
    ib = np.stack(np.meshgrid(np.arange(nb[0]), np.arange(nb[1]), np.arange(nb[2]), indexing="ij"), -1).reshape(-1, 3)
    centres = lo + (ib + 0.5) * block * h
    dc = eval_points(node, centres, cell=block * h * 2)
    half_diag = np.sqrt(3.0) * 0.5 * block * h
    active = np.abs(dc) < half_diag * band + 2 * h
    ib = ib[active]
    if verbose:
        print(f"  mesh_sdf: grid {n.tolist()} blocks {nb.tolist()} active {len(ib)}/{len(active)}")
    all_v = []
    all_f = []
    nv = 0
    ar = np.arange(block + 1)
    gi = np.stack(np.meshgrid(ar, ar, ar, indexing="ij"), -1).reshape(-1, 3)
    for b in ib:
        base = b * block
        idx = base[None, :] + gi
        P = lo + idx * h
        blo = P.min(axis=0)
        bhi = P.max(axis=0)
        d = node.ev(P, blo, bhi, 3 * h)
        vol = d.reshape(block + 1, block + 1, block + 1)
        if vol.min() >= 0.0 or vol.max() <= 0.0:
            continue
        try:
            verts, faces, _, _ = marching_cubes(vol, 0.0, allow_degenerate=False)
        except (ValueError, RuntimeError):
            continue
        if len(faces) == 0:
            continue
        all_v.append(verts + base[None, :])
        all_f.append(faces + nv)
        nv += len(verts)
    if not all_v:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    V = np.concatenate(all_v)
    F = np.concatenate(all_f).astype(np.int64)
    # weld duplicates on block borders (vertices lie on lattice edges)
    key = np.round(V * 8192.0).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    V = V[first]
    F = inv[F]
    ok = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
    F = F[ok]
    V = lo + V * h
    # orientation: make outward (positive signed volume)
    vol = np.einsum("ij,ij->i", V[F[:, 0]], np.cross(V[F[:, 1]], V[F[:, 2]])).sum() / 6.0
    if vol < 0:
        F = F[:, ::-1]
    return V, F


def remove_faces(V, F, face_mask_keep):
    F = F[face_mask_keep]
    used = np.zeros(len(V), dtype=bool)
    used[F.ravel()] = True
    remap = -np.ones(len(V), dtype=np.int64)
    remap[used] = np.arange(used.sum())
    return V[used], remap[F]


def keep_largest_components(V, F, min_faces=200):
    """Drop tiny disconnected islands (marching-cube specks)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    nV = len(V)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    A = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(nV, nV))
    ncomp, lab = connected_components(A, directed=False)
    flab = lab[F[:, 0]]
    counts = np.bincount(flab, minlength=ncomp)
    keep = counts[flab] >= min_faces
    return remove_faces(V, F, keep)
