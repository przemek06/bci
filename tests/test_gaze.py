import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pygame

from nightdrive import settings as S
from nightdrive.gaze.base import GazeFeatures, GazePoint
from nightdrive.gaze.calibration import TARGETS, GazeCalibration, design_matrix
from nightdrive.gaze.features import N_FEATURES, gaze_features
from nightdrive.gaze.session import CalibrationSession
from nightdrive.gaze.tracker import GazeMonitor, GazeTracker


def fake_eye_features(xy, rng):
    """Synthetic camera features: iris offset roughly linear in the gaze target, plus noise."""
    x, y = xy
    f = np.zeros(N_FEATURES)
    f[:3] = [(x - 0.5) * 1.2, (y - 0.5) * 0.6, (y - 0.5) * 1.5]
    f[:3] += 0.01 * rng.standard_normal(3)
    f[3:] += 0.002 * rng.standard_normal(N_FEATURES - 3)
    return f


def test_calibration_recovers_targets_and_roundtrips(tmp_path):
    rng = np.random.default_rng(0)
    feats, labels = [], []
    for t in TARGETS:
        for _ in range(20):
            feats.append(fake_eye_features(t, rng))
            labels.append(t)
    cal = GazeCalibration.fit(np.array(feats), np.array(labels))
    assert cal.error < 0.05
    pred = cal.predict(fake_eye_features((0.3, 0.7), rng))[0]
    assert abs(pred[0] - 0.3) < 0.08 and abs(pred[1] - 0.7) < 0.08
    cal.save(tmp_path / "c.json")
    loaded = GazeCalibration.load(tmp_path / "c.json")
    assert np.allclose(loaded.weights, cal.weights)
    assert GazeCalibration.load(tmp_path / "missing.json") is None


def test_two_cameras_fuse_and_calibrate():
    rng = np.random.default_rng(2)
    feats, labels = [], []
    for t in TARGETS:
        for _ in range(20):
            feats.append(
                np.concatenate([fake_eye_features(t, rng), fake_eye_features(t, rng)])
            )
            labels.append(t)
    cal = GazeCalibration.fit(np.array(feats), np.array(labels), block=N_FEATURES)
    assert cal.raw_block == N_FEATURES and cal.n_features == 2 * N_FEATURES
    assert cal.error < 0.05


def test_session_collects_all_targets_and_repeats_when_starved():
    rng = np.random.default_rng(1)
    s = CalibrationSession()
    t, dt = 0.0, 1 / 30
    # no samples for the first target's window: it must be repeated
    for _ in range(int((S.CALIB_SETTLE + S.CALIB_SAMPLE) / dt) + 2):
        s.update(dt, None)
    assert s.index == 0
    for _ in range(10000):
        if s.done:
            break
        t += dt
        tx, ty = s.target
        s.update(dt, GazeFeatures(fake_eye_features((tx, ty), rng), 1.0, t))
    assert s.done
    assert s.fit().error < 0.05


def test_gaze_features_blink_and_shift():
    lm = np.zeros((478, 2))
    # right eye then left eye: corners, lids, iris centre (image coords)
    for (a, b, up, lo, iris), cx in (
        ((33, 133, 159, 145, 468), 0.4),
        ((263, 362, 386, 374, 473), 0.6),
    ):
        lm[a], lm[b] = (cx - 0.04, 0.5), (cx + 0.04, 0.5)
        lm[up], lm[lo] = (cx, 0.49), (cx, 0.51)
        lm[iris] = (cx, 0.5)
    lm[1] = (0.5, 0.6)
    base, q = gaze_features(lm, 640, 480)
    assert base.shape == (N_FEATURES,) and q == 1.0
    assert abs(base[0]) < 1e-9
    lm[468] += (0.02, 0)
    lm[473] += (0.02, 0)
    looked, _ = gaze_features(lm, 640, 480)
    assert looked[0] > 0.4
    with_blend, _ = gaze_features(
        lm, 640, 480, {"eyeLookUpLeft": 0.6, "eyeLookUpRight": 0.4}
    )
    assert abs(with_blend[8] - 0.5) < 1e-9
    lm[159], lm[145] = (0.4, 0.5), (0.4, 0.5)
    assert gaze_features(lm, 640, 480)[1] == 0.0


