import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from nightdrive import settings as S
from nightdrive.app import App
from nightdrive.scenes import DriveScene, GameOverScene, MenuScene


def test_menu_to_drive_and_back():
    app = App(seed=1, audio=False)
    assert isinstance(app.scene, MenuScene)
    app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert isinstance(app.scene, DriveScene)
    start = app.scene.world.position
    for _ in range(600):  # 10 s of driving
        app.scene.update(1 / 60)
        app.scene.draw(app.canvas)
    assert app.scene.world.position != start
    assert app.scene.world.speed > S.MENU_SPEED
    app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert isinstance(app.scene, MenuScene)
    app.present()
    pygame.quit()


def test_failed_qte_leads_to_game_over_and_retry():
    app = App(seed=3, audio=False)
    app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    drive = app.scene
    drive.on_distracted()
    for _ in range(600):  # never press anything
        app.scene.update(1 / 60)
        app.scene.draw(app.canvas)
        if isinstance(app.scene, GameOverScene):
            break
    assert isinstance(app.scene, GameOverScene)
    over = app.scene
    for _ in range(int(4 / (1 / 60))):  # jump scare, fade, game-over screen
        over.update(1 / 60)
        over.draw(app.canvas)
    assert over.can_continue
    over.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert isinstance(app.scene, DriveScene) and app.scene.director.history == []
    pygame.quit()


def test_game_with_audio_runs_a_full_fail_cycle():
    app = App(seed=3, audio=True)
    app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    app.scene.on_distracted()
    for _ in range(600):
        app.scene.update(1 / 60)
        app.music.update(1 / 60)
        if isinstance(app.scene, GameOverScene):
            break
    assert isinstance(app.scene, GameOverScene)
    assert not app.music.playing  # silence for the scare
    pygame.quit()
