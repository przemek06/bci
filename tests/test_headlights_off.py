"""The headlight features are switched off for now (settings.HEADLIGHTS_ENABLED = False).

These tests use the shipped default (the `headlights_default` fixture). The same features keep
being tested with the flag ON by the other test files (see conftest.py).
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from nightdrive import art
from nightdrive import settings as S
from nightdrive.app import App
from nightdrive.light_switch import ClickLightSwitch, SsvepLightSwitch
from nightdrive.roadside import IDLE
from nightdrive.scenes import DriveScene


def start_drive(**kw):
    app = App(seed=7, audio=False, **kw)
    app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert isinstance(app.scene, DriveScene)
    drive = app.scene
    drive.auto_timer = (
        1e9  # no random road events or ghosts: only the headlights are under test
    )
    drive.ghost.timer = 1e9
    return app, drive


def click_button(app):
    scale, ox, oy = app._view()
    cx, cy = art.LIGHT_BUTTON.center
    pos = (ox + cx * scale, oy + cy * scale)
    app.scene.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)
    )


def test_the_game_ships_with_the_headlight_features_off(headlights_default):
    assert S.HEADLIGHTS_ENABLED is False


def test_lights_stay_on_and_never_flicker_and_no_monster_comes(headlights_default):
    _app, drive = start_drive()
    lights = drive.world.headlights
    for _ in range(
        60 * 90
    ):  # 90 s of driving: longer than FLICKER_RANGE and the monster delays
        drive.update(1 / 60)
        assert lights.on and not lights.flickering and lights.light == 1.0
        assert drive.roadside.mode == IDLE
    assert lights.flicker_count == 0
    pygame.quit()


def test_the_button_and_the_switch_do_nothing(headlights_default):
    app, drive = start_drive()
    lights = drive.world.headlights
    click_button(app)
    drive.toggle_lights()
    drive.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    drive.update(1 / 60)
    assert lights.on and lights.light == 1.0
    assert drive.world.button_flicker is False and drive.world.button_hover is False
    pygame.quit()


def test_the_monster_debug_key_does_nothing(headlights_default):
    _app, drive = start_drive()
    drive.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m))
    drive.update(1 / 60)
    assert drive.roadside.mode == IDLE
    pygame.quit()


def test_the_dashboard_button_and_lamp_are_not_drawn(headlights_default, monkeypatch):
    app, drive = start_drive()
    drive.update(1 / 60)

    def button_pixels():
        drive.draw(app.canvas)
        return pygame.image.tobytes(
            app.canvas.subsurface(art.LIGHT_BUTTON).copy(), "RGB"
        )

    off = button_pixels()
    monkeypatch.setattr(S, "HEADLIGHTS_ENABLED", True)  # same frame, feature on
    on = button_pixels()
    assert off != on  # the button is there only when the feature is on
    pygame.quit()


def test_the_lights_option_is_ignored_and_no_ssvep_reader_starts(
    headlights_default, capsys
):
    app = App(seed=7, audio=False, lights="ssvep")
    assert isinstance(app.light_switch, ClickLightSwitch)
    assert not isinstance(app.light_switch, SsvepLightSwitch)
    assert "[headlights] switched off" in capsys.readouterr().out
    pygame.quit()
