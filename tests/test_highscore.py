"""The high score: storage rules, and the congratulations on the screens."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import json

import pygame
import pytest

from nightdrive import scenes
from nightdrive import settings as S
from nightdrive.app import App
from nightdrive.events import CATALOGUE
from nightdrive.highscore import HighScore
from nightdrive.scenes import DriveScene, GameOverScene, MenuScene

# --- storage -------------------------------------------------------------------------------


def test_missing_corrupt_or_odd_files_mean_no_record_yet(tmp_path):
    assert HighScore(tmp_path / "nope.json").best == 0
    for text in (
        "not json at all",
        '{"best": "abc"}',
        '{"best": -5}',
        "[]",
        '{"other": 1}',
    ):
        path = tmp_path / "bad.json"
        path.write_text(text, encoding="utf-8")
        assert HighScore(path).best == 0, text


def test_only_a_higher_score_is_a_record_and_it_is_kept(tmp_path):
    path = tmp_path / "hs.json"
    hs = HighScore(path)
    assert hs.submit(0) is False and not path.exists()  # 0 is not a record
    assert hs.submit(120) is True and hs.best == 120
    assert json.loads(path.read_text(encoding="utf-8")) == {"best": 120}
    assert hs.submit(120) is False  # a tie is not a record
    assert hs.submit(80) is False and hs.best == 120
    assert HighScore(path).best == 120  # still there next session
    assert hs.submit(121) is True and HighScore(path).best == 121


def test_an_unwritable_place_never_crashes_the_game(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    hs = HighScore(blocker / "sub" / "hs.json")  # a folder cannot be made under a file
    assert hs.submit(50) is True and hs.best == 50  # kept in memory for this session


# --- screens ---------------------------------------------------------------------------------


@pytest.fixture
def texts(monkeypatch):
    drawn = []
    real = scenes.draw_text
    monkeypatch.setattr(
        scenes,
        "draw_text",
        lambda surf, text, *a, **k: (drawn.append(text), real(surf, text, *a, **k))[1],
    )
    return drawn


def start_drive(best=0):
    app = App(seed=3, audio=False)
    if best:
        app.highscore.submit(best)
    app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    drive = app.scene
    assert isinstance(drive, DriveScene)
    drive.auto_timer = 1e9
    drive.ghost.timer = 1e9
    return app, drive


def game_over(app, drive, score):
    drive.world.score.value = float(score)
    return GameOverScene(app, drive.world, CATALOGUE[0], survived=30)


def finish(scene, app, seconds=4.5, dt=1 / 60):
    for _ in range(round(seconds / dt)):
        scene.update(dt)
        scene.draw(app.canvas)


def test_the_first_score_is_a_new_high_score(texts):
    app, drive = start_drive()
    over = game_over(app, drive, 500)
    assert over.new_record and app.highscore.best == 500
    finish(over, app)
    assert "NEW HIGH SCORE!" in texts and "CONGRATULATIONS!" in texts
    assert not any(
        t.startswith("PREVIOUS BEST") for t in texts
    )  # nothing to compare with yet
    pygame.quit()


def test_beating_the_record_congratulates_and_shows_the_previous_best(texts):
    app, drive = start_drive(best=500)
    over = game_over(app, drive, 800)
    assert over.new_record and over.previous_best == 500 and app.highscore.best == 800
    finish(over, app)
    assert "NEW HIGH SCORE!" in texts and "PREVIOUS BEST  500" in texts
    pygame.quit()


def test_a_lower_score_just_shows_the_high_score_to_beat(texts):
    app, drive = start_drive(best=500)
    over = game_over(app, drive, 200)
    assert not over.new_record and app.highscore.best == 500
    finish(over, app)
    assert "HIGH SCORE  500" in texts and "NEW HIGH SCORE!" not in texts
    pygame.quit()


def test_the_game_over_screen_chimes_once_for_a_record_and_never_otherwise():
    app, drive = start_drive(best=100)
    played = []
    app.sfx.play = lambda name, pan=None: played.append(name)
    finish(game_over(app, drive, 300), app, seconds=6.0)
    assert played.count("saved") == 1
    played.clear()
    finish(game_over(app, drive, 50), app, seconds=6.0)
    assert "saved" not in played
    pygame.quit()


def test_passing_the_record_mid_run_congratulates_once(texts):
    app, drive = start_drive(best=100)
    played = []
    app.sfx.play = lambda name, pan=None: played.append(name)
    drive.update(1 / 60)
    assert drive.record_left == 0  # not beaten yet
    drive.world.score.value = 150.0  # passes the 100 from an earlier run
    drive.update(1 / 60)
    drive.draw(app.canvas)
    assert (
        drive.record_left > 0
        and "NEW HIGH SCORE!" in texts
        and "CONGRATULATIONS!" in texts
    )
    assert played.count("saved") == 1
    for _ in range(
        round((S.RECORD_BANNER_S + 1) / (1 / 60))
    ):  # the banner goes away and stays away
        drive.update(1 / 60)
    assert drive.record_left == 0 and played.count("saved") == 1
    pygame.quit()


def test_no_mid_run_banner_when_there_is_no_record_to_beat(texts):
    app, drive = (
        start_drive()
    )  # first ever run: any score "beats" 0, which is not worth a banner
    drive.world.score.value = 400.0
    drive.update(1 / 60)
    drive.draw(app.canvas)
    assert drive.record_left == 0 and "NEW HIGH SCORE!" not in texts
    pygame.quit()


def test_the_best_is_only_shown_on_the_menu_and_the_end_screen_never_while_driving(
    texts,
):
    app, drive = start_drive(best=321)
    drive.update(1 / 60)
    drive.draw(app.canvas)
    assert not any(
        "BEST" in t or "HIGH SCORE" in t for t in texts
    )  # nothing at the bottom
    texts.clear()
    menu = MenuScene(app, drive.world)
    menu.draw(app.canvas)
    assert "HIGH SCORE  321" in texts
    pygame.quit()


def test_leaving_with_escape_keeps_a_new_best(tmp_path):
    app, drive = start_drive()
    drive.world.score.value = 300.0
    drive.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert isinstance(app.scene, MenuScene) and app.highscore.best == 300
    assert HighScore().best == 300  # saved to the (test) file
    pygame.quit()


def test_closing_the_window_mid_run_keeps_a_new_best():
    app, drive = start_drive()
    drive.world.score.value = 250.0
    assert drive.end_run() is True and app.highscore.best == 250
    pygame.quit()