def test_monitor_triggers_only_on_sustained_quality_look_away():
    m = GazeMonitor()
    away = GazePoint(0.02, 0.5, 1.0, 0.0)
    ahead = GazePoint(0.5, 0.5, 1.0, 0.0)
    for _ in range(int(S.GAZE_AWAY_TIME * 10) - 1):
        assert not m.update(0.1, away)
    assert not m.update(0.1, ahead)  # glancing back resets the timer
    assert not m.update(0.1, GazePoint(0.02, 0.5, 0.0, 0.0))  # poor quality ignored
    assert not m.update(0.1, None)
    fired = [m.update(0.1, away) for _ in range(int(S.GAZE_AWAY_TIME * 10) + 1)]
    assert sum(fired) == 1
    assert not any(
        m.update(0.1, away) for _ in range(int(S.GAZE_AWAY_TIME * 10))
    )  # cooldown


class FakeSource:
    needs_calibration = True

    def __init__(self):
        self.f = None

    def start(self): ...
    def stop(self): ...
    def latest(self):
        return self.f

    def status(self):
        return "fake"


def test_tracker_needs_calibration_and_drops_stale():
    src = FakeSource()
    tr = GazeTracker(src)
    src.f = GazeFeatures(np.zeros(N_FEATURES), 1.0, 10.0)
    assert tr.update(10.0) is None  # not calibrated
    w = np.zeros((design_matrix(np.zeros(N_FEATURES), N_FEATURES).shape[1], 2))
    w[0] = (0.5, 0.25)
    tr.set_calibration(GazeCalibration(w, N_FEATURES))
    p = tr.update(10.0)
    assert (round(p.x, 2), round(p.y, 2)) == (0.5, 0.25)
    assert tr.update(10.0 + S.GAZE_STALE + 0.1) is None


def test_menu_toggle_and_calibration_scene_headless():
    from nightdrive.app import App
    from nightdrive.calibration_scene import CalibrationScene
    from nightdrive.scenes import DriveScene

    app = App(seed=1, gaze="mouse")
    assert app.gaze and app.gaze.ready
    app.set_scene(DriveScene(app, app.scene.world))
    for _ in range(120):
        app.gaze.update()
        app.scene.update(1 / 60)
        app.scene.draw(app.canvas)
    app.disable_gaze()
    app.gaze_mode = "webcam"
    app.enable_gaze()  # thread starts; camera may or may not exist
    app.set_scene(CalibrationScene(app, app.scene.world))
    app.scene.update(1 / 60)
    app.scene.draw(app.canvas)
    app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    app.quit()
    pygame.quit()


def test_calibration_scene_runs_fullscreen_and_restores_window():
    import time

    from nightdrive.app import App
    from nightdrive.calibration_scene import RESULT, CalibrationScene

    app = App(seed=1)
    src = FakeSource()
    app.gaze = GazeTracker(src)
    rng = np.random.default_rng(3)
    scene = CalibrationScene(app, app.scene.world)
    app.set_scene(scene)
    src.f = GazeFeatures(fake_eye_features((0.5, 0.5), rng), 1.0, time.monotonic())
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert app.fullscreen and scene.draws_window
    for i in range(4000):
        if scene.session.target is not None:
            src.f = GazeFeatures(
                fake_eye_features(scene.session.target, rng), 1.0, i / 30
            )
        scene.update(1 / 30)
        if scene.draws_window:
            scene.draw_window(pygame.display.get_surface())
        if scene.state == RESULT:
            break
    assert scene.state == RESULT and not app.fullscreen
    assert max(scene.cal.error_xy) < 0.05
    scene.draw(app.canvas)
    pygame.quit()


