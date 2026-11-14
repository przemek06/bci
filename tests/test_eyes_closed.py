import random

import pytest

from nightdrive.attention.eyes_closed import EyesClosedConfig, EyesClosedDetector
from nightdrive.lsl.alpha_reader import relative_alpha

DT = 0.25  # the stream updates at ~4 Hz


def calibrated(cfg=None, base=0.3, noise=0.02, n=40, seed=1):
    rng = random.Random(seed)
    det = EyesClosedDetector(cfg)
    det.calibrate(base + rng.gauss(0, noise) for _ in range(n))
    return det


def feed(det, t0, seconds, value):
    state = None
    t = t0
    while t < t0 + seconds:
        state = det.update(t, value)
        t += DT
    return state, t


def test_relative_alpha():
    assert relative_alpha([1, 4, 1, 4, 2, 8]) == pytest.approx(0.25)
    assert relative_alpha([1, 0, 1, 0]) == 0.0
    with pytest.raises(ValueError):
        relative_alpha([1, 2, 3])


def test_calibrate_needs_samples():
    with pytest.raises(ValueError):
        EyesClosedDetector().calibrate([0.3] * 3)


def test_uncalibrated_never_passes():
    det = EyesClosedDetector()
    state, _ = feed(det, 0, 10, 0.9)
    assert not state.calibrated and not state.closed and not state.passed


def test_open_eyes_noise_never_triggers():
    det = calibrated()
    rng = random.Random(7)
    t = 0.0
    for _ in range(400):
        state = det.update(t, 0.3 + rng.gauss(0, 0.02))
        assert not state.closed
        t += DT


def test_closed_eyes_pass_after_hold():
    det = calibrated()
    state, t = feed(det, 0, 5, 0.3)
    assert not state.closed
    det.reset()
    hold = det.cfg.hold_s  # whatever it is tuned to
    state, t = feed(det, t, hold * 0.6, 0.8)
    assert state.closed and not state.passed
    state, t = feed(det, t, hold * 0.8, 0.8)
    assert state.passed and state.held_s >= hold


def test_short_dip_is_forgiven_long_dip_resets():
    cfg = EyesClosedConfig(smooth_s=0.2)  # one sample per window: no smoothing
    det = calibrated(cfg)
    hold = cfg.hold_s  # whatever it is tuned to
    _, t = feed(det, 0, hold * 0.6, 0.8)
    state, t = feed(det, t, DT, 0.3)  # 0.25 s dip < grace 0.5 s
    assert state.closed
    state, t = feed(det, t, hold * 0.6, 0.8)
    assert (
        state.closed and state.passed
    )  # the dip did not restart the timer (0.6 + 0.6 > 1 x hold)
    state, t = feed(det, t, 1.0, 0.3)  # 1 s dip > grace
    assert not state.closed and state.held_s == 0.0


def test_signal_loss_resets_hold():
    det = calibrated()
    state, t = feed(det, 0, 2.0, 0.8)
    assert state.closed
    state = det.update(t + 5.0)  # no samples for 5 s
    assert not state.signal_ok and not state.closed and state.held_s == 0.0


def test_reset_clears_passed():
    det = calibrated()
    state, t = feed(det, 0, 6.0, 0.8)
    assert state.passed
    det.reset()
    assert not det.update(t, 0.3).passed
