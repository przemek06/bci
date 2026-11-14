"""SSVEP headlight switch: the measure, the decision rules, the LSL reader and the switch."""

import itertools
import os
import threading
import time
import uuid

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pygame
import pytest

import nightdrive.scenes as scenes_mod
from nightdrive import art
from nightdrive import settings as S
from nightdrive.app import App
from nightdrive.attention.ssvep import SsvepConfig, SsvepDetector, ssvep_score_db
from nightdrive.light_switch import SsvepLightSwitch
from nightdrive.scenes import DriveScene
from tools.ssvep_sim_stream import SimulatedEeg

FS = 250
F = S.HEADLIGHT_BUTTON_HZ  # 15 Hz


def eeg(attending, seconds=2.0, seed=0, freq=F, strength=3.0):
    sim = SimulatedEeg(freq=freq, seed=seed, ssvep_uv=strength)
    return sim.chunk(int(seconds * FS), attending).T  # (channels, samples)


# --- the measure ---------------------------------------------------------------------------------


def test_attending_scores_clearly_higher_than_not_attending():
    base = [ssvep_score_db(eeg(False, seed=i), FS, F) for i in range(20)]
    attn = [ssvep_score_db(eeg(True, seed=100 + i), FS, F) for i in range(20)]
    assert np.mean(attn) - np.mean(base) > 4.0
    assert np.percentile(attn, 10) > np.percentile(base, 90)  # separable trial by trial


def test_score_is_a_ratio_so_amplifier_gain_does_not_matter():
    w = eeg(True)
    assert ssvep_score_db(w * 1000, FS, F) == pytest.approx(
        ssvep_score_db(w, FS, F), abs=1e-6
    )
    assert ssvep_score_db(w + 500.0, FS, F) == pytest.approx(
        ssvep_score_db(w, FS, F), abs=1e-6
    )  # DC offset


def test_it_responds_to_the_stimulus_frequency_not_to_others():
    w = eeg(True, freq=15.0)
    assert ssvep_score_db(w, FS, 15.0) > ssvep_score_db(w, FS, 12.5) + 8
    assert ssvep_score_db(w, FS, 15.0) > ssvep_score_db(w, FS, 20.0) + 8


def test_strong_alpha_does_not_fool_a_15_hz_detector():
    t = np.arange(2 * FS) / FS
    rng = np.random.default_rng(3)
    alpha_only = 40 * np.sin(2 * np.pi * 10 * t) + 5 * rng.standard_normal((3, len(t)))
    assert ssvep_score_db(alpha_only, FS, 15.0) < 3.0  # below the minimum threshold


def test_other_frequencies_and_shorter_windows_work():
    for f in (20.0, 15.0):
        attn = np.mean(
            [
                ssvep_score_db(eeg(True, 1.0, seed=i, freq=f, strength=6.0), FS, f)
                for i in range(15)
            ]
        )
        base = np.mean(
            [
                ssvep_score_db(eeg(False, 1.0, seed=50 + i, freq=f), FS, f)
                for i in range(15)
            ]
        )
        assert attn - base > 3.0, f


def test_degenerate_input_does_not_crash():
    assert ssvep_score_db(np.zeros((3, 500)), FS, F) == 0.0
    assert isinstance(
        ssvep_score_db(np.random.default_rng(0).standard_normal(500), FS, F), float
    )  # one channel
    assert isinstance(
        ssvep_score_db(eeg(False), FS, 100.0), float
    )  # beyond what the sampling rate can show


# --- the decision rules --------------------------------------------------------------------------


def calibrated(cfg=None, baseline=-2.0, spread=0.5):
    d = SsvepDetector(cfg)
    rng = np.random.default_rng(1)
    d.calibrate(baseline + spread * rng.standard_normal(60))
    return d


def feed(d, scores, t0=0.0, step=0.25):
    """Feed scores every `step` seconds; returns (list of fire times, final time)."""
    t, fired = t0, []
    for sc in scores:
        t += step
        if d.update(t, sc).triggered:
            fired.append(round(t, 3))
    return fired, t


def test_uncalibrated_detector_never_fires_and_needs_enough_baseline():
    d = SsvepDetector()
    fired, _ = feed(d, [30.0] * 40)
    assert fired == [] and not d.calibrated
    with pytest.raises(ValueError):
        d.calibrate([0.0] * 3)


