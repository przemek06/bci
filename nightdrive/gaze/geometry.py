"""Geometric gaze model: estimates where each camera is from the user's head motion, then
intersects each camera's 3D gaze ray (L2CS direction from the 3D eye position) with the screen.

Screen frame (cm): origin at the screen centre, x right, y up, z toward the user.
Camera frame: MediaPipe's (x right in the image, y up, z toward the viewer, face at z < 0).
Per camera we solve for rotation, translation, depth scale and a gaze angle bias; the eye
offset in the head frame is shared. Calibration dots are the supervision, so a camera
placed anywhere (phones on a stand, a laptop camera) ends up in the right place.
"""

import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from .. import settings as S
from .features import N_BASE

# per-camera feature indices (see features.py)
I_TZ, I_YAW, I_PITCH, I_TX, I_TY, I_ROT = 5, 6, 7, 13, 14, 15
MAX_SAMPLES = 700
FOLDS = 4
SIGNS = [(sx, sy) for sx in (1, -1) for sy in (1, -1)]
PRIOR_ROT0 = np.array([0.0, np.pi, 0.0])  # camera looking at the user from the screen


def _blocks(f: np.ndarray, block: int) -> list[np.ndarray]:
    return [f[:, c * block : (c + 1) * block] for c in range(f.shape[1] // block)]


def _valid(b: np.ndarray) -> np.ndarray:
    return np.abs(b[:, I_ROT : I_ROT + 9]).sum(axis=1) > 1e-6


def _umeyama(src: np.ndarray, dst: np.ndarray):
    """Similarity (scale, R, t) with dst ≈ s R src + t."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    a, b = src - mu_s, dst - mu_d
    u, d, vt = np.linalg.svd(b.T @ a / len(src))
    s_mat = np.eye(3)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        s_mat[2, 2] = -1
    r = u @ s_mat @ vt
    var = (a**2).sum() / len(src)
    scale = float(np.trace(np.diag(d) @ s_mat) / max(var, 1e-9))
    return scale, r, mu_d - scale * r @ mu_s


class _Layout:
    """Parameter vector: [eye offset(3)] + per camera [rotvec(3), t(3), scale, yaw bias, pitch bias]."""

    def __init__(self, n_cams: int):
        self.n = n_cams

    def size(self) -> int:
        return 3 + 9 * self.n

    def split(self, p: np.ndarray):
        off = p[:3]
        cams = [p[3 + 9 * i : 3 + 9 * (i + 1)] for i in range(self.n)]
        return off, cams


def _rays(p: np.ndarray, layout: _Layout, blocks: list[np.ndarray], signs: list[tuple]):
    """Per camera: eye position (n,3), gaze direction (n,3), screen hit (n,2) in cm."""
    off, cams = layout.split(p)
    out = []
    for b, c, (sx, sy) in zip(blocks, cams, signs):
        r_cam = Rotation.from_rotvec(c[:3]).as_matrix()
        r_head = b[:, I_ROT : I_ROT + 9].reshape(-1, 3, 3)
        pos = np.column_stack([b[:, I_TX], b[:, I_TY], b[:, I_TZ]]) + r_head @ off
        eye = (r_cam @ (c[6] * pos).T).T + c[3:6]
        yaw, pitch = b[:, I_YAW] + c[7], b[:, I_PITCH] + c[8]
        d_cam = np.column_stack(
            [
                sx * np.cos(pitch) * np.sin(yaw),
                sy * np.sin(pitch),
                np.cos(pitch) * np.cos(yaw),
            ]
        )
        g = (r_cam @ d_cam.T).T
        lam = eye[:, 2] / np.maximum(-g[:, 2], 0.2)
        hit = eye[:, :2] + lam[:, None] * g[:, :2]
        out.append((eye, g, hit))
    return out


class GeometricCalibration:
    method = "geometry"

    def __init__(
        self,
        params: np.ndarray,
        signs: list[tuple],
        affine: np.ndarray,
        block: int,
        n_features: int,
        screen_cm: tuple[float, float],
        error_xy: tuple[float, float] = (0.0, 0.0),
        tag: str = "",
    ):
        self.params = params
        self.signs = signs
        self.affine = affine  # (3, 2): hit_norm -> corrected, applied to [x, y, 1]
        self.block = block
        self.raw_block = block
        self.n_features = n_features
        self.screen_cm = screen_cm
        self.error_xy = error_xy
        self.error = float(np.hypot(*error_xy))
        self.tag = tag
        self.layout = _Layout(n_features // block)

    def hits(self, features: np.ndarray):
        f = np.atleast_2d(features)
        blocks = _blocks(f, self.block)
        rays = _rays(self.params, self.layout, blocks, self.signs)
        w, h = self.screen_cm
        valid = np.array([_valid(b) for b in blocks])  # (cams, n)
        hit = np.array([r[2] for r in rays])  # (cams, n, 2)
        return valid, hit / np.array([w, h]) * np.array([1, -1]) + 0.5

    def predict(self, features: np.ndarray) -> np.ndarray:
        valid, hit = self.hits(features)
        wts = valid[..., None].astype(float)
        fused = (hit * wts).sum(0) / np.maximum(wts.sum(0), 1e-9)
        fused[wts.sum(0)[:, 0] == 0] = 0.5
        xy1 = np.column_stack([np.clip(fused, -1, 2), np.ones(len(fused))])
        return xy1 @ self.affine

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "kind": "geometry",
                    "params": self.params.tolist(),
                    "signs": self.signs,
                    "affine": self.affine.tolist(),
                    "block": self.block,
                    "n_features": self.n_features,
                    "screen_cm": list(self.screen_cm),
                    "error_xy": list(self.error_xy),
                    "tag": self.tag,
                }
            )
        )

    @classmethod
    def from_dict(cls, d: dict) -> "GeometricCalibration":
        return cls(
            np.array(d["params"]),
            [tuple(s) for s in d["signs"]],
            np.array(d["affine"]),
            int(d["block"]),
            int(d["n_features"]),
            tuple(d["screen_cm"]),
            tuple(d["error_xy"]),
            d.get("tag", ""),
        )


def _initial(blocks, targets_cm, screen_cm):
    """Starting camera poses: camera 0 at the top of the screen, the others via a similarity
    fit of the synchronised head positions onto camera 0's."""
    n = len(blocks)
    layout = _Layout(n)
    p = np.zeros(layout.size())
    p[:3] = [0.0, 3.0, 5.0]
    r0 = Rotation.from_rotvec(PRIOR_ROT0).as_matrix()
    t0 = np.array([0.0, screen_cm[1] / 2 + S.GAZE_CAM0_ABOVE_SCREEN_CM, 0.0])
    pos = [np.column_stack([b[:, I_TX], b[:, I_TY], b[:, I_TZ]]) for b in blocks]
    ok0 = _valid(blocks[0])
    for i in range(n):
        o = 3 + 9 * i
        if i == 0:
            p[o : o + 3] = PRIOR_ROT0
            p[o + 3 : o + 6] = t0
            p[o + 6] = 1.0
            continue
        both = ok0 & _valid(blocks[i])
        if both.sum() < 20:
            p[o : o + 3] = PRIOR_ROT0
            p[o + 3 : o + 6] = t0
            p[o + 6] = 1.0
            continue
        s, r, t = _umeyama(pos[i][both], pos[0][both])
        p[o : o + 3] = Rotation.from_matrix(r0 @ r).as_rotvec()
        p[o + 3 : o + 6] = r0 @ t + t0
        p[o + 6] = s
    return layout, p


def _pick_signs(p, layout, blocks, targets_cm):
    signs = []
    for i, b in enumerate(blocks):
        best = None
        for s in SIGNS:
            trial = [(1, 1)] * len(blocks)
            trial[i] = s
            hit = _rays(p, layout, blocks, trial)[i][2]
            ok = _valid(b)
            err = np.median(np.linalg.norm(hit[ok] - targets_cm[ok], axis=1))
            if best is None or err < best[0]:
                best = (err, s)
        signs.append(best[1])
    return signs


def _solve(p0, layout, blocks, targets_cm, signs, prior, max_nfev=60):
    valid = [_valid(b) for b in blocks]
    n = len(blocks)

    def resid(p):
        rays = _rays(p, layout, blocks, signs)
        parts = []
        for (eye, g, hit), ok in zip(rays, valid):
            parts.append(((hit - targets_cm) * ok[:, None]).ravel())
        for i in range(1, n):
            both = valid[0] & valid[i]
            parts.append(((rays[i][0] - rays[0][0]) * both[:, None]).ravel() * 0.5)
        _, cams = layout.split(p)
        pr = layout.split(prior)[1]
        parts.append((cams[0][:3] - pr[0][:3]) * 8.0)
        parts.append((cams[0][3:6] - pr[0][3:6]) * 0.5)
        for c in cams:
            parts.append(c[7:9] * 20.0)  # keep angle biases small
        parts.append((p[:3] - prior[:3]) * 0.5)
        return np.concatenate(parts)

    res = least_squares(
        resid, p0, loss="soft_l1", f_scale=4.0, max_nfev=max_nfev, x_scale="jac"
    )
    return res.x


def _affine(hit_norm, targets, lam=0.05):
    x = np.column_stack([hit_norm, np.ones(len(hit_norm))])
    ident = np.vstack([np.eye(2), np.zeros((1, 2))])
    reg = lam * len(x) * np.eye(3)
    reg[2, 2] = 0
    return np.linalg.solve(x.T @ x + reg, x.T @ targets + reg @ ident)


def fit_geometry(
    features: np.ndarray,
    targets: np.ndarray,
    block: int,
    screen_cm: tuple[float, float] | None = None,
) -> GeometricCalibration:
    """Fit camera poses and gaze geometry. Reported error is cross-validated by target group."""
    screen_cm = screen_cm or S.GAZE_SCREEN_CM
    features = np.asarray(features, float)
    targets = np.asarray(targets, float)
    rng = np.random.default_rng(0)
    if len(features) > MAX_SAMPLES:
        keep = np.sort(rng.choice(len(features), MAX_SAMPLES, replace=False))
        features, targets = features[keep], targets[keep]
    w, h = screen_cm
    to_cm = lambda t: np.column_stack([(t[:, 0] - 0.5) * w, (0.5 - t[:, 1]) * h])
    blocks = _blocks(features, block)
    tcm = to_cm(targets)
    layout, p0 = _initial(blocks, tcm, screen_cm)
    signs = _pick_signs(p0, layout, blocks, tcm)
    p = _solve(p0, layout, blocks, tcm, signs, p0)

    def make(params, aff):
        return GeometricCalibration(
            params, signs, aff, block, features.shape[1], screen_cm
        )

    ident = np.vstack([np.eye(2), np.zeros((1, 2))])
    cal = make(p, ident)
    groups = np.unique(targets, axis=0)
    sq = []
    for k in range(min(FOLDS, len(groups))):
        held = np.zeros(len(features), bool)
        for gi, g in enumerate(groups):
            if gi % FOLDS == k:
                held |= np.all(targets == g, axis=1)
        if held.all() or not held.any():
            continue
        tr = [b[~held] for b in blocks]
        pk = _solve(p, layout, tr, tcm[~held], signs, p0, max_nfev=15)
        ck = make(pk, ident)
        fused_tr = ck.predict(features[~held])
        aff = _affine(fused_tr, targets[~held])
        pred = np.column_stack([ck.predict(features[held]), np.ones(held.sum())]) @ aff
        sq.append((pred - targets[held]) ** 2)
    cal.affine = _affine(cal.predict(features), targets)
    if sq:
        mse = np.concatenate(sq).mean(axis=0)
        cal.error_xy = (float(np.sqrt(mse[0])), float(np.sqrt(mse[1])))
        cal.error = float(np.sqrt(mse.sum()))
    return cal


def usable(features: np.ndarray, block: int) -> bool:
    """Geometry needs L2CS gaze angles and head rotation (not present for the MediaPipe-only model)."""
    f = np.asarray(features, float)
    return (
        block > N_BASE
        and bool(np.any(np.abs(f[:, I_YAW]) > 1e-9))
        and bool(_valid(f[:, :block]).any())
    )
