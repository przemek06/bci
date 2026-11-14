"""The SSVEP demo: stimulus, simulated source, model (which button?), view and command line."""

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

from nightdrive.attention.ssvep import SsvepConfig
from nightdrive.attention.ssvep_sim import SimulatedEeg, SimulatedSource
from nightdrive.light_switch import stimulus_level, stimulus_lit
from nightdrive.ssvep_demo import (
    DEFAULT_FREQS,
    DemoModel,
    DemoView,
    bar_fraction,
    layout,
    main,
    parse_args,
)

FS = 250


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def make(freqs=DEFAULT_FREQS, strength=6.0, calibration_s=6.0, log=None):
    clock = Clock()
    source = SimulatedSource(strength=strength, clock=clock)
    model = DemoModel(freqs, source, calibration_s=calibration_s, clock=clock, log=log)
    model.start()
    return model, source, clock


def run(model, clock, seconds, source=None, look=None, dt=0.05):
    if source is not None:
        source.look_at(look)
    for _ in range(round(seconds / dt)):
        clock.advance(dt)
        model.update()


# --- the stimulus ---------------------------------------------------------------------------------------


def test_sine_stimulus_swings_between_dark_and_bright_at_the_right_frequency():
    hz = 7.5
    levels = [stimulus_level(i / 6000, hz, "sine") for i in range(6000)]
    assert min(levels) == pytest.approx(0.0, abs=1e-3) and max(levels) == pytest.approx(
        1.0, abs=1e-3
    )
    crossings = sum((a - 0.5) * (b - 0.5) < 0 for a, b in itertools.pairwise(levels))
    assert crossings in (2 * 7, 2 * 8)  # two per cycle over one second (7.5 cycles)
    assert stimulus_level(0.3, 0, "sine") == 1.0  # 0 Hz = steady


def test_square_level_agrees_with_stimulus_lit():
    for t in (0.0, 0.01, 0.034, 0.05, 0.2):
        assert stimulus_level(t, 15.0, "square") == (
            1.0 if stimulus_lit(t, 15.0) else 0.0
        )


def test_only_the_60_over_2k_frequencies_give_an_exact_square_wave_on_a_60_hz_screen():
    def duty(hz):
        return (
            sum(stimulus_lit((k + 0.25) / 60, hz) for k in range(240)) / 240
        )  # just inside each frame

    for hz in (30.0, 15.0, 10.0, 7.5, 6.0):
        assert duty(hz) == 0.5, hz
    assert duty(20.0) != 0.5  # 1.5 frames per half-cycle: lit for 2 of every 3 frames
    assert duty(20.0) == pytest.approx(2 / 3, abs=0.02)


# --- the simulated source -------------------------------------------------------------------------------------


def test_simulated_source_behaves_like_an_eeg_reader():
    clock = Clock()
    src = SimulatedSource(clock=clock)
    src.start()
    assert src.connected and src.sampling_rate == FS
    assert src.window(1.0) is None  # nothing has happened yet
    clock.advance(3.0)
    w = src.window(2.0)
    assert w.shape == (3, 2 * FS)
    clock.advance(30.0)  # a long stall: only the newest data is kept, no giant burst
    assert src.window(2.0).shape == (3, 2 * FS)


def test_simulated_eeg_can_look_at_any_frequency():
    from nightdrive.attention.ssvep import ssvep_score_db

    for f in (6.0, 13.0, 17.0):
        on = np.mean(
            [
                ssvep_score_db(
                    SimulatedEeg(seed=i, ssvep_uv=6.0).chunk(2 * FS, True, f).T, FS, f
                )
                for i in range(8)
            ]
        )
        off = np.mean(
            [
                ssvep_score_db(
                    SimulatedEeg(seed=i, ssvep_uv=6.0).chunk(2 * FS, False).T, FS, f
                )
                for i in range(8)
            ]
        )
        assert on - off > 3.0, f  # the same frequency, looked at vs not looked at


# --- the model: which button? ------------------------------------------------------------------------------------


def test_model_calibrates_then_reports_the_button_being_looked_at():
    lines = []
    model, src, clock = make(log=lines.append)
    assert "WAITING" in model.status_text and model.verdict == model.status_text
    run(model, clock, 5.0)
    assert "CALIBRATING" in model.status_text and not model.calibrated
    run(model, clock, 6.0)
    assert model.calibrated and model.status_text == ""
    assert model.verdict == "LOOKING AT: NOTHING"
    for idx, hz in enumerate(DEFAULT_FREQS):
        run(model, clock, 7.0, src, look=hz)
        assert model.selected == idx, (hz, model.scores)
        assert model.verdict == f"LOOKING AT: BUTTON {idx + 1} ({hz:g} Hz)"
        run(model, clock, 4.0, src, look=None)
        assert model.selected is None
    text = "\n".join(lines)
    assert "calibrating for 6 s" in text and "CALIBRATED. Thresholds:" in text
    assert "looking at BUTTON 3 (13 Hz)" in text and "looking at nothing" in text


