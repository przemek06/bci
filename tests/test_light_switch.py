"""The headlight button: a flickering dashboard control behind a LightSwitch interface (click now, BCI later)."""

import itertools
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from nightdrive import art
from nightdrive import settings as S
from nightdrive.app import App
from nightdrive.light_switch import (
    ClickLightSwitch,
    LightSwitch,
    make_light_switch,
    stimulus_lit,
)
from nightdrive.scenes import DriveScene
from nightdrive.world import World


def start_drive():
    app = App(seed=3, audio=False)
    app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert isinstance(app.scene, DriveScene)
    return app, app.scene


def window_pos(app, canvas_xy):
    scale, ox, oy = app._view()
    return (ox + canvas_xy[0] * scale, oy + canvas_xy[1] * scale)


def click(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=pos)


# --- the flicker (the future SSVEP stimulus) -------------------------------------------------


def test_stimulus_is_a_50_percent_square_wave_at_the_given_frequency():
    hz = 15.0
    samples = [stimulus_lit(i / 6000, hz) for i in range(6000)]  # one second at 6 kHz
    assert abs(sum(samples) / len(samples) - 0.5) < 0.01  # half lit
    transitions = sum(a != b for a, b in itertools.pairwise(samples))
    assert 2 * hz - 1 <= transitions <= 2 * hz + 1  # two per cycle
    assert stimulus_lit(0.0, hz) and not stimulus_lit(
        0.5 / hz + 1e-6, hz
    )  # lit first, then dark


def test_at_60_fps_15_hz_is_two_frames_lit_two_dark():
    frames = [stimulus_lit(k / 60, 15.0) for k in range(8)]
    assert frames == [True, True, False, False, True, True, False, False]


def test_zero_hz_means_steady():
    assert all(stimulus_lit(t / 10, 0) for t in range(50))


def test_default_frequency_avoids_the_alpha_band_used_by_the_ghost():
    assert not (8.0 <= S.HEADLIGHT_BUTTON_HZ <= 12.0)


# --- the dashboard button ----------------------------------------------------------------------


def face_pixel(surf):
    return tuple(surf.get_at(art.LIGHT_BUTTON.move(0, 0).topleft)[:3])


def test_button_alternates_between_lit_and_black_and_shows_the_lights_state():
    def draw(lit, lights_on):
        surf = pygame.Surface((S.W, S.H))
        art.draw_light_button(surf, lit, lights_on, False, 0)
        return surf

    on_lit, off_lit, dark = draw(True, True), draw(True, False), draw(False, True)
    assert face_pixel(on_lit) == (120, 210, 255) and face_pixel(off_lit) == (
        255,
        150,
        80,
    )
    assert face_pixel(dark) == (
        4,
        5,
        8,
    )  # the dark half-cycle: strong contrast for the stimulus
    assert face_pixel(on_lit) != face_pixel(off_lit)


def test_hover_highlights_the_border():
    plain, hover = pygame.Surface((S.W, S.H)), pygame.Surface((S.W, S.H))
    art.draw_light_button(plain, True, True, False, 0)
    art.draw_light_button(hover, True, True, True, 0)
    corner = art.LIGHT_BUTTON.inflate(4, 4).midtop
    assert plain.get_at(corner) != hover.get_at(corner)


def test_world_flickers_the_button_at_its_frequency_only_while_driving():
    world = World(art.Art(), seed=1)
    surf = pygame.Surface((S.W, S.H))
    clock = [0.0]
    world.clock = lambda: clock[0]
    world.button_hz = 15.0
    pixels = {}
    for flicker in (False, True):
        world.button_flicker = flicker
        seen = set()
        for t in (0.0, 0.5 / 15 + 1e-4, 1.0 / 15 + 1e-4, 1.5 / 15 + 1e-4):
            clock[0] = t
            world.draw(surf)
            seen.add(
                tuple(
                    surf.get_at((art.LIGHT_BUTTON.x + 1, art.LIGHT_BUTTON.centery))[:3]
                )
            )
        pixels[flicker] = seen
    assert len(pixels[False]) == 1  # steady in the menu
    assert len(pixels[True]) == 2  # lit and dark while driving


