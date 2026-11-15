import os
import random
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from nightdrive import settings as S
from nightdrive.app import App
from nightdrive.attention.base import AttentionState
from nightdrive.attention.bci_source import BciAttention
from nightdrive.attention.focus_index import FocusEstimator, engagement_index
from nightdrive.attention.sim_sources import (
    KeyboardAttention,
    NullAttention,
    RandomAttention,
)
from nightdrive.events import AFTERMATH, DEAD, QTE, EventDirector
from nightdrive.focus_pass import FocusMeter, FocusPass, FocusPassConfig
from nightdrive.lsl.band_reader import band_sums
from nightdrive.lsl.reader import StreamSample
from nightdrive.qte import SUCCESS, Qte
from nightdrive.scenes import DriveScene, GameOverScene

DT = 0.25  # the band stream updates at ~4 Hz


def bands(ratio: float):
    """(theta, alpha, beta_low, beta_mid, beta_high, gamma) whose attention value is `ratio`.
    Theta is deliberately large: it must not matter."""
    return (50.0, 1.0, 0.0, 0.0, ratio, 0.0)


def calibrated_estimator(seed=1, noise=0.1, seconds=30):
    rng = random.Random(seed)
    est = FocusEstimator()
    t = 0.0
    while t < seconds:
        state = est.update(t, bands(1.0 + rng.gauss(0, noise)))
        t += DT
    assert state.calibrated
    return est, t


# --- index + reader parsing -----------------------------------------------------


def test_attention_value_is_all_beta_plus_gamma_over_alpha():
    assert engagement_index((50, 1, 0, 0, 2, 0)) == pytest.approx(2.0)  # (2+0)/1
    assert engagement_index((50, 1, 0, 0, 2, 4)) == pytest.approx(6.0)  # (2+4)/1
    assert engagement_index((50, 2, 3, 5, 2, 0)) == pytest.approx(
        5.0
    )  # (3+5+2)/2: all beta
    assert engagement_index((1, 2, 3, 5, 2, 4)) == pytest.approx(7.0)  # (3+5+2+4)/2
    assert engagement_index((1, 1, 0, 0, 2, 0)) == engagement_index(
        (900, 1, 0, 0, 2, 0)
    )  # no theta
    assert engagement_index((1, 0, 1, 1, 2, 0)) is None  # no alpha


def test_band_sums_adds_channels_in_six_bands():
    one = [1, 2, 3, 4, 5, 6]
    assert band_sums(one + [10, 20, 30, 40, 50, 60]) == (11, 22, 33, 44, 55, 66)
    with pytest.raises(ValueError):
        band_sums([1, 2, 3, 4])


# --- estimator --------------------------------------------------------------------


def test_uncalibrated_is_neutral():
    est = FocusEstimator()
    state = est.update(0.0, bands(3.0))
    assert not state.calibrated and state.level == 1.0


def test_calibration_takes_about_half_a_minute():
    est = FocusEstimator()
    t, done_at = 0.0, None
    while t < 60 and done_at is None:
        if est.update(t, bands(1.0)).calibrated:
            done_at = t
        t += DT
    assert done_at is not None and done_at <= 30.0


def test_level_is_relative_to_the_baseline():
    est, t = calibrated_estimator()
    assert est.baseline == pytest.approx(1.0, abs=0.05)
    state = None
    for _ in range(40):
        state = est.update(t, bands(1.0))
        t += DT
    assert state.level == pytest.approx(1.0, abs=0.1)
    for _ in range(40):  # 60% more beta + gamma relative to alpha
        state = est.update(t, bands(1.6))
        t += DT
    assert state.level == pytest.approx(1.6, abs=0.1)
    for _ in range(40):
        state = est.update(t, bands(0.7))
        t += DT
    assert state.level == pytest.approx(0.7, abs=0.05)


def test_the_level_reacts_within_a_couple_of_seconds():
    est, t = calibrated_estimator()
    state = None
    for _ in range(8):  # 2 s of strong focus
        state = est.update(t, bands(2.0))
        t += DT
    assert state.level > 1.8


def test_median_smoothing_ignores_a_short_artifact_burst():
    est, t = calibrated_estimator()
    state = None
    for i in range(80):  # 0.5 s artifact burst every 5 s
        state = est.update(t, bands(5.0 if i % 20 in (5, 6) else 1.0))
        t += DT
    assert state.level == pytest.approx(1.0, abs=0.1)