def test_no_button_is_ever_reported_that_is_not_being_looked_at():
    model, src, clock = make()
    run(model, clock, 12.0)
    seen = []
    for hz in DEFAULT_FREQS:
        want = DEFAULT_FREQS.index(hz)
        src.look_at(hz)
        for _ in range(round(8 / 0.05)):
            clock.advance(0.05)
            model.update()
            seen.append((want, model.selected))
        src.look_at(None)
        run(model, clock, 4.0)
    assert all(sel in (None, want) for want, sel in seen)
    assert any(sel == want for want, sel in seen)


def test_recalibrating_restarts_and_forgets_the_selection():
    model, src, clock = make()
    run(model, clock, 12.0)
    run(model, clock, 7.0, src, look=13.0)
    assert model.selected == 2
    model.recalibrate()
    assert not model.calibrated and model.selected is None and model.thresholds is None
    assert "WAITING" in model.status_text
    run(model, clock, 12.0, src, look=None)
    assert model.calibrated


def test_lost_stream_is_reported_and_clears_the_selection():
    model, src, clock = make()
    run(model, clock, 12.0)
    run(model, clock, 7.0, src, look=17.0)
    assert model.selected == 3
    src.connected = False  # the stream dies
    run(model, clock, 3.0)
    assert model.status_text == "SIGNAL LOST" and model.selected is None


# --- the view ---------------------------------------------------------------------------------------------------------


def test_layout_fits_any_window_and_button_count():
    for size in ((1280, 720), (640, 480), (1920, 1080)):
        for n in (2, 4, 6):
            lay = layout(size, n)
            assert len(lay.buttons) == n
            for r in lay.buttons:
                assert 0 <= r.left and r.right <= size[0] and r.bottom < lay.verdict_y
            assert all(not a.colliderect(b) for a, b in itertools.pairwise(lay.buttons))
    assert (
        bar_fraction(-100) == 0.0
        and bar_fraction(100) == 1.0
        and 0 < bar_fraction(3) < 1
    )


def pixel(surf, rect):
    return tuple(surf.get_at(rect.center)[:3])


def test_buttons_flicker_at_their_own_frequencies_and_the_selection_is_outlined():
    pygame.init()
    model, src, clock = make()
    wall = Clock(0.0)
    view = DemoView(model, wave="sine", sim=src, clock=wall)
    surf = pygame.Surface((1280, 720))
    lay = layout(surf.get_size(), 4)
    seen = [set() for _ in lay.buttons]
    for k in range(120):  # two seconds of 60 Hz frames
        wall.t = k / 60
        view.draw(surf)
        for i, r in enumerate(lay.buttons):
            seen[i].add(pixel(surf, r))
    assert all(
        len(s) >= 6 for s in seen
    )  # a sine, not on/off: many brightness levels per button
    # 6 Hz vs 17 Hz: different rates of change at the same moment
    wall.t = 0.0
    view.draw(surf)
    a = [pixel(surf, r)[0] for r in lay.buttons]
    wall.t = 1 / 60
    view.draw(surf)
    b = [pixel(surf, r)[0] for r in lay.buttons]
    steps = [abs(x - y) for x, y in zip(a, b, strict=True)]
    assert steps[3] > steps[0]  # 17 Hz changes faster than 6 Hz
    # the outline appears around the selected button only
    run(model, clock, 12.0)
    run(model, clock, 7.0, src, look=7.5)
    assert model.selected == 1
    view.draw(surf)
    outline = [tuple(surf.get_at((r.left - 7, r.centery))[:3]) for r in lay.buttons]
    assert outline[1] == (120, 255, 160) and all(
        o != (120, 255, 160) for i, o in enumerate(outline) if i != 1
    )
    assert "LOOKING AT: BUTTON 2 (7.5 Hz)" in view.drawn_text
    pygame.quit()


def test_view_shows_calibration_then_scores_and_thresholds():
    pygame.init()
    model, src, clock = make()
    view = DemoView(model, sim=src, clock=Clock(0.0))
    surf = pygame.Surface((1280, 720))
    run(model, clock, 5.0)
    view.draw(surf)
    assert any("CALIBRATING" in t for t in view.drawn_text)
    run(model, clock, 8.0)
    view.draw(surf)
    assert "LOOKING AT: NOTHING" in view.drawn_text
    assert sum(t.endswith(" dB") for t in view.drawn_text) == 4  # one score per button
    assert any("simulated EEG" in t for t in view.drawn_text) and any(
        "dropped frames" in t for t in view.drawn_text
    )
    pygame.quit()