def test_threshold_follows_the_players_baseline_within_limits():
    cfg = SsvepConfig()
    quiet, noisy = (
        calibrated(baseline=-2.0, spread=0.3),
        calibrated(baseline=-2.0, spread=3.0),
    )
    assert (
        cfg.min_threshold_db
        <= quiet.threshold
        < noisy.threshold
        <= cfg.max_threshold_db
    )
    polluted = calibrated(
        baseline=20.0, spread=1.0
    )  # the player stared at the button during calibration
    assert (
        polluted.threshold == cfg.max_threshold_db
    )  # the switch is not locked out for good
    assert quiet.release < quiet.threshold


def test_fires_once_after_the_hold_time():
    d = calibrated()
    fired, _ = feed(d, [8.0] * 6)
    assert len(fired) == 1
    assert fired[0] == pytest.approx(
        0.25 + d.cfg.hold_s, abs=0.01
    )  # first above at 0.25 s, then held 0.5 s


def test_a_glance_is_not_enough():
    d = calibrated()
    fired, _ = feed(d, [-2.0] * 4 + [8.0] + [-2.0] * 6)
    assert fired == []


def test_staring_does_not_toggle_again_and_looking_away_rearms():
    d = calibrated()
    stare, t = feed(d, [8.0] * 40)  # ten seconds of staring
    assert len(stare) == 1
    away, t = feed(d, [-2.0] * 12, t0=t)  # three seconds looking at the road
    assert away == []
    again, _ = feed(d, [8.0] * 8, t0=t)
    assert len(again) == 1  # the second deliberate look


def test_cooldown_keeps_a_quick_look_away_and_back_from_toggling_twice():
    d = calibrated()
    first, t = feed(d, [8.0] * 4)
    assert len(first) == 1
    quick, t = feed(
        d, [-2.0] * 2 + [8.0] * 3, t0=t
    )  # away 0.5 s, back: still inside the 2 s cooldown
    assert quick == []
    later, _ = feed(d, [-2.0] * 3 + [8.0] * 6, t0=t + 2.0)
    assert len(later) == 1


def test_a_middling_score_does_not_rearm_it():
    d = calibrated()
    feed(d, [8.0] * 4)  # fires
    mid = (d.release + d.threshold) / 2
    fired, t = feed(
        d, [mid] * 20, t0=10.0
    )  # between the release level and the threshold
    assert fired == []
    fired, _ = feed(d, [8.0] * 6, t0=t)
    assert fired == []  # never dropped below the release level: still disarmed


def test_losing_the_signal_resets_the_hold():
    d = calibrated()
    feed(d, [8.0] * 2)  # a look is under way...
    state = d.update(10.0)  # ...then no scores for a long while
    assert state.signal_ok is False and state.attending is False
    fired, _ = feed(d, [8.0] * 2, t0=10.0)
    assert fired == []  # it has to hold again from scratch


# --- the LSL reader -------------------------------------------------------------------------------


def lsl_outlet(name, channels=3, rate=FS):
    from pylsl import StreamInfo, StreamOutlet

    return StreamOutlet(
        StreamInfo(name, "EEG", channels, rate, "float32", name + "-src")
    )


def lsl_available():
    from pylsl import resolve_byprop

    name = "Probe_" + uuid.uuid4().hex[:8]
    outlet = lsl_outlet(name)
    found = bool(resolve_byprop("name", name, timeout=3))
    del outlet
    return found


@pytest.fixture(scope="module")
def lsl():
    if not lsl_available():
        pytest.skip("LSL loopback is not available here")


