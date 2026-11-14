import math

import numpy as np
import pygame

from . import settings as S
from .gaze.session import CalibrationSession
from .scenes import ACCENT, BAD, DIM, GOOD, TEXT, MenuScene, draw_text

INTRO, RUN, RESULT, FAILED = range(4)


class CalibrationScene:
    """Look at each dot while it shrinks; then a regression maps eye features to screen coordinates."""

    def __init__(self, app, world):
        self.app = app
        self.world = world
        self.state = INTRO
        self.session = self._new_session()
        self.cal = None
        self.t = 0.0
        self.run_t = 0.0
        self.was_fullscreen = app.fullscreen
        self.font = pygame.font.Font(None, 28)

    @property
    def draws_window(self):
        """The dots are drawn on the whole screen, not on the small pixel-art canvas."""
        return self.state == RUN

    def _new_session(self):
        return CalibrationSession(block=getattr(self.app.gaze.source, "block", None))

    def _menu(self):
        self.app.set_fullscreen(self.was_fullscreen)
        self.app.set_scene(MenuScene(self.app, self.world))

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_ESCAPE:
            self._menu()
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.state == INTRO and self.app.gaze.source.latest() is not None:
                self.session = self._new_session()
                self.run_t = 0.0
                self.app.set_fullscreen(True)  # calibrate over the whole screen
                self.state = RUN
            elif self.state == RESULT:
                self.app.gaze.set_calibration(self.cal)
                self.app.gaze.save_calibration()
                self._menu()
        elif event.key == pygame.K_r and self.state in (RESULT, FAILED):
            self.state = INTRO

    def update(self, dt):
        self.t += dt
        self.world.update(dt)
        if self.state != RUN:
            return
        self.run_t += dt
        if self.run_t < 0.8:  # let the display mode switch settle
            return
        self.session.update(dt, self.app.gaze.source.latest())
        if self.session.done:
            self.app.set_fullscreen(self.was_fullscreen)
            try:
                self.cal = self.session.fit()
                self.cal.tag = self.app.gaze_tag
                self.state = RESULT
            except (ValueError, np.linalg.LinAlgError):
                self.state = FAILED

    def draw_window(self, win):
        win.fill((4, 6, 14))
        ww, wh = win.get_size()
        s = self.session
        tx, ty = s.target
        px, py = int(tx * ww), int(ty * wh)
        shrink = 1.0 - min(1.0, s.t / (S.CALIB_SETTLE + S.CALIB_SAMPLE)) * 0.6
        pulse = 1 + 0.15 * math.sin(self.t * 8)
        r = max(4, int(wh * 0.025 * shrink * pulse))
        pygame.draw.circle(win, (255, 120, 90), (px, py), r + 6, 2)
        pygame.draw.circle(
            win, (255, 255, 255) if s.sampling else (120, 120, 140), (px, py), r
        )
        pygame.draw.circle(win, (0, 0, 0), (px, py), 2)
        label = f"{s.index + 1}/{len(s.targets)}   {self.app.gaze.source.status()}"
        img = self.font.render(label, True, DIM)
        win.blit(img, img.get_rect(midbottom=(ww // 2, wh - 12)))
        hint = (
            "Keep looking at the dot while slowly moving your head: lean, turn, tilt"
            if s.moving
            else "Keep your head still and follow the dot with your eyes"
        )
        img = self.font.render(hint, True, ACCENT if s.moving else DIM)
        win.blit(img, img.get_rect(midtop=(ww // 2, 12)))

    def draw(self, surf):
        surf.fill((4, 6, 14))
        cx = S.W // 2
        f = self.app.font_small
        if self.state == INTRO:
            draw_text(surf, "EYE CALIBRATION", self.app.font_big, TEXT, center=(cx, 30))
            for i, line in enumerate(
                (
                    "Sit at your normal driving distance with your face well lit.",
                    "Round 1: eyes only. Round 2: keep watching the dot while moving your head.",
                    "Full screen for ~45 s: first head still, then moving your head.",
                )
            ):
                draw_text(surf, line, f, DIM, center=(cx, 60 + i * 12))
            ready = self.app.gaze.source.latest() is not None
            status = self.app.gaze.source.status()
            draw_text(
                surf,
                f"camera: {status}",
                f,
                GOOD if status == "tracking" else BAD,
                center=(cx, 110),
            )
            if ready and int(self.t * 2) % 2 == 0:
                draw_text(surf, "ENTER - START", f, ACCENT, center=(cx, 140))
            draw_text(surf, "ESC - BACK", f, DIM, center=(cx, 164))
        elif self.state == RESULT:
            ex, ey = (e * 100 for e in self.cal.error_xy)
            good = max(ex, ey) < 8
            draw_text(
                surf,
                "CALIBRATED",
                self.app.font_big,
                GOOD if good else ACCENT,
                center=(cx, 40),
            )
            draw_text(
                surf,
                f"{self.cal.method}: error x {ex:.1f}%  y {ey:.1f}% of the screen",
                f,
                TEXT,
                center=(cx, 70),
            )
            if not good:
                draw_text(
                    surf, "Rather high; consider retrying.", f, DIM, center=(cx, 84)
                )
            p = self.app.gaze.source.latest()
            if p is not None:
                x, y = self.cal.predict(p.values)[0]
                dw, dh = pygame.display.get_desktop_sizes()[0]
                cx0, cy0, cw, ch = self.app._canvas_on_screen()
                pos = (int((x * dw - cx0) / cw * S.W), int((y * dh - cy0) / ch * S.H))
                pygame.draw.circle(surf, GOOD, pos, 4, 1)
            draw_text(
                surf,
                "ENTER - SAVE    R - RETRY    ESC - DISCARD",
                f,
                ACCENT,
                center=(cx, 150),
            )
        else:
            draw_text(
                surf, "CALIBRATION FAILED", self.app.font_big, BAD, center=(cx, 60)
            )
            draw_text(surf, "R - RETRY    ESC - BACK", f, DIM, center=(cx, 110))