def head_moved_features(xy, head, rng):
    """Eyes compensate for head pose: the iris offset needed for a target depends on yaw/pitch/position."""
    x, y = xy
    yaw, pitch, tx, ty, tz = head
    f = np.zeros(N_FEATURES)
    f[0] = ((x - 0.5) - 0.6 * yaw - 0.02 * tx) / 0.8
    f[1] = ((y - 0.5) - 0.5 * pitch - 0.02 * ty) / 0.5
    f[2] = f[1] * 1.2
    f[3], f[4], f[5], f[13], f[14] = yaw, pitch, tz, tx, ty
    f[:3] += 0.005 * rng.standard_normal(3)
    return f


def test_calibration_with_head_movement_generalises_to_new_head_poses():
    rng = np.random.default_rng(4)

    def head():
        return rng.normal(0, [0.15, 0.1, 4, 3, 4])

    feats, labels = [], []
    for round_targets, moving in ((TARGETS, False), (TARGETS[::2], True)):
        for t in round_targets:
            for _ in range(20):
                h = head() if moving else np.zeros(5)
                feats.append(head_moved_features(t, h, rng))
                labels.append(t)
    cal = GazeCalibration.fit(np.array(feats), np.array(labels))
    errs = []
    for _ in range(100):
        t = (rng.uniform(0.1, 0.9), rng.uniform(0.1, 0.9))
        f = head_moved_features(t, head() * 0.7, rng)
        errs.append(np.abs(cal.predict(f)[0] - t))
    assert np.mean(errs, axis=0).max() < 0.05


def _synthetic_two_cam(n=900, seed=0):
    """Two cameras at known poses, head moving; gaze rays aimed exactly at random screen points."""
    from scipy.spatial.transform import Rotation

    from nightdrive.gaze.features import N_FEATURES

    rng = np.random.default_rng(seed)
    w, h = S.GAZE_SCREEN_CM
    r0 = np.diag([-1.0, 1, -1])
    t0 = np.array([0, h / 2 + 0.6, 0])
    r1 = Rotation.from_euler("y", 150, degrees=True).as_matrix() @ r0
    t1 = np.array([-28.0, -5, 5])
    off = np.array([0, 3, 5.0])
    feats, targets = [], []
    for _ in range(n):
        tgt = rng.uniform(0.05, 0.95, 2)
        goal = np.array([(tgt[0] - 0.5) * w, (0.5 - tgt[1]) * h, 0.0])
        head_rot = Rotation.from_euler("xyz", rng.normal(0, 0.15, 3)).as_matrix()
        eye_screen = np.array(
            [rng.normal(0, 6), rng.normal(0, 4), 50 + rng.normal(0, 5)]
        )
        row = []
        for r, t in ((r0, t0), (r1, t1)):
            head_cam = (
                r.T @ (eye_screen - t) - head_rot @ off
            )  # head position in camera frame
            gdir = r.T @ ((goal - eye_screen) / np.linalg.norm(goal - eye_screen))
            yaw, pitch = np.arctan2(gdir[0], gdir[2]), np.arcsin(gdir[1])
            f = np.zeros(N_FEATURES)
            f[5], f[6], f[7], f[13], f[14] = (
                head_cam[2],
                yaw,
                pitch,
                head_cam[0],
                head_cam[1],
            )
            f[15:24] = head_rot.ravel()
            row.append(f)
        feats.append(np.concatenate(row))
        targets.append(tgt)
    return np.array(feats), np.array(targets)


def test_geometry_recovers_cameras_and_generalises():
    from nightdrive.gaze.features import N_FEATURES
    from nightdrive.gaze.geometry import fit_geometry

    x, y = _synthetic_two_cam()
    # 24 distinct targets only, like a real calibration
    idx = np.arange(len(y))
    uniq = np.unique(y, axis=0)[:24]
    keep = np.array([i for i in idx if (y[i] == uniq).all(axis=1).any()])
    x_cal, y_cal = x[keep], y[keep]
    cal = fit_geometry(x_cal, y_cal, N_FEATURES)
    xt, yt = _synthetic_two_cam(200, seed=5)
    err = np.abs(cal.predict(xt) - yt).mean()
    assert err < 0.05
