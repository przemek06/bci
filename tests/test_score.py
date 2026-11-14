import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from nightdrive import art
from nightdrive import settings as S
from nightdrive.app import App
from nightdrive.scenes import DriveScene, GameOverScene, MenuScene
from nightdrive.score import MAX_DISPLAY, Score


def key(k):
    return pygame.event.Event(pygame.KEYDOWN, key=k)


# --- the score itself (pure logic) ---------------------------------------------------------


def test_score_rises_with_time_only():
    score = Score(per_second=10)
    assert score.display == 0
    for _ in range(60 * 5):  # five seconds
        score.update(1 / 60)
    assert score.display == 50
    assert score.history == []  # nothing else has touched it


def test_default_rate_comes_from_settings():
    score = Score()
    score.update(2.0)
    assert score.display == 2 * S.SCORE_PER_SECOND


def test_other_sources_can_add_and_subtract():
    score = Score(per_second=0)
    score.add(100, "saved a QTE")
    score.add(-30, "bumped a prop")
    assert score.display == 70
    assert score.history == [(100, "saved a QTE"), (-30, "bumped a prop")]
    score.add(-1000, "huge penalty")
    assert score.display == 0  # never negative


def test_display_is_an_integer_capped_at_six_digits():
    score = Score(per_second=0)
    score.add(MAX_DISPLAY + 5000)
    assert score.display == MAX_DISPLAY and isinstance(score.display, int)
    score.reset()
    assert score.display == 0 and score.history == []


# --- the dashboard readout ---------------------------------------------------------------


def lit_pixels(value, dy=0):
    surf = pygame.Surface((S.W, S.H))
    surf.fill((0, 0, 0))
    art.draw_score(surf, value, dy)
    box = art.SCORE_BOX.move(0, dy)
    lit = sum(
        1
        for x in range(box.left, box.right)
        for y in range(box.top, box.bottom)
        if surf.get_at((x, y))[:3] == art.LCD_LIT
    )
    return surf, lit


def test_dashboard_digits_light_up_the_right_amount():
    # the 3x5 font: '0' has 12 pixels, '1' has 8, '8' has 13 (six of them: 78)
    assert lit_pixels(0)[1] == 12
    assert lit_pixels(1)[1] == 8
    assert lit_pixels(888888)[1] == 78


def test_dashboard_readout_stays_inside_its_box_and_follows_the_bob():
    for dy in (-1, 0, 1):
        surf, _ = lit_pixels(123456, dy)
        box = art.SCORE_BOX.move(0, dy).inflate(2, 2)
        for x in range(S.W):
            for y in range(S.H):
                if surf.get_at((x, y))[:3] != (0, 0, 0):
                    assert box.collidepoint(x, y), (x, y, dy)
    surf, _ = lit_pixels(99999999)  # too many digits: shows the last six, no crash


# --- in the game ---------------------------------------------------------------------------


def start_drive():
    app = App(seed=3, audio=False)
    app.scene.handle_event(key(pygame.K_RETURN))
    assert isinstance(app.scene, DriveScene)
    return app


def test_score_runs_during_the_drive_and_restarts_each_time():
    app = start_drive()
    drive = app.scene
    drive.auto_timer = drive.ghost.timer = 9999  # keep the drive quiet
    for _ in range(60 * 3):
        drive.update(1 / 60)
    assert 25 <= drive.world.score.display <= 35  # about 3 s * 10/s
    drive.draw(app.canvas)  # the dashboard draws it
    drive.handle_event(key(pygame.K_ESCAPE))
    assert isinstance(app.scene, MenuScene) and drive.world.score.display == 0
    app.scene.handle_event(key(pygame.K_RETURN))  # a new drive starts from zero
    assert app.scene.world.score.display == 0
    pygame.quit()


def test_menu_does_not_earn_points():
    app = App(seed=3, audio=False)
    for _ in range(120):
        app.scene.update(1 / 60)
    assert app.scene.world.score.display == 0
    pygame.quit()


def test_game_over_shows_the_final_score_and_retry_resets_it():
    app = start_drive()
    drive = app.scene
    drive.auto_timer = drive.ghost.timer = 9999
    for _ in range(60 * 2):
        drive.update(1 / 60)
    final = drive.world.score.display
    assert final > 0
    drive.on_distracted()
    for _ in range(600):  # never press anything: the event kills the run
        app.scene.update(1 / 60)
        if isinstance(app.scene, GameOverScene):
            break
    over = app.scene
    assert isinstance(over, GameOverScene) and over.world.score.display >= final
    for _ in range(int(4 / (1 / 60))):
        over.update(1 / 60)
        over.draw(app.canvas)  # renders the SCORE line
    over.handle_event(key(pygame.K_RETURN))
    assert isinstance(app.scene, DriveScene) and app.scene.world.score.display == 0
    pygame.quit()
