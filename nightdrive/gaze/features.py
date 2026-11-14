"""Turns MediaPipe face landmarks (478 points, iris included) into a small gaze feature vector."""

import numpy as np

# (corner_a, corner_b, upper_lid, lower_lid, iris_center) per eye
RIGHT_EYE = (33, 133, 159, 145, 468)
LEFT_EYE = (263, 362, 386, 374, 473)
NOSE_TIP = 1
BLINK_RATIO = 0.12  # lid gap / eye width below which we treat the eye as closed

# Per camera, "key" features first (they also get quadratic/interaction terms):
#   0 iris x, 1 iris y (eye-in-head), 2 iris between the lids, 3 head yaw, 4 head pitch,
#   5 head distance from the camera (tz, cm), 6-7 L2CS gaze yaw/pitch (0 when that model is off),
# then 8 blendshape look-up, 9 look-down, 10 head roll, 11-12 nose vs eyes, 13-14 head x, y (cm).
# Head pose and position come from MediaPipe's facial transformation matrix, so the model can
# separate "eyes moved" from "head moved".
N_BASE = 15  # features used by the regression
# 15-23: head rotation matrix (row-major), only used by the geometric model
N_FEATURES = 24
N_KEY = 8


def _eye(lm: np.ndarray, idx):
    a, b, up, lo, iris = (lm[i] for i in idx)
    if a[0] > b[0]:
        a, b = b, a
    width = np.linalg.norm(b - a)
    u = (b - a) / width
    v = np.array([-u[1], u[0]])
    centre = (a + b) / 2
    off = iris - centre
    iris_xy = np.array([off @ u, off @ v]) / (width / 2)
    openness = np.linalg.norm(up - lo) / width
    # where the iris sits between the lids: -1 at the upper lid, +1 at the lower lid
    lid_mid = (up + lo) / 2
    gap = max(np.linalg.norm(lo - up), 1e-6)
    lid_pos = ((iris - lid_mid) @ v) / (gap / 2)
    return iris_xy, centre, openness, lid_pos


def head_matrix(matrix: np.ndarray | None) -> np.ndarray:
    return (
        np.zeros(9)
        if matrix is None
        else np.asarray(matrix, dtype=float)[:3, :3].ravel()
    )


def head_pose(matrix: np.ndarray | None) -> np.ndarray:
    """yaw, pitch, roll (radians) and translation x, y, z (cm) from the 4x4 facial transformation matrix."""
    if matrix is None:
        return np.zeros(6)
    m = np.asarray(matrix, dtype=float)
    r = m[:3, :3]
    yaw = np.arctan2(r[0, 2], r[2, 2])
    pitch = np.arcsin(np.clip(-r[1, 2], -1, 1))
    roll = np.arctan2(r[1, 0], r[0, 0])
    return np.array([yaw, pitch, roll, *m[:3, 3]])


def gaze_features(
    landmarks: np.ndarray,
    frame_w: int,
    frame_h: int,
    blend: dict[str, float] | None = None,
    matrix: np.ndarray | None = None,
    net_gaze: tuple[float, float] | None = None,
):
    """landmarks: (>=478, 2+) normalised image coords. Returns (features, quality)."""
    lm = np.asarray(landmarks, dtype=float)[:, :2] * np.array([frame_w, frame_h])
    r_iris, r_c, r_open, r_lid = _eye(lm, RIGHT_EYE)
    l_iris, l_c, l_open, l_lid = _eye(lm, LEFT_EYE)
    iod = np.linalg.norm(l_c - r_c)
    if iod < 1e-6:
        return np.zeros(N_FEATURES), 0.0
    mid = (l_c + r_c) / 2
    axis = (l_c - r_c) / iod
    down = np.array([-axis[1], axis[0]])
    nose = lm[NOSE_TIP] - mid
    head = np.array([nose @ axis, nose @ down]) / iod
    iris = (r_iris + l_iris) / 2
    b = blend or {}
    up = (b.get("eyeLookUpLeft", 0.0) + b.get("eyeLookUpRight", 0.0)) / 2
    dn = (b.get("eyeLookDownLeft", 0.0) + b.get("eyeLookDownRight", 0.0)) / 2
    yaw, pitch, roll, tx, ty, tz = head_pose(matrix)
    quality = 0.0 if min(r_open, l_open) < BLINK_RATIO else 1.0
    values = np.array(
        [iris[0], iris[1], (r_lid + l_lid) / 2, yaw, pitch, tz]
        + list(net_gaze or (0.0, 0.0))
        + [up, dn, roll, head[0], head[1], tx, ty]
        + list(head_matrix(matrix))
    )
    return values, quality
