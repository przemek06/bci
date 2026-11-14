"""The merged features (headlights, audio, events) and the BCI eyes-closed ghost must cooperate."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from helpers import requires_audio

from nightdrive import samples
from nightdrive.app import App
from nightdrive.scenes import DriveScene, GameOverScene


def key(k):
    return pygame.event.Event(pygame.KEYDOWN, key=k)


def start_drive(audio=False):
    app = App(seed=3, audio=audio)  # keyboard eyes by default
    app.scene.handle_event(key(pygame.K_RETURN))
    assert isinstance(app.scene, DriveScene)
    return app


def test_app_keeps_both_constructor_styles():
    """main() calls App(seed, eyes, eyes_log=...); the tests/game use audio=..."""
    app = App(1, "keyboard", eyes_log=False, audio=False)
    assert app.eyes.mode == "keyboard" and app.music.ok is False
    pygame.quit()


def test_space_toggles_headlights_but_not_during_a_keyboard_ghost():
    app = start_drive()
    drive = app.scene
    lights = drive.world.headlights
    drive.handle_event(key(pygame.K_SPACE))
    assert not lights.on
    drive.handle_event(key(pygame.K_SPACE))
    assert lights.on
    assert drive.ghost.trigger()  # holding SPACE now means "eyes closed"
    drive.handle_event(key(pygame.K_SPACE))
    assert lights.on  # unchanged
    pygame.quit()


def test_no_road_event_while_a_ghost_is_active():
    app = start_drive()
    drive = app.scene
    assert drive.ghost.trigger()
    drive.on_distracted()
    drive.handle_event(key(pygame.K_1))
    assert not drive.director.active
    pygame.quit()


@requires_audio
def test_ghost_has_sounds_and_death_screen_plays_them():
    for name in ("scare_ghost",):
        assert name in samples.COMPOSITES
    app = start_drive(audio=True)
    assert {"scare_ghost", "ghost_moan"} <= set(app.sfx.sounds)
    drive = app.scene
    assert drive.ghost.trigger()
    drive.update(1 / 60)
    assert app.music.duck  # music dips while the ghost is here
    over = GameOverScene(app, drive.world, drive.ghost.death_event, 12.0, 1)
    over.update(1 / 60)
    over.draw(app.canvas)  # uses the jump-scare image the ghost package registered
    assert over.event.name == "ghost"
    pygame.quit()


# --- eye gaze (webcam/mouse tracking) together with the ghost, audio and headlights ----------


def fake_gaze():
    from types import SimpleNamespace

    return SimpleNamespace(
        ready=True,
        point=None,
        source=SimpleNamespace(needs_calibration=False, status=lambda: "ok"),
        update=lambda: None,
        stop=lambda: None,
    )


def test_app_accepts_all_options_together():
    """audio + ghost eyes + gaze: every constructor argument from every branch works at once."""
    app = App(1, "keyboard", False, False, "mouse", [0], "mediapipe")
    assert (
        app.gaze is not None and app.eyes.mode == "keyboard" and app.music.ok is False
    )
    for _ in range(3):  # a few frames through the loop pieces: no crash
        app.eyes.update()
        app.gaze.update()
        app.scene.update(1 / 60)
        app.scene.draw(app.canvas)
    app.disable_gaze()
    pygame.quit()


def test_menu_has_eye_tracking_entry_and_still_quits():
    app = App(seed=1, audio=False)
    assert app.scene.options == ["START", "EYE TRACKING: OFF", "QUIT"]
    app.scene.selected = 2
    app.scene.handle_event(key(pygame.K_RETURN))
    assert app.running is False
    pygame.quit()


def test_g_is_the_ghost_and_tab_toggles_the_gaze_marker():
    app = start_drive()
    drive = app.scene
    assert app.show_gaze is True
    drive.handle_event(key(pygame.K_TAB))
    assert app.show_gaze is False
    drive.handle_event(key(pygame.K_TAB))
    assert app.show_gaze is True
    drive.handle_event(key(pygame.K_g))
    assert drive.ghost.active  # G spawns the ghost, it does not touch the gaze marker
    assert app.show_gaze is True
    pygame.quit()


def test_gaze_distraction_replaces_the_timer_but_never_interrupts_a_ghost():
    app = start_drive()
    drive = app.scene
    app.gaze = fake_gaze()
    drive.gaze_monitor.update = lambda dt, point: (
        True
    )  # "the player looked away long enough"
    assert drive.ghost.trigger()
    drive.update(1 / 60)
    assert not drive.director.active  # a ghost is running: no road event on top of it
    drive.ghost.reset()
    drive.update(1 / 60)
    assert drive.director.active  # gaze triggers the road event
    pygame.quit()


def test_gaze_does_not_run_the_random_timer_when_ready():
    app = start_drive()
    drive = app.scene
    app.gaze = fake_gaze()
    drive.gaze_monitor.update = lambda dt, point: False
    drive.auto_timer = 0.0  # would fire immediately without gaze
    drive.update(1 / 60)
    assert not drive.director.active
    app.gaze = None  # no gaze: the timer is back
    drive.update(1 / 60)
    assert drive.director.active
    pygame.quit()
