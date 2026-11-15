import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from nightdrive.app import App
from nightdrive.attention.eyes_source import BciEyes, KeyboardEyes
from nightdrive.ghost.encounter import (
    ACTIVE,
    DEAD,
    IDLE,
    PASSED,
    GhostConfig,
    GhostEncounter,
)
from nightdrive.lsl.alpha_reader import AlphaSample
from nightdrive.scenes import DriveScene, GameOverScene

# --- encounter state machine -------------------------------------------------


def test_encounter_dies_at_deadline():
    enc = GhostEncounter(GhostConfig(relax_s=0.0, deadline_s=2.0))
    assert enc.start() and not enc.start()
    for _ in range(19):
        enc.update(0.1, progress=0.2)
    assert enc.state == ACTIVE
    enc.update(0.2, progress=0.2)
    assert enc.state == DEAD and enc.dead


def test_encounter_pass_then_relief_then_idle():
    enc = GhostEncounter(GhostConfig(relax_s=0.0, relief_s=1.0))
    enc.start()
    enc.update(0.1, progress=1.0, passed=True)
    assert enc.state == PASSED and enc.passed_count == 1
    enc.update(1.1)
    assert enc.state == IDLE


def test_encounter_signal_loss_pauses_then_cancels_without_death():
    enc = GhostEncounter(GhostConfig(relax_s=0.0, deadline_s=2.0, signal_grace_s=1.0))
    enc.start()
    for _ in range(9):  # 0.9 s of lost signal: deadline frozen
        enc.update(0.1, signal_ok=False)
    assert enc.state == ACTIVE and enc.time_left == 2.0
    for _ in range(3):
        enc.update(0.1, signal_ok=False)
    assert enc.state == IDLE and enc.passed_count == 0


def test_relax_phase_counts_nothing_and_the_deadline_starts_after_it():
    enc = GhostEncounter(GhostConfig(relax_s=3.0, deadline_s=2.0))
    enc.start()
    assert enc.relaxing
    for _ in range(29):  # 2.9 s: even a "passed" report changes nothing
        enc.update(0.1, progress=1.0, passed=True)
    assert enc.state == ACTIVE and enc.relaxing
    assert enc.progress == 0.0 and enc.time_left == 2.0 and enc.passed_count == 0
    enc.update(0.2)  # the relax time is over
    assert enc.state == ACTIVE and not enc.relaxing and enc.time_left == 2.0
    for _ in range(19):  # now the deadline runs
        enc.update(0.1)
    assert enc.state == ACTIVE
    enc.update(0.2)
    assert enc.dead


def test_the_ghost_can_be_passed_once_the_relax_time_is_over():
    enc = GhostEncounter(GhostConfig(relax_s=1.0))
    enc.start()
    enc.update(1.1)
    enc.update(0.1, progress=1.0, passed=True)
    assert enc.state == PASSED and enc.passed_count == 1


def test_the_prompt_tells_the_player_prompt_seconds_not_the_real_hold():
    from nightdrive.attention.eyes_closed import EyesClosedConfig
    from nightdrive.ghost.visuals import instruction_text

    cfg = GhostConfig()
    text = instruction_text("KEEP THEM SHUT", cfg.prompt_seconds)
    assert text == f"KEEP THEM SHUT FOR {cfg.prompt_seconds:g} SECONDS"
    assert (
        cfg.prompt_seconds != EyesClosedConfig().hold_s
    )  # the text and the check differ on purpose


def test_default_relax_time_is_three_seconds():
    assert GhostConfig().relax_s == 3.0


# --- eye sources --------------------------------------------------------------


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


def test_bci_eyes_calibrates_then_detects_closed():
    clock = {"t": 0.0}
    reader = FakeReader()
    eyes = BciEyes(
        reader=reader, calibration_s=10.0, settle_s=2.0, clock=lambda: clock["t"]
    )
    assert eyes.status_text == "EEG: WAITING FOR STREAM" and not eyes.ready

    def step(value, dt=0.25):
        clock["t"] += dt
        reader.buf.append(AlphaSample(t=clock["t"], lsl_t=clock["t"], value=value))
        return eyes.update()

    for i in range(40):  # 10 s of open eyes: still calibrating (needs settle + 10 s)
        step(0.2 + 0.01 * (i % 3))
    assert not eyes.detector.calibrated and "CALIBRATING" in eyes.status_text
    for i in range(12):
        step(0.2 + 0.01 * (i % 3))
    assert eyes.detector.calibrated and eyes.ready and eyes.status_text == ""

    eyes.begin_challenge()
    state = None
    for _ in range(24):  # 6 s of high alpha
        state = step(0.8)
    assert state.closed and state.passed


