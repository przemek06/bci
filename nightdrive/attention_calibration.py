"""Attention calibration before the game: sit still, eyes open, while the baseline is recorded.

Shown after START (and on a retry) only while the attention source still needs a baseline, i.e. with
the headset (`--attention bci`). The recording starts when this screen opens, so by the time the
drive begins the attention feature already works and the player can just play. Once the baseline
exists (the first time only) every later START goes straight into the game.

ENTER skips it ("play anyway": the baseline is then still recorded during the drive, and events wait
for it), ESC goes back to the menu. If the headset stream does not show up, the screen says so.
"""

import pygame

from . import settings as S
from .scenes import BAD, DIM, GOOD, TEXT, DriveScene, MenuScene, draw_text

READY_S = 1.2  # "READY!" stays this long before the game starts
NO_SIGNAL_S = 8.0  # no headset stream for this long: say so


class AttentionCalibrationScene:
    def __init__(self, app, world):
        self.app = app
        self.world = world
        self.world.cruise = S.MENU_SPEED
        self.t = 0.0
        self.ready_t = 0.0
        self.veil = pygame.Surface((S.W, S.H), pygame.SRCALPHA)
        self.veil.fill((2, 3, 12, 150))
        self._emit("calibration screen opened: sit still, eyes open")

    # --- state read from the attention source ------------------------------------

    @property
    def source(self):
        return self.app.attention

    @property
    def waiting(self) -> bool:
        """The headset stream has not been seen yet."""
        return bool(getattr(self.source, "waiting_for_stream", False))

    @property
    def progress(self) -> float:
        return max(
            0.0, min(1.0, float(getattr(self.source, "calibration_progress", 0.0)))
        )

    @property
    def done(self) -> bool:
        return bool(self.source.calibrated)

    @property
    def no_signal(self) -> bool:
        return self.waiting and self.t > NO_SIGNAL_S

    def _emit(self, text: str) -> None:
        log = getattr(self.source, "log", None)
        if log:
            log(f"[attention] {text}")

    # --- scene API ----------------------------------------------------------------

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_ESCAPE:
            self.app.set_scene(MenuScene(self.app, self.world))
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._emit(
                "calibration skipped: playing anyway (it continues during the drive)"
            )
            self._start()

    def _start(self):
        self.app.set_scene(DriveScene(self.app, self.world))

    def update(self, dt):
        self.t += dt
        self.world.update(dt)
        self.app.sfx.engine(self.world.speed / S.CRUISE_SPEED)
        self.app.sfx.ambience()
        self.source.update()  # records the baseline (and discards anything buffered before now)
        if self.done:
            if self.ready_t == 0.0:
                self._emit("calibrated: starting the game")
            self.ready_t += dt
            if self.ready_t >= READY_S:
                self._start()

    def draw(self, surf):
        self.world.draw(surf)
        surf.blit(self.veil, (0, 0))
        cx = S.W // 2
        draw_text(
            surf,
            "CALIBRATION",
            self.app.font_title,
            TEXT,
            center=(cx, 34),
            shadow=(120, 30, 40),
        )
        if self.done:
            draw_text(surf, "READY!", self.app.font_big, GOOD, center=(cx, 74))
        elif self.waiting:
            dots = "." * (1 + int(self.t * 2) % 3)
            draw_text(
                surf,
                f"WAITING FOR THE HEADSET{dots}",
                self.app.font,
                TEXT,
                center=(cx, 74),
            )
        else:
            draw_text(
                surf, "CALIBRATING YOUR ATTENTION", self.app.font, TEXT, center=(cx, 74)
            )
        if self.no_signal:
            draw_text(
                surf,
                "NO HEADSET SIGNAL - IS THE PUBLISHER RUNNING?",
                self.app.font_small,
                BAD,
                center=(cx, 90),
            )
        else:
            draw_text(
                surf,
                "SIT STILL, EYES OPEN, LOOK AT THE SCREEN",
                self.app.font_small,
                DIM,
                center=(cx, 90),
            )
        self._draw_bar(surf, cx, 108, 1.0 if self.done else self.progress)
        percent = 100 if self.done else int(self.progress * 100)
        draw_text(surf, f"{percent}%", self.app.font_small, DIM, center=(cx, 122))
        draw_text(
            surf,
            "ENTER - PLAY ANYWAY      ESC - MENU",
            self.app.font_small,
            DIM,
            center=(cx, 160),
        )

    @staticmethod
    def _draw_bar(surf, cx, y, frac):
        bar = pygame.Rect(0, 0, 160, 8)
        bar.midtop = (cx, y)
        pygame.draw.rect(surf, (6, 8, 20), bar)
        pygame.draw.rect(
            surf, GOOD, (bar.x + 1, bar.y + 1, int((bar.w - 2) * frac), bar.h - 2)
        )
        pygame.draw.rect(surf, DIM, bar, 1)
