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