def test_baseline_follows_recent_normal_play():
    est, t = calibrated_estimator()
    rng = random.Random(5)
    state = None
    for _ in range(1300):  # 5+ minutes where "normal" is now a different level
        state = est.update(t, bands(1.6 + rng.gauss(0, 0.1)))
        t += DT
    assert est.baseline == pytest.approx(1.6, abs=0.1)
    assert state.level == pytest.approx(1.0, abs=0.15)


def test_a_short_drop_barely_moves_the_baseline():
    est, t = calibrated_estimator()
    before = est.baseline
    for _ in range(48):
        est.update(t, bands(0.4))
        t += DT
    assert abs(est.baseline - before) < 0.1


def test_stale_signal_drops_quality():
    est, t = calibrated_estimator()
    assert est.update(t, bands(1.0)).quality == 1.0
    assert est.update(t + 30).quality == 0.0


def test_unusable_samples_do_not_start_calibration():
    est = FocusEstimator()
    est.update(0.0, (0.0, 0.0, 1.0, 1.0, 1.0, 1.0))
    assert est.calibration_progress(100.0) == 0.0


# --- focus meter (pure) ---------------------------------------------------------------


def att(level, quality=1.0, calibrated=True):
    return AttentionState(level, quality, 0.0, calibrated)


def run_meter(meter, seconds, level, dt=0.05, **kw):
    for _ in range(round(seconds / dt)):
        meter.update(dt, att(level, **kw))
    return meter


# Everything is expressed in the configured values, so these tests survive tuning them.
CFG = FocusPassConfig()
PASS = CFG.pass_level
HOLD = CFG.hold_s
DELAY = CFG.delay_s
NODELAY = FocusPassConfig(delay_s=0.0)  # for tests that are not about the settle time
HIGH = PASS + 0.5  # clearly focusing
SLIP = PASS - 0.3  # clearly below the line


def test_meter_passes_after_holding_a_high_level():
    m = FocusMeter(NODELAY)
    run_meter(m, HOLD * 0.9, HIGH)
    assert not m.passed and 0.85 < m.progress < 1.0
    run_meter(m, HOLD * 0.3, HIGH)
    assert m.passed


def test_meter_does_not_pass_below_the_threshold_or_without_a_good_signal():
    m = run_meter(
        FocusMeter(NODELAY), HOLD * 3, PASS - 0.05
    )  # just under the line is not enough
    assert not m.passed and m.progress == 0.0
    assert not run_meter(FocusMeter(NODELAY), HOLD * 3, HIGH, calibrated=False).passed
    assert not run_meter(FocusMeter(NODELAY), HOLD * 3, HIGH, quality=0.1).passed


def test_a_dip_holds_the_progress_still_and_never_resets_it():
    m = FocusMeter(NODELAY)
    run_meter(m, HOLD * 0.5, HIGH)
    held = m.held
    run_meter(m, HOLD * 2, SLIP)  # a long bad stretch
    after = m.held
    # the average lags a little (up to avg_s) before it falls below the line, then it stands still
    assert held <= after <= held + CFG.avg_s + 0.05
    run_meter(m, 3.0, SLIP)
    assert m.held == pytest.approx(after)  # no draining, no reset
    assert not m.passed
    run_meter(
        m, HOLD + CFG.avg_s, HIGH
    )  # focus returns: carries on from where it stopped
    assert m.passed


def test_one_bad_value_does_not_even_stall_the_progress():
    m = FocusMeter(NODELAY)
    run_meter(m, HOLD * 0.4, HIGH)
    m.update(0.05, att(SLIP))  # a single bad frame
    held = m.held
    run_meter(m, 0.5, HIGH)
    assert m.held == pytest.approx(held + 0.5, abs=0.06)  # the average barely moved


def test_the_meter_compares_the_average_level():
    m = FocusMeter(NODELAY)
    run_meter(m, CFG.avg_s, HIGH)
    assert m.avg_level == pytest.approx(HIGH)
    run_meter(m, CFG.avg_s, SLIP)  # the whole window is now the low level
    assert m.avg_level == pytest.approx(SLIP, abs=0.05)
    m.reset()
    assert m.avg_level is None and m.held == 0.0