def wait_for(cond, timeout=8.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_reader_returns_the_newest_samples_in_order_even_after_wrapping(lsl):
    from nightdrive.lsl.eeg_reader import EegReader

    name = "RampEEG_" + uuid.uuid4().hex[:8]
    outlet = lsl_outlet(name)
    reader = EegReader(
        stream_name=name, keep_s=2.0
    )  # holds 2 s: we push 5 s, so it wraps
    reader.start()
    try:
        assert reader.window(1.0) is None and not reader.connected  # nothing yet
        total = 5 * FS
        for start in range(0, total, 50):
            ramp = np.arange(start, start + 50, dtype=np.float32)
            outlet.push_chunk(np.stack([ramp, -ramp, ramp * 2], axis=1))
            time.sleep(0.01)
        assert wait_for(lambda: reader._filled >= 2 * FS and reader.connected)
        assert wait_for(
            lambda: (
                (reader.window(1.0) is not None)
                and reader.window(1.0)[0, -1] == total - 1
            )
        )
        w = reader.window(1.0)
        assert (
            w.shape == (3, FS)
            and reader.channel_count == 3
            and reader.sampling_rate == FS
        )
        assert np.array_equal(
            np.diff(w[0]), np.ones(FS - 1)
        )  # consecutive, oldest first
        assert np.array_equal(w[1], -w[0]) and np.array_equal(
            w[2], 2 * w[0]
        )  # channels kept apart
        assert reader.window(5.0) is None  # more than it keeps
    finally:
        reader.stop()


# --- the switch (with a stand-in reader) --------------------------------------------------------


class FakeReader:
    """Stands in for EegReader: a simulated brain that can be looking at the button or not."""

    sampling_rate = FS

    def __init__(self, seed=0, strength=3.0):
        self.sim = SimulatedEeg(freq=F, seed=seed, ssvep_uv=strength)
        self.data = np.zeros((3, 0))
        self.attending = False
        self.connected = True
        self.started = self.stopped = False
        self._carry = 0.0

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def advance(self, dt):
        self._carry += dt * FS
        n = int(self._carry)
        self._carry -= n
        if n and self.connected:
            self.data = np.concatenate(
                [self.data, self.sim.chunk(n, self.attending).T], axis=1
            )[:, -10 * FS :]

    def window(self, seconds):
        n = round(seconds * FS)
        return self.data[:, -n:].copy() if self.data.shape[1] >= n else None


class Rig:
    """A switch, its fake reader and a clock, run frame by frame like the drive scene does."""

    def __init__(self, cfg=None, log=None, app=None):
        self.t = 1000.0
        self.reader = FakeReader()
        self.app = app or App(seed=1, audio=False)
        self.cfg = cfg or SsvepConfig(calibration_s=4.0)
        self.switch = SsvepLightSwitch(
            self.app, reader=self.reader, config=self.cfg, clock=lambda: self.t, log=log
        )
        self.toggles = 0

    def run(self, seconds, attending=False, dt=1 / 60):
        self.reader.attending = attending
        for _ in range(round(seconds / dt)):
            self.t += dt
            self.reader.advance(dt)
            if self.switch.update(dt):
                self.toggles += 1


def test_switch_calibrates_while_driving_then_toggles_when_looked_at():
    rig = Rig()
    assert rig.switch.stimulus_hz == F and not rig.switch.ready
    assert "WAITING" in rig.switch.status_text
    rig.run(2.5)  # filling the first window
    rig.run(2.0)
    assert "CALIBRATING" in rig.switch.status_text and rig.toggles == 0
    rig.run(4.0)  # the player keeps looking at the road: calibration finishes
    assert (
        rig.switch.detector.calibrated
        and rig.switch.status_text == ""
        and rig.switch.ready
    )
    assert rig.toggles == 0
    rig.run(5.0, attending=True)  # looks at the button
    assert rig.toggles == 1  # one look, one toggle
    rig.run(4.0)  # looks away
    rig.run(5.0, attending=True)
    assert rig.toggles == 2
    rig.app and pygame.quit()


def test_no_toggling_while_calibrating_even_if_the_player_looks_at_the_button():
    rig = Rig()
    rig.run(3.0)
    rig.run(3.0, attending=True)  # staring during calibration
    assert rig.toggles == 0 and not rig.switch.detector.calibrated
    pygame.quit()


def test_the_mouse_still_works_as_a_fallback():
    rig = Rig()
    scale, ox, oy = rig.app._view()
    cx, cy = art.LIGHT_BUTTON.center
    click = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(ox + cx * scale, oy + cy * scale)
    )
    assert rig.switch.handle_event(click) is True
    pygame.quit()


def test_leaving_the_drive_scene_restarts_calibration_and_clears_a_look_in_progress():
    rig = Rig()
    rig.run(5.0)
    assert rig.switch._cal_scores  # collecting a baseline
    rig.t += 5.0  # back to the menu for a while: nothing measured there counts
    rig.run(0.1)
    assert (
        len(rig.switch._cal_scores) <= 2
        and rig.switch._cal_start is None
        or rig.switch._cal_start > 0
    )
    rig.run(10.0)
    assert rig.switch.detector.calibrated  # calibrates afresh from the new session
    rig.run(1.2, attending=True)  # a look begins...
    rig.t += 5.0  # ...we leave and come back
    rig.run(0.2, attending=True)
    assert rig.toggles == 0  # the unfinished look did not carry over
    pygame.quit()


def test_status_reports_a_lost_stream_and_recovers():
    rig = Rig()
    rig.run(12.0)
    assert rig.switch.status_text == ""
    rig.reader.connected = False
    assert rig.switch.status_text == "SSVEP: SIGNAL LOST" and not rig.switch.ready
    rig.run(3.0, attending=True)  # a dead stream never toggles
    assert rig.toggles == 0
    rig.reader.connected = True
    rig.run(2.5)
    assert rig.switch.status_text == ""
    pygame.quit()


