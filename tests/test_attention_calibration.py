"""The attention calibration screen between START and the first game (attention_calibration.py)."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from nightdrive import attention_calibration as ac
from nightdrive.app import App
from nightdrive.attention.base import AttentionState
from nightdrive.attention.bci_source import BciAttention
from nightdrive.lsl.reader import StreamSample
from nightdrive.scenes import DriveScene, MenuScene, start_drive


class CalSource:
    """Stands in for the headset source: needs a baseline, reports its progress."""

    mode = "bci"
    needs_calibration = True
    log = None
    status_text = ""
    debug_text = "cal source"

    def __init__(self):
        self.calibrated = False
        self.calibration_progress = 0.0
        self.waiting_for_stream = True
        self.updates = 0

    def start(self):
        pass

    def stop(self):
        pass

    def update(self, ignore=False):
        self.updates += 1
        return AttentionState(
            1.0, 1.0 if self.calibrated else 0.0, 0.0, self.calibrated
        )


def make_app(source=None):
    app = App(seed=3, audio=False)
    if source is not None:
        app.attention = source
    return app


def press(app, key):
    app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def run(app, seconds, dt=1 / 60):
    for _ in range(round(seconds / dt)):
        app.scene.update(dt)
        app.scene.draw(app.canvas)


def test_without_a_headset_start_goes_straight_to_the_game():
    app = make_app()  # no attention source
    press(app, pygame.K_RETURN)
    assert isinstance(app.scene, DriveScene)
    pygame.quit()


def test_with_the_headset_start_opens_the_calibration_first():
    source = CalSource()
    app = make_app(source)
    press(app, pygame.K_RETURN)
    assert isinstance(app.scene, ac.AttentionCalibrationScene)
    run(app, 0.5)
    assert source.updates > 0  # the screen runs the baseline recording
    assert isinstance(
        app.scene, ac.AttentionCalibrationScene
    )  # and does not start the game by itself
    pygame.quit()


def test_the_game_starts_when_calibrated_and_attention_already_works():
    source = CalSource()
    app = make_app(source)
    press(app, pygame.K_RETURN)
    source.waiting_for_stream = False
    source.calibration_progress = 0.5
    run(app, 1.0)
    assert isinstance(app.scene, ac.AttentionCalibrationScene)  # still recording
    source.calibrated = True
    run(app, ac.READY_S + 0.5)
    drive = app.scene
    assert isinstance(drive, DriveScene)
    drive.update(1 / 60)
    assert drive.focus.ready  # no waiting for a baseline during play
    pygame.quit()


def test_enter_plays_anyway_and_escape_goes_back_to_the_menu():
    app = make_app(CalSource())
    press(app, pygame.K_RETURN)
    press(app, pygame.K_ESCAPE)
    assert isinstance(app.scene, MenuScene)
    press(app, pygame.K_RETURN)
    assert isinstance(app.scene, ac.AttentionCalibrationScene)
    press(app, pygame.K_RETURN)  # play anyway
    assert isinstance(app.scene, DriveScene)
    pygame.quit()


def test_once_calibrated_later_starts_skip_the_screen():
    source = CalSource()
    app = make_app(source)
    source.calibrated = True
    press(app, pygame.K_RETURN)
    assert isinstance(app.scene, DriveScene)
    assert isinstance(
        start_drive(app, app.scene.world), DriveScene
    )  # also what a retry uses
    source.calibrated = False  # e.g. skipped the first time: ask again
    assert isinstance(start_drive(app, app.scene.world), ac.AttentionCalibrationScene)
    pygame.quit()


def test_the_screen_says_what_is_going_on(monkeypatch):
    drawn = []
    real = ac.draw_text
    monkeypatch.setattr(
        ac,
        "draw_text",
        lambda surf, text, *a, **k: (drawn.append(text), real(surf, text, *a, **k))[1],
    )
    source = CalSource()
    app = make_app(source)
    press(app, pygame.K_RETURN)
    scene = app.scene

    run(app, 0.5)
    assert any(t.startswith("WAITING FOR THE HEADSET") for t in drawn)
    assert not any("NO HEADSET SIGNAL" in t for t in drawn)

    drawn.clear()
    scene.t = ac.NO_SIGNAL_S + 1.0  # the stream never appears
    scene.draw(app.canvas)
    assert any("NO HEADSET SIGNAL" in t for t in drawn)

    drawn.clear()
    source.waiting_for_stream = False
    source.calibration_progress = 0.4
    scene.draw(app.canvas)
    assert "CALIBRATING YOUR ATTENTION" in drawn and "40%" in drawn

    drawn.clear()
    source.calibrated = True
    scene.draw(app.canvas)
    assert "READY!" in drawn and "100%" in drawn
    pygame.quit()


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


def test_the_real_headset_source_is_calibrated_by_the_screen_before_the_game_starts():
    clock = {"t": 0.0}
    reader = FakeReader()
    app = make_app(BciAttention(reader=reader, clock=lambda: clock["t"]))
    press(app, pygame.K_RETURN)
    assert isinstance(app.scene, ac.AttentionCalibrationScene)
    assert not app.attention.calibrated

    steps = 0
    while isinstance(app.scene, ac.AttentionCalibrationScene) and steps < 400:
        clock["t"] += 0.25  # the band stream updates about 4 times a second
        reader.buf.append(
            StreamSample(clock["t"], clock["t"], (50.0, 1.0, 0.0, 0.0, 1.0, 0.0))
        )
        app.scene.update(0.25)
        app.scene.draw(app.canvas)
        steps += 1
    drive = app.scene
    assert isinstance(drive, DriveScene)  # the game started...
    assert app.attention.calibrated  # ...with the baseline already recorded
    assert steps * 0.25 < 40  # about 25 s of sitting still, not a whole minute
    clock["t"] += 0.25
    reader.buf.append(
        StreamSample(clock["t"], clock["t"], (50.0, 1.0, 0.0, 0.0, 1.0, 0.0))
    )
    drive.update(1 / 60)
    assert drive.focus.ready
    pygame.quit()