def test_draining_is_still_available_as_an_option():
    m = FocusMeter(FocusPassConfig(drain=2.0, delay_s=0.0))
    run_meter(m, HOLD * 0.5, HIGH)
    held = m.held
    run_meter(m, 2.0, SLIP)
    assert m.held < held  # slips lose progress when drain > 0


def test_nothing_counts_during_the_settle_time_and_counting_starts_from_zero():
    m = FocusMeter()  # the default config, with the settle time
    assert not m.counting
    run_meter(m, DELAY * 0.9, HIGH * 3)  # clearly high, but still settling
    assert not m.counting and not m.passed
    assert m.progress == 0.0 and m.avg_level is None  # not even recorded
    run_meter(m, 0.2, HIGH)  # the settle time is over
    assert m.counting and m.held <= 0.1  # starts from zero, nothing carried over
    run_meter(m, HOLD + CFG.avg_s, HIGH)
    assert m.passed


def test_the_bar_only_shows_after_the_settle_time():
    pygame.font.init()
    font = pygame.font.Font(None, 14)
    f = FocusPass(SimpleNamespace(attention=FakeSource(HIGH), font_small=font))
    f.update(0.05, qte_active=False)  # the source is ready
    surf = pygame.Surface((S.W, S.H))
    spot = (S.W // 2, 88)  # inside the progress bar

    def drawn_bar_pixel():
        surf.fill((0, 0, 0))
        f.draw(surf)
        return tuple(surf.get_at(spot))[:3]

    for _ in range(round(DELAY * 0.5 / 0.05)):  # half the settle time
        f.update(0.05, qte_active=True)
    assert not f.meter.counting
    assert drawn_bar_pixel() == (0, 0, 0)  # no bar yet (only the "OR FOCUS" hint)
    for _ in range(round(DELAY / 0.05)):
        f.update(0.05, qte_active=True)
    assert f.meter.counting
    assert drawn_bar_pixel() != (0, 0, 0)  # the bar is there now


# --- focus pass glue --------------------------------------------------------------------


class FakeSource:
    mode = "fake"
    status_text = ""
    debug_text = "fake source"
    needs_calibration = False

    def __init__(self, level, calibrated=True, quality=1.0):
        self.level, self.calibrated, self.quality = level, calibrated, quality
        self.log = None
        self.ignored = []

    def start(self):
        pass

    def stop(self):
        pass

    def update(self, ignore=False):
        self.ignored.append(ignore)
        return AttentionState(self.level, self.quality, 0.0, self.calibrated)


def make_focus(source):
    return FocusPass(SimpleNamespace(attention=source, font_small=None))


def test_event_window_is_only_longer_when_focus_can_pass():
    cfg = FocusPassConfig()
    f = make_focus(FakeSource(1.0, calibrated=False))
    assert f.qte_window(1.5) == 1.5  # before any update
    f.update(0.05, qte_active=False)
    assert f.qte_window(1.5) == 1.5  # not calibrated
    f = make_focus(FakeSource(1.0))
    f.update(0.05, qte_active=False)
    assert (
        f.qte_window(1.5) == cfg.delay_s + cfg.qte_window_s
    )  # settle time + the time to focus
    f = make_focus(FakeSource(1.0, quality=0.0))
    f.update(0.05, qte_active=False)
    assert f.qte_window(1.5) == 1.5  # no fresh signal


def test_focus_only_counts_during_a_quick_time_event_and_logs():
    source = FakeSource(2.0)
    lines = []
    source.log = lines.append
    f = make_focus(source)
    for _ in range(40):  # 2 s of high focus with no event running: nothing
        assert not f.update(0.05, qte_active=False)
    assert f.meter.held == 0.0
    passed = False
    for _ in range(
        round((DELAY + HOLD + 1.0) / 0.05)
    ):  # settle time, the hold, plus a margin
        passed = f.update(0.05, qte_active=True) or passed
    assert passed
    text = "\n".join(lines)
    assert (
        "QTE started: press the key OR focus" in text and "QTE PASSED BY FOCUS" in text
    )
    assert "fake source" in text


def test_a_ghost_on_screen_pauses_focus_and_tells_the_source_to_ignore():
    source = FakeSource(2.0)
    f = make_focus(source)
    for _ in range(40):
        assert not f.update(0.05, qte_active=True, paused=True)
    assert source.ignored[-1] is True and f.meter.held == 0.0


# --- quick-time event + director ----------------------------------------------------------


def test_qte_can_be_passed_by_focus():
    q = Qte("K", 5.0)
    q.update(1.2)
    q.succeed_by_focus()
    assert q.result == SUCCESS and q.via == "focus" and q.reaction == pytest.approx(1.2)
    q2 = Qte("K", 5.0)
    q2.press("k")
    assert q2.via == "key"


def make_world():
    return SimpleNamespace(
        position=0.0,
        speed=S.CRUISE_SPEED,
        cruise=S.CRUISE_SPEED,
        speed_rate=0.8,
        actors=[],
        headlights=SimpleNamespace(on=True, flickering=False),
        track=SimpleNamespace(
            length=600_000, mark=lambda *a: None, clear_marks=lambda: None
        ),
    )


def test_director_uses_the_window_and_records_how_the_event_was_passed():
    d = EventDirector(make_world(), random.Random(1))
    assert d.qte_window == S.QTE_WINDOW  # unchanged by default
    d.qte_window = 5.0
    d.trigger()
    assert d.state == QTE and d.qte.window == 5.0
    d.update(1.0)
    d.pass_by_focus()
    d.update(0.016)
    assert d.state == AFTERMATH
    assert d.history[-1]["result"] == SUCCESS and d.history[-1]["input"] == "focus"


def test_director_records_key_presses_as_keys():
    d = EventDirector(make_world(), random.Random(1))
    d.trigger()
    d.press(d.qte.letter)
    d.update(0.016)
    assert d.history[-1]["input"] == "key"


def test_dark_headlights_shorten_the_window_and_the_focus_window_in_proportion():
    dark = make_world()
    dark.headlights = SimpleNamespace(on=False, flickering=False)
    d = EventDirector(dark, random.Random(1))
    d.trigger()
    assert d.qte.window == pytest.approx(S.QTE_WINDOW_DARK)  # main's rule, unchanged
    d2 = EventDirector(dark, random.Random(1))
    d2.qte_window = 5.0  # focus can pass the event
    d2.trigger()
    assert d2.qte.window == pytest.approx(5.0 * S.QTE_WINDOW_DARK / S.QTE_WINDOW)
    lit = EventDirector(make_world(), random.Random(1))
    lit.qte_window = 5.0
    lit.trigger()
    assert lit.qte.window == pytest.approx(5.0)  # lights on: the focus window as set


# --- sources ---------------------------------------------------------------------------


class FakeReader:
    def __init__(self):
        self.connected = True
        self.buf = []

    def start(self):
        pass

    def stop(self):
        pass

    def drain(self):
        out, self.buf = self.buf, []
        return out


def test_bci_attention_calibrates_tracks_ignores_and_logs_beta_and_gamma():
    clock = {"t": 0.0}
    reader = FakeReader()
    source = BciAttention(reader=reader, clock=lambda: clock["t"])
    rng = random.Random(2)

    def step(ratio, gamma=0.0):
        clock["t"] += DT
        b = bands(ratio)
        reader.buf.append(StreamSample(clock["t"], clock["t"], b[:5] + (gamma,)))
        return source.update()

    assert source.status_text == "ATTENTION: WAITING FOR STREAM"
    for _ in range(120):  # 30 s of baseline
        s = step(1.0 + rng.gauss(0, 0.1))
    assert s.calibrated and source.status_text == ""
    for _ in range(40):
        s = step(1.8)
    assert s.level == pytest.approx(1.8, abs=0.1)
    step(2.0, gamma=1.5)
    text = source.debug_text
    assert "level" in text and "beta raw 2.0" in text and "gamma raw 1.5" in text

    clock["t"] += DT  # while ignoring, incoming data is discarded
    reader.buf.append(StreamSample(clock["t"], clock["t"], bands(9.0)))
    source.update(ignore=True)
    assert reader.buf == [] and source.estimator.index == pytest.approx(3.5)


def test_sim_sources_stay_in_range_and_respond():
    clock = {"t": 0.0}
    rnd = RandomAttention(random.Random(1), clock=lambda: clock["t"])
    for _ in range(2000):
        clock["t"] += 0.1
        assert 0.0 <= rnd.update().level <= 2.0

    direction = {"v": 0}
    kb = KeyboardAttention(
        lambda: direction["v"], clock=lambda: clock["t"], rate_per_s=0.5
    )
    assert kb.update().level == 1.0
    direction["v"] = 1
    for _ in range(10):
        clock["t"] += 0.1
        kb.update()
    assert kb.level == pytest.approx(1.5)
    assert not NullAttention().update().calibrated


# --- whole scene ----------------------------------------------------------------------


def start_drive(direction):
    """A drive scene whose simulated attention rises (+1), falls (-1) or stays (0)."""
    app = App(seed=4)
    clock = {"t": 0.0}
    app.attention = KeyboardAttention(
        lambda: direction, clock=lambda: clock["t"], rate_per_s=1.0
    )
    app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    drive = app.scene
    assert isinstance(drive, DriveScene)
    drive.auto_timer = 1e9  # no random events: the test starts them
    drive.ghost.timer = 1e9

    def run(seconds, dt=1 / 60, until=None):
        for _ in range(int(seconds / dt)):
            clock["t"] += dt
            app.scene.update(dt)
            app.scene.draw(app.canvas)
            if until and until():
                break

    return app, drive, run


def test_high_attention_passes_a_quick_time_event_without_a_key():
    app, drive, run = start_drive(+1)  # attention keeps rising
    run(0.5)  # focus source is now ready
    drive.on_distracted()
    assert (
        drive.director.state == QTE
        and drive.director.qte.window
        == drive.focus.cfg.delay_s + drive.focus.cfg.qte_window_s
    )
    run(
        drive.focus.cfg.delay_s + drive.focus.cfg.qte_window_s,
        until=lambda: drive.director.state != QTE,
    )
    assert drive.director.state == AFTERMATH  # passed, no key pressed
    assert drive.director.history[-1]["input"] == "focus"
    assert app.scene is drive  # and the run goes on
    pygame.quit()


def test_without_high_attention_the_event_still_fails_as_before():
    app, drive, run = start_drive(-1)  # attention falls and stays low
    run(0.5)
    drive.on_distracted()
    run(12.0, until=lambda: isinstance(app.scene, GameOverScene))
    assert isinstance(app.scene, GameOverScene)
    assert (
        drive.director.state == DEAD or drive.director.history[-1]["result"] != SUCCESS
    )
    pygame.quit()


def test_attention_off_leaves_the_quick_time_event_unchanged():
    app = App(seed=4)  # --attention off (default)
    app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    drive = app.scene
    drive.auto_timer = 1e9
    drive.ghost.timer = 1e9
    for _ in range(30):
        drive.update(1 / 60)
    drive.on_distracted()
    assert drive.director.qte.window == S.QTE_WINDOW
    assert not drive.focus.ready
    pygame.quit()


# --- the letter keys are the no-BCI mode ---------------------------------------------------


def key_of(letter):
    return pygame.event.Event(
        pygame.KEYDOWN, key=getattr(pygame, f"K_{letter.lower()}")
    )


def start_bci_drive(source=None, direction=1):
    """A drive in the BCI mode: an attention source is on, so the letter keys are off."""
    app = App(seed=4, audio=False, attention="keyboard")
    assert app.qte_keys is False
    clock = {"t": 0.0}
    app.attention = source or KeyboardAttention(
        lambda: direction, clock=lambda: clock["t"], rate_per_s=1.0
    )
    app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    drive = app.scene
    drive.auto_timer = 1e9
    drive.ghost.timer = 1e9

    def run(seconds, dt=1 / 60):
        for _ in range(round(seconds / dt)):
            clock["t"] += dt
            drive.update(dt)
            drive.draw(app.canvas)

    return app, drive, run


def test_without_bci_the_letter_keys_are_the_mode():
    app = App(seed=4, audio=False)  # no attention source
    assert app.qte_keys is True
    app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    drive = app.scene
    drive.auto_timer = 1e9
    drive.ghost.timer = 1e9
    drive.update(1 / 60)
    drive.on_distracted()  # an event starts without any focus measurement
    assert drive.director.state == QTE and drive.keys_active
    drive.handle_event(key_of(drive.director.qte.letter))
    assert drive.director.qte.result == SUCCESS and drive.director.qte.via == "key"
    pygame.quit()


def test_in_the_bci_mode_the_letter_keys_do_nothing():
    _app, drive, run = start_bci_drive(direction=-1)  # focus never reaches the line
    run(0.5)
    drive.on_distracted()
    assert drive.director.state == QTE and not drive.keys_active
    letter = drive.director.qte.letter
    wrong = "A" if letter != "A" else "B"
    drive.handle_event(key_of(wrong))  # a wrong key does not fail it...
    drive.handle_event(key_of(letter))  # ...and the right key does not pass it
    assert drive.director.state == QTE and drive.director.qte.result is None
    pygame.quit()


def test_in_the_bci_mode_focus_passes_and_no_letter_is_drawn(monkeypatch):
    from nightdrive import scenes

    drawn = []
    real = scenes.draw_text
    monkeypatch.setattr(
        scenes,
        "draw_text",
        lambda surf, text, *a, **k: (drawn.append(text), real(surf, text, *a, **k))[1],
    )
    _app, drive, run = start_bci_drive(direction=1)
    run(0.5)
    drive.on_distracted()
    letter = drive.director.qte.letter
    drawn.clear()
    run(0.1)
    assert (
        "FOCUS!" in drawn and "WATCH OUT ON THE ROAD!" in drawn
    )  # a text, not a letter box
    assert letter not in drawn
    run(
        drive.focus.cfg.delay_s + drive.focus.cfg.qte_window_s,
    )
    assert drive.director.history[-1]["input"] == "focus"
    pygame.quit()


def test_in_the_bci_mode_an_event_waits_until_focus_is_ready():
    _app, drive, run = start_bci_drive()
    drive.on_distracted()  # nothing has been measured yet
    assert not drive.director.active
    run(0.3)
    drive.on_distracted()
    assert drive.director.active
    pygame.quit()


def test_if_the_signal_is_lost_mid_event_the_keys_come_back_as_a_fallback():
    source = FakeSource(0.2)  # a low level: focus will not pass it
    _app, drive, run = start_bci_drive(source=source)
    run(0.5)
    drive.on_distracted()
    assert drive.director.state == QTE and not drive.keys_active
    source.quality = 0.0  # the headset drops out
    run(0.1)
    assert drive.keys_active  # never an unwinnable event
    drive.handle_event(key_of(drive.director.qte.letter))
    assert drive.director.qte.result == SUCCESS and drive.director.qte.via == "key"
    pygame.quit()


# --- the focus-only prompt: a text, and the focus meter is the only bar ---------------------


def _is_black(surface):
    return not any(pygame.image.tobytes(surface, "RGB"))


def test_in_the_bci_mode_the_prompt_is_a_text_with_no_box_and_no_countdown_bar():
    _app, drive, run = start_bci_drive(direction=-1)
    run(0.5)
    drive.on_distracted()
    qte = drive.director.qte
    blank = pygame.Surface((S.W, S.H))
    drive._draw_prompt(blank, qte, show_letter=False)
    # the countdown bar sat at about y=64 under the 44 px box: nothing may be drawn there
    strip = blank.subsurface(pygame.Rect(S.W // 2 - 40, 58, 80, 20))
    assert _is_black(strip)
    boxed = pygame.Surface((S.W, S.H))
    drive._draw_prompt(
        boxed, qte, show_letter=True
    )  # the keys mode still has box + bar
    assert not _is_black(boxed.subsurface(pygame.Rect(S.W // 2 - 40, 58, 80, 20)))
    pygame.quit()


def test_in_the_bci_mode_the_focus_meter_shows_only_after_the_settle_time():
    pygame.font.init()
    font = pygame.font.Font(None, 14)
    f = FocusPass(SimpleNamespace(attention=FakeSource(HIGH), font_small=font))
    f.update(0.05, qte_active=False)
    surf = pygame.Surface((S.W, S.H))
    for _ in range(round(DELAY * 0.5 / 0.05)):
        f.update(0.05, qte_active=True)
    surf.fill((0, 0, 0))
    f.draw(surf, keys_enabled=False)
    assert _is_black(surf)  # no hint, no bar while settling
    for _ in range(round(DELAY / 0.05)):
        f.update(0.05, qte_active=True)
    surf.fill((0, 0, 0))
    f.draw(surf, keys_enabled=False)
    assert not _is_black(
        surf.subsurface(pygame.Rect(S.W // 2 - 40, 62, 80, 22))
    )  # label + bar
    pygame.quit()
