"""The player has no settings: no mute, nothing about fullscreen on the menu. (Eye tracking keeps its menu entries.)"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

import nightdrive.scenes as scenes_mod
from nightdrive.app import App


def run_with_keys(app, *keys):
    """Feed key presses to the real event loop, then quit."""
    for k in keys:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k))
    pygame.event.post(pygame.event.Event(pygame.QUIT))
    app.run()


def menu_texts(monkeypatch):
    texts = []
    real = scenes_mod.draw_text
    monkeypatch.setattr(
        scenes_mod,
        "draw_text",
        lambda surf, text, *a, **k: (texts.append(text), real(surf, text, *a, **k))[1],
    )
    app = App(seed=1, audio=False)
    for _ in range(5):
        app.scene.update(1 / 60)
    app.scene.draw(app.canvas)
    return app, texts


def test_menu_does_not_mention_fullscreen_or_mute(monkeypatch):
    app, texts = menu_texts(monkeypatch)
    shown = " ".join(texts).upper()
    for word in ("FULLSCREEN", "FULL SCREEN", "MUTE", "F11", "F10"):
        assert word not in shown, word
    assert "UP/DOWN + ENTER" in shown  # navigation help stays
    assert app.scene.options == [
        "START",
        "EYE TRACKING: OFF",
        "QUIT",
    ]  # eye tracking stays
    pygame.quit()


def test_f11_still_toggles_fullscreen_quietly():
    app = App(seed=1, audio=False)
    assert not app.fullscreen
    run_with_keys(app, pygame.K_F11)
    assert app.fullscreen


def test_f10_does_nothing_any_more():
    app = App(seed=1, audio=False)
    before = (app.fullscreen, app.music.target)
    run_with_keys(app, pygame.K_F10)
    assert (app.fullscreen, app.music.target) == before
    assert not hasattr(app.music, "muted") and not hasattr(app.sfx, "muted")