def test_mouse_hover_and_number_keys_steer_the_simulated_player(monkeypatch):
    pygame.init()
    model, src, _clock = make()
    view = DemoView(model, sim=src, clock=Clock(0.0))
    size = (1280, 720)
    rects = layout(size, 4).buttons
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: rects[2].center)
    view.update_simulated_gaze(size)
    assert view.hover == 2 and src.looking_at == DEFAULT_FREQS[2]
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (5, 700))  # off the buttons
    view.update_simulated_gaze(size)
    assert view.hover is None and src.looking_at is None
    view.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2)
    )  # sticky choice
    view.update_simulated_gaze(size)
    assert src.looking_at == DEFAULT_FREQS[1]
    view.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_0))
    view.update_simulated_gaze(size)
    assert src.looking_at is None
    pygame.quit()


def test_keys_quit_and_recalibrate():
    pygame.init()
    model, src, clock = make()
    run(model, clock, 12.0)
    view = DemoView(model, sim=src, clock=Clock(0.0))
    assert view.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r)) is None
    assert not model.calibrated  # R recalibrates
    assert (
        view.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        == "quit"
    )
    assert view.handle_event(pygame.event.Event(pygame.QUIT)) == "quit"
    assert (
        view.handle_event(
            pygame.event.Event(
                pygame.MOUSEMOTION, pos=(1, 1), rel=(0, 0), buttons=(0, 0, 0)
            )
        )
        is None
    )
    pygame.quit()


def test_dropped_frames_are_counted():
    pygame.init()
    model, src, _clock = make()
    wall = Clock(0.0)
    view = DemoView(model, sim=src, clock=wall)
    for dt in (1 / 60, 1 / 60, 0.05, 1 / 60):  # the 50 ms frame was a stutter
        wall.t += dt
        view.count_frame()
    assert view.frames == 4 and view.dropped == 1
    pygame.quit()


# --- command line -------------------------------------------------------------------------------------------------------


def test_command_line_defaults_and_validation():
    args = parse_args([])
    assert (
        tuple(args.freqs) == DEFAULT_FREQS
        and args.source == "lsl"
        and args.wave == "sine"
    )
    assert parse_args(["--freqs", "6", "9", "15", "--source", "sim"]).freqs == [
        6.0,
        9.0,
        15.0,
    ]
    with pytest.raises(SystemExit):
        parse_args(["--freqs", "10"])  # one button is not a choice


def test_the_default_buttons_avoid_alpha_and_do_not_share_harmonics():
    assert not any(8.0 <= f <= 12.0 for f in DEFAULT_FREQS)
    cfg = SsvepConfig()
    marks = [f * h for f in DEFAULT_FREQS for h in range(1, cfg.harmonics + 1)]
    assert len(set(marks)) == len(
        marks
    )  # no button's 2nd harmonic is another's fundamental
    assert min(abs(a - b) for i, a in enumerate(marks) for b in marks[i + 1 :]) >= 1.0


def test_demo_runs_headless_in_simulated_mode_and_exits_cleanly(capsys):
    pygame.init()
    pygame.event.post(pygame.event.Event(pygame.QUIT))
    assert main(["--source", "sim", "--size", "640", "480"]) == 0
    assert "[ssvep-demo]" in capsys.readouterr().out


# --- end to end over real LSL ----------------------------------------------------------------------------------------------


def test_demo_picks_the_right_button_from_a_real_lsl_stream():
    from pylsl import StreamInfo, StreamOutlet, resolve_byprop

    from nightdrive.lsl.eeg_reader import EegReader

    name = "DemoE2E_" + uuid.uuid4().hex[:8]
    outlet = StreamOutlet(StreamInfo(name, "EEG", 3, FS, "float32", name + "-src"))
    if not resolve_byprop("name", name, timeout=3):
        pytest.skip("LSL loopback is not available here")
    sim = SimulatedEeg(seed=5, ssvep_uv=8.0)
    looking = {"hz": None}
    stop = threading.Event()

    def publish():
        start, sent = time.perf_counter(), 0
        while not stop.is_set():
            due = int((time.perf_counter() - start) * FS) - sent
            if due >= 5:
                hz = looking["hz"]
                outlet.push_chunk(sim.chunk(5, hz is not None, hz).astype(np.float32))
                sent += 5
            else:
                time.sleep(0.004)

    cfg = SsvepConfig(window_s=1.5, hold_s=0.3, min_calib_scores=8)
    model = DemoModel(
        DEFAULT_FREQS, EegReader(stream_name=name), config=cfg, calibration_s=3.0
    )
    feeder = threading.Thread(target=publish, daemon=True)
    feeder.start()
    model.start()
    try:
        end = time.monotonic() + 9.0
        while time.monotonic() < end and not model.calibrated:
            model.update()
            time.sleep(1 / 60)
        assert model.calibrated, model.status_text
        looking["hz"] = 13.0  # the player looks at button 3
        end = time.monotonic() + 8.0
        while time.monotonic() < end and model.selected != 2:
            model.update()
            time.sleep(1 / 60)
        assert model.selected == 2
        assert model.verdict == "LOOKING AT: BUTTON 3 (13 Hz)"
    finally:
        stop.set()
        model.stop()
        pygame.quit()
