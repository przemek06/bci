"""The merged features (headlights, audio, events) and the BCI eyes-closed ghost must cooperate."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from helpers import requires_audio

from nightdrive import samples
from nightdrive import settings as S
from nightdrive.app import App
from nightdrive.scenes import DriveScene, GameOverScene


def key(k):
    return pygame.event.Event(pygame.KEYDOWN, key=k)


def click_lights(app, button=1):
    """Click the dashboard headlight button (the window coordinates of its centre)."""
    from nightdrive import art

    scale, ox, oy = app._view()
    cx, cy = art.LIGHT_BUTTON.center
    pos = (ox + cx * scale, oy + cy * scale)
    app.scene.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=pos)
    )


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


def test_clicking_the_dashboard_button_toggles_the_headlights_and_space_does_not():
    app = start_drive()
    drive = app.scene
    lights = drive.world.headlights
    click_lights(app)
    assert not lights.on
    click_lights(app)
    assert lights.on
    drive.handle_event(key(pygame.K_SPACE))
    assert lights.on  # SPACE no longer works the lights
    assert drive.ghost.trigger()  # and it is free to mean "eyes closed" for the ghost
    click_lights(app)
    assert not lights.on  # the button still works during a ghost
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
    over = GameOverScene(app, drive.world, drive.ghost.death_event, 12.0)
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


@requires_audio
def test_ghost_sounds_play_through_the_real_drive_scene():
    app = start_drive(audio=True)
    drive = app.scene
    assert {"ghost_rumble", "ghost_appear", "ghost_relief", "engine"} <= set(
        app.sfx.sounds
    )
    assert drive.ghost.trigger()
    for _ in range(90):  # 3 s: appears, drone running, rattles around
        drive.update(1 / 30)
    assert "ghost_rumble" in app.sfx._loops
    drive.handle_event(key(pygame.K_ESCAPE))  # leaving the drive silences the ghost
    assert "ghost_rumble" not in app.sfx._loops
    pygame.quit()


# --- roadside monster and hitchhikers inside the real drive scene --------------------------------


def quiet_drive(audio=False):
    app = start_drive(audio=audio)
    drive = app.scene
    drive.auto_timer = drive.ghost.timer = 9999  # no random QTE events or ghosts
    drive.roadside._next_monster = drive.roadside._next_hitch = 9999
    drive.world.headlights.flicker_enabled = False
    return app, drive


def run_until(app, drive, cls, seconds):
    for _ in range(int(seconds * 60)):
        app.scene.update(1 / 60)
        app.scene.draw(app.canvas)
        if isinstance(app.scene, cls):
            return True
    return False


def test_monster_with_the_lights_on_ends_the_run():
    app, drive = quiet_drive()
    drive.handle_event(key(pygame.K_m))
    assert drive.roadside.mode == "monster"
    assert run_until(app, drive, GameOverScene, 9)
    assert (
        app.scene.event.name == "monster"
        and app.scene.event.over_text == "THE MONSTER SAW YOU"
    )
    pygame.quit()


def test_monster_with_the_lights_off_is_survived_for_points():
    app, drive = quiet_drive()
    drive.handle_event(key(pygame.K_m))
    click_lights(app)  # lights off
    assert not drive.world.headlights.on
    for _ in range(7 * 60):
        app.scene.update(1 / 60)
        app.scene.draw(app.canvas)  # the HUD draws the warning and the suspicion bar
        assert isinstance(app.scene, DriveScene)  # still alive
    assert drive.roadside.survived_count == 1
    assert drive.world.score.display >= S.MONSTER_BONUS
    pygame.quit()


def test_picking_up_a_real_hitchhiker_gives_points_and_an_impostor_ends_the_run():
    app, drive = quiet_drive()
    drive.handle_event(key(pygame.K_h))  # random: force a real one for the test
    drive.roadside.reset()
    assert drive.roadside.start_hitchhiker(impostor=False)
    for _ in range(600):
        drive.update(1 / 60)
        drive.draw(app.canvas)
        if drive.roadside.can_pick_up:
            break
    drive.handle_event(key(pygame.K_RETURN))
    assert drive.roadside.mode == "boarding"
    for _ in range(120):
        drive.update(1 / 60)
    assert drive.world.score.display >= S.HITCH_BONUS and isinstance(
        app.scene, DriveScene
    )

    drive.roadside.reset()
    drive.roadside.start_hitchhiker(impostor=True)
    for _ in range(600):
        drive.update(1 / 60)
        if drive.roadside.can_pick_up:
            break
    drive.handle_event(key(pygame.K_RETURN))
    assert run_until(app, drive, GameOverScene, 4)
    assert app.scene.event.name == "impostor"
    pygame.quit()


def test_enter_does_nothing_without_a_hitchhiker_nearby():
    _app, drive = quiet_drive()
    before = drive.world.score.display
    drive.handle_event(key(pygame.K_RETURN))
    assert not drive.roadside.active and drive.world.speed >= 0
    drive.roadside.start_hitchhiker(impostor=False)
    drive.handle_event(key(pygame.K_RETURN))  # far away
    assert drive.roadside.mode == "hitch" and drive.world.score.display == before
    pygame.quit()


def test_one_scare_at_a_time():
    _app, drive = quiet_drive()
    drive.roadside.start_monster()
    drive.on_distracted()  # a QTE event while a monster is out: refused
    drive.handle_event(key(pygame.K_1))
    drive.handle_event(key(pygame.K_g))  # and no ghost either
    assert not drive.director.active and not drive.ghost.active
    drive.roadside.reset()
    assert drive.ghost.trigger()
    drive.handle_event(key(pygame.K_m))  # no monster during a ghost
    assert not drive.roadside.active
    pygame.quit()


def test_leaving_the_drive_clears_the_roadside():
    _app, drive = quiet_drive()
    drive.roadside.start_monster()
    drive.handle_event(key(pygame.K_ESCAPE))
    assert not drive.roadside.active and drive.world.actors == []
    pygame.quit()


@requires_audio
def test_roadside_sounds_exist_and_play():
    app, drive = quiet_drive(audio=True)
    assert {
        "scare_monster",
        "scare_impostor",
        "pickup",
        "monster_growl",
        "monster_rumble",
    } <= set(app.sfx.sounds)
    drive.roadside.start_monster()  # plays the growl
    drive.world.position = S.ROADSIDE_SPAWN_DISTANCE - 10000
    for _ in range(30):
        drive.update(1 / 60)
    assert "monster_rumble" in app.sfx._loops  # tension while it is suspicious
    drive.handle_event(key(pygame.K_ESCAPE))
    assert "monster_rumble" not in app.sfx._loops
    pygame.quit()


def test_a_new_run_never_inherits_roadside_creatures():
    app, drive = quiet_drive()
    drive.roadside.start_hitchhiker(impostor=True)
    assert drive.world.actors
    world = drive.world
    app.scene = DriveScene(
        app, world
    )  # e.g. retry after a game over that left something behind
    assert world.actors == []
    pygame.quit()


def test_dying_to_a_qte_event_leaves_no_roadside_creature_behind():
    app, drive = quiet_drive()
    drive.roadside.start_monster()
    drive.roadside.reset()  # (the director and the roadside never run together; reset must be safe)
    drive.on_distracted()
    for _ in range(600):
        app.scene.update(1 / 60)
        if isinstance(app.scene, GameOverScene):
            break
    assert isinstance(app.scene, GameOverScene) and drive.world.actors == []
    pygame.quit()


def test_roadside_warnings_show_once_per_game_not_once_per_run(monkeypatch):
    texts = []
    import nightdrive.scenes as scenes_mod

    real_draw_text = scenes_mod.draw_text
    monkeypatch.setattr(
        scenes_mod,
        "draw_text",
        lambda surf, text, *a, **k: (
            texts.append(text),
            real_draw_text(surf, text, *a, **k),
        )[1],
    )
    app, drive = quiet_drive()
    drive.roadside.start_monster()
    drive.draw(app.canvas)
    assert "MONSTER! LIGHTS OFF!" in texts  # the first one warns
    assert run_until(app, drive, GameOverScene, 9)  # lights on: it gets you
    for _ in range(300):  # the game-over screen ignores keys for its first ~2.7 s
        app.scene.update(1 / 60)
    app.scene.handle_event(key(pygame.K_RETURN))  # retry
    assert isinstance(app.scene, DriveScene)
    retry = app.scene
    retry.auto_timer = retry.ghost.timer = 9999
    retry.roadside._next_monster = retry.roadside._next_hitch = 9999
    assert "monster" in app.roadside_hints
    texts.clear()
    retry.roadside.start_monster()
    for _ in range(90):
        retry.update(1 / 60)
        retry.draw(app.canvas)
    assert not any(
        "MONSTER" in t or "DARK" in t for t in texts
    )  # no text, no bar: just the monster
    assert retry.roadside.mode == "monster"
    pygame.quit()