def test_menu_button_is_steady_and_the_drive_button_flickers():
    app = App(seed=3, audio=False)
    assert app.scene.world.button_flicker is False
    app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert app.scene.world.button_flicker is True
    assert (
        app.scene.world.button_hz
        == app.light_switch.stimulus_hz
        == S.HEADLIGHT_BUTTON_HZ
    )


# --- the click implementation ----------------------------------------------------------------------


def test_clicking_the_button_toggles_and_clicking_elsewhere_does_not():
    app, _drive = start_drive()
    switch = app.light_switch
    assert isinstance(switch, ClickLightSwitch)
    centre = window_pos(app, art.LIGHT_BUTTON.center)
    assert switch.handle_event(click(centre)) is True
    assert switch.handle_event(click(centre, button=3)) is False  # right click
    assert (
        switch.handle_event(click(window_pos(app, (250, 60)))) is False
    )  # elsewhere on the screen
    assert switch.handle_event(click((-5, -5))) is False  # outside the window canvas
    assert (
        switch.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
        is False
    )
    pygame.quit()


def test_button_is_a_little_forgiving_at_the_edges():
    app, _ = start_drive()
    just_outside = (art.LIGHT_BUTTON.right + 1, art.LIGHT_BUTTON.centery)
    far_outside = (art.LIGHT_BUTTON.right + 12, art.LIGHT_BUTTON.centery)
    assert app.light_switch.handle_event(click(window_pos(app, just_outside)))
    assert not app.light_switch.handle_event(click(window_pos(app, far_outside)))
    pygame.quit()


def test_window_to_canvas_respects_the_letterbox():
    app = App(seed=1, audio=False)
    scale, ox, oy = app._view()
    assert app.window_to_canvas((ox + 10 * scale, oy + 20 * scale)) == (10, 20)
    assert app.window_to_canvas((ox - 1, oy + 5)) is None
    assert app.window_to_canvas((ox + S.W * scale, oy)) is None
    pygame.quit()


def test_hover_follows_the_mouse(monkeypatch):
    app, drive = start_drive()
    over = window_pos(app, art.LIGHT_BUTTON.center)
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: over)
    drive.update(1 / 60)
    assert drive.world.button_hover is True
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: window_pos(app, (250, 60)))
    drive.update(1 / 60)
    assert drive.world.button_hover is False
    pygame.quit()


# --- the interface: a future BCI plugs in here -------------------------------------------------------


def test_base_switch_never_toggles_and_has_no_hover():
    base = LightSwitch()
    assert base.handle_event(click((0, 0))) is False and base.update(1.0) is False
    assert base.hover is False and base.stimulus_hz == S.HEADLIGHT_BUTTON_HZ
    base.start()
    base.stop()


def test_a_polling_input_such_as_a_bci_toggles_through_update():
    class FakeSsvep(LightSwitch):
        stimulus_hz = 7.5  # its own frequency: the button follows it

        def __init__(self):
            self.attended = False
            self.started = self.stopped = False

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

        def update(self, dt):
            fired, self.attended = self.attended, False
            return fired

    app, drive = start_drive()
    bci = FakeSsvep()
    app.light_switch = bci
    bci.start()
    lights = drive.world.headlights
    drive.update(1 / 60)
    assert lights.on  # nothing detected: nothing happens
    bci.attended = True  # the classifier decides the player is looking at the flicker
    drive.update(1 / 60)
    assert not lights.on
    drive.update(1 / 60)
    assert not lights.on  # one detection = one toggle
    assert bci.started
    pygame.quit()


def test_factory_knows_click_and_ssvep_and_rejects_the_rest():
    from nightdrive.light_switch import SsvepLightSwitch

    app = App(seed=1, audio=False)
    assert isinstance(make_light_switch("click", app), ClickLightSwitch)
    ssvep = make_light_switch("ssvep", app, log=False)  # not started: no stream thread
    assert isinstance(ssvep, SsvepLightSwitch) and isinstance(ssvep, LightSwitch)
    with pytest.raises(ValueError):
        make_light_switch("telepathy", app)
    pygame.quit()


def test_the_app_starts_and_stops_its_light_switch():
    app = App(seed=1, audio=False)
    events = []
    app.light_switch.stop = lambda: events.append("stop")
    pygame.event.post(pygame.event.Event(pygame.QUIT))
    app.run()
    assert events == ["stop"]