def test_it_explains_itself_in_the_log():
    lines = []
    rig = Rig(log=lines.append)
    rig.run(12.0)
    rig.run(4.0, attending=True)
    text = "\n".join(lines)
    assert "[ssvep] calibrating" in text and "CALIBRATED" in text and "DETECTED" in text
    assert "thr" in text and "dB" in text
    pygame.quit()


def test_switch_starts_and_stops_its_reader_and_is_lazy_about_pylsl():
    rig = Rig()
    rig.switch.start()
    rig.switch.stop()
    assert rig.reader.started and rig.reader.stopped
    pygame.quit()


# --- inside the real drive scene -------------------------------------------------------------------


def test_drive_scene_toggles_the_lights_when_the_player_looks_and_shows_calibration(
    monkeypatch,
):
    texts = []
    real = scenes_mod.draw_text
    monkeypatch.setattr(
        scenes_mod,
        "draw_text",
        lambda surf, text, *a, **k: (texts.append(text), real(surf, text, *a, **k))[1],
    )
    app = App(seed=3, audio=False)
    rig = Rig(app=app)
    app.light_switch = rig.switch
    app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    drive = app.scene
    assert isinstance(drive, DriveScene)
    drive.auto_timer = drive.ghost.timer = 9999
    drive.roadside._next_monster = drive.roadside._next_hitch = 9999
    drive.world.headlights.flicker_enabled = False
    lights = drive.world.headlights

    def frames(seconds, attending=False):
        rig.reader.attending = attending
        for _ in range(round(seconds * 60)):
            rig.t += 1 / 60
            rig.reader.advance(1 / 60)
            drive.update(1 / 60)
            drive.draw(app.canvas)

    frames(4.0)
    assert any(
        "CALIBRATING" in t for t in texts
    )  # the HUD tells the player to look at the road
    frames(6.0)
    texts.clear()
    drive.draw(app.canvas)
    assert not any("SSVEP" in t for t in texts)  # ready: no clutter on screen
    assert lights.on
    frames(5.0, attending=True)
    assert not lights.on  # looked at the button: lights off
    pygame.quit()


def test_app_can_start_in_ssvep_mode_and_stops_cleanly():
    app = App(seed=1, audio=False, lights="ssvep", ssvep_log=False)
    assert isinstance(app.light_switch, SsvepLightSwitch)
    assert app.light_switch.stimulus_hz == S.HEADLIGHT_BUTTON_HZ
    pygame.event.post(pygame.event.Event(pygame.QUIT))
    app.run()  # starts the reader thread, then stops it again on the way out
    assert app.light_switch.reader._thread is None


# --- end to end over real LSL, with the simulator ---------------------------------------------------


def test_end_to_end_through_lsl_with_the_simulator(lsl):
    from nightdrive.lsl.eeg_reader import EegReader

    name = "E2E_EEG_" + uuid.uuid4().hex[:8]
    outlet = lsl_outlet(name)
    sim = SimulatedEeg(freq=F, seed=5, ssvep_uv=6.0)
    attending = threading.Event()
    stop = threading.Event()

    def publish():
        start, sent = time.perf_counter(), 0
        while not stop.is_set():
            due = int((time.perf_counter() - start) * FS) - sent
            if due >= 5:
                outlet.push_chunk(sim.chunk(5, attending.is_set()).astype(np.float32))
                sent += 5
            else:
                time.sleep(0.004)

    cfg = SsvepConfig(window_s=1.5, calibration_s=3.0, hold_s=0.3, min_calib_scores=8)
    app = App(seed=1, audio=False)
    switch = SsvepLightSwitch(app, reader=EegReader(stream_name=name), config=cfg)
    feeder = threading.Thread(target=publish, daemon=True)
    feeder.start()
    switch.start()
    toggles = 0
    try:
        deadline = time.monotonic() + 9.0
        while time.monotonic() < deadline and not switch.detector.calibrated:
            toggles += bool(switch.update(1 / 60))
            time.sleep(1 / 60)
        assert switch.detector.calibrated, switch.status_text
        assert toggles == 0
        attending.set()  # the player looks at the button
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline and toggles == 0:
            toggles += bool(switch.update(1 / 60))
            time.sleep(1 / 60)
        assert toggles == 1
    finally:
        stop.set()
        switch.stop()
        pygame.quit()


def test_pairwise_is_used():
    assert list(itertools.pairwise([1, 2, 3])) == [(1, 2), (2, 3)]