def test_bci_eyes_not_ready_when_stream_lost():
    clock = {"t": 0.0}
    reader = FakeReader()
    eyes = BciEyes(
        reader=reader, calibration_s=1.0, settle_s=0.0, clock=lambda: clock["t"]
    )
    for _ in range(20):
        clock["t"] += 0.25
        reader.buf.append(AlphaSample(clock["t"], clock["t"], 0.2))
        eyes.update()
    assert eyes.ready
    reader.connected = False
    assert not eyes.ready and eyes.status_text == "EEG: SIGNAL LOST"


# --- whole scene, headless -----------------------------------------------------


def make_drive(seed=5):
    app = App(seed=seed)
    clock, down = {"t": 0.0}, {"v": False}
    app.eyes = KeyboardEyes(lambda: down["v"], clock=lambda: clock["t"])
    app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert isinstance(app.scene, DriveScene)

    def run(seconds, dt=1 / 60):
        for _ in range(int(seconds / dt)):
            clock["t"] += dt
            app.scene.update(dt)
            app.scene.draw(app.canvas)

    return app, down, run


def test_ghost_kills_if_eyes_stay_open():
    app, _down, run = make_drive()
    assert app.scene.ghost.trigger()
    cfg = app.scene.ghost.cfg
    run(cfg.relax_s + cfg.deadline_s + 1.0)  # past the deadline, eyes never closed
    assert isinstance(app.scene, GameOverScene)
    assert app.scene.event.over_text == "THE GHOST GOT YOU"
    for _ in range(300):  # jump scare + fade + game-over screen render without errors
        app.scene.update(1 / 60)
        app.scene.draw(app.canvas)
    pygame.quit()


def test_ghost_passes_if_eyes_held_closed():
    app, down, run = make_drive()
    drive = app.scene
    assert drive.ghost.trigger()
    down["v"] = True
    cfg = drive.ghost.cfg
    hold = drive.ghost.eyes.detector.cfg.hold_s
    run(cfg.relax_s + hold + 2.0)  # relax time, then the hold
    assert app.scene is drive and drive.ghost.passed_count == 1
    down["v"] = False
    run(3.0)
    assert not drive.ghost.active
    pygame.quit()


def test_eyes_closed_during_the_relax_time_do_not_count():
    app, down, run = make_drive()
    drive = app.scene
    assert drive.ghost.trigger()
    down["v"] = True  # eyes closed from the very first moment
    cfg = drive.ghost.cfg
    hold = drive.ghost.eyes.detector.cfg.hold_s
    run(
        cfg.relax_s + hold * 0.4
    )  # relax time plus a moment: counting only just started
    assert drive.ghost.active and drive.ghost.passed_count == 0
    run(hold + 1.0)  # the hold has to be collected after the relax time
    assert drive.ghost.passed_count == 1
    pygame.quit()


def test_bci_eyes_logs_values_and_calibration():
    clock = {"t": 0.0}
    reader = FakeReader()
    lines = []
    eyes = BciEyes(
        reader=reader,
        calibration_s=3.0,
        settle_s=0.0,
        clock=lambda: clock["t"],
        log=lines.append,
        log_interval_s=1.0,
    )
    for _ in range(40):
        clock["t"] += 0.25
        reader.buf.append(AlphaSample(clock["t"], clock["t"], 0.2))
        eyes.update()
    text = "\n".join(lines)
    assert "calibrating" in text and "CALIBRATED" in text
    assert "raw  0.200" in lines[-1] and "thr" in lines[-1] and "open" in lines[-1]
    assert 8 <= len(lines) <= 14  # roughly one line per second, not one per frame
