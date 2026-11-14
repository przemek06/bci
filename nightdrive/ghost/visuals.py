"""Ghost art (procedural, like the rest of the game) and the on-screen challenge overlay."""

import math
import random

import pygame

from .. import settings as S
from .encounter import ACTIVE, PASSED, GhostEncounter

TEXT = (225, 228, 255)
GOOD = (120, 255, 160)
BAD = (255, 90, 80)
DIM = (120, 128, 170)
SHADOW = (5, 6, 16)

BODY = (205, 220, 240)
BODY_SHADE = (140, 160, 200)
FIGURE_W, FIGURE_H = 80, 120


def make_ghost_figure() -> pygame.Surface:
    """A hovering sheet ghost, drawn small and scaled up (nearest-neighbour) when shown."""
    w, h = FIGURE_W, FIGURE_H
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, BODY_SHADE, (2, 0, w - 4, 74))
    pygame.draw.ellipse(s, BODY, (5, 2, w - 10, 70))
    pygame.draw.rect(s, BODY, (5, 36, w - 10, 70))
    pygame.draw.rect(s, BODY_SHADE, (w - 14, 36, 9, 70))  # shaded right side
    bumps = 5
    cw = (w - 10) / bumps
    for i in range(bumps):  # jagged ragged hem
        cx = int(5 + cw * (i + 0.5))
        pygame.draw.circle(s, BODY, (cx, 104 + (7 if i % 2 else 0)), int(cw / 2) + 1)
    pygame.draw.ellipse(s, BODY_SHADE, (-6, 52, 18, 38))  # arms
    pygame.draw.ellipse(s, BODY_SHADE, (w - 12, 52, 18, 38))
    for ex in (20, 46):  # hollow eyes
        pygame.draw.ellipse(s, (6, 6, 14), (ex, 26, 15, 24))
        pygame.draw.circle(s, (230, 60, 70), (ex + 7, 42), 2)
    pygame.draw.ellipse(s, (6, 6, 14), (30, 60, 20, 30))  # wailing mouth
    return s


def make_ghost_scare() -> pygame.Surface:
    """Full-screen close-up used for the jump scare when the player fails."""
    w, h = S.W, S.H
    s = pygame.Surface((w, h))
    s.fill((3, 3, 9))
    for r in range(120, 20, -10):  # cold glow behind the face
        k = (120 - r) // 4
        pygame.draw.ellipse(
            s, (6 + k, 10 + k, 22 + k * 2), (w // 2 - r * 1.5, h // 2 - r, r * 3, r * 2)
        )
    pygame.draw.ellipse(s, BODY_SHADE, (46, -34, 228, 250))
    pygame.draw.ellipse(s, (222, 232, 248), (54, -30, 212, 244))
    rng = random.Random(3)
    for _ in range(26):  # ragged vertical streaks
        x = rng.randint(70, 250)
        y = rng.randint(0, 90)
        pygame.draw.line(
            s,
            (170, 188, 220),
            (x, y),
            (x + rng.randint(-3, 3), y + rng.randint(30, 90)),
        )
    for ex in (92, 176):  # sunken sockets
        pygame.draw.ellipse(s, (90, 104, 140), (ex - 6, 38, 62, 92))
        pygame.draw.ellipse(s, (4, 4, 10), (ex, 44, 50, 80))
        pygame.draw.circle(s, (230, 50, 60), (ex + 25, 98), 5)
    pygame.draw.line(s, (4, 4, 10), (84, 34), (140, 52), 4)  # angry brows
    pygame.draw.line(s, (4, 4, 10), (236, 34), (180, 52), 4)
    pygame.draw.ellipse(s, (4, 4, 10), (124, 116, 72, 92))  # screaming mouth
    for i in range(6):  # jagged teeth along the top of the mouth
        tx = 130 + i * 11
        pygame.draw.polygon(
            s, (222, 232, 248), [(tx, 122), (tx + 10, 122), (tx + 5, 138)]
        )
    return s


class GhostVisuals:
    def __init__(self, app) -> None:
        self.app = app
        self.figure = make_ghost_figure()
        app.assets.jumpscares.setdefault("ghost", make_ghost_scare())
        self.t = 0.0
        self.flash = 0.0
        self.dark = 0.0  # 0..1, screen dims while the eyes are closed
        self.rng = random.Random(11)

    def reset(self) -> None:
        self.t = self.flash = self.dark = 0.0

    def start(self) -> None:
        self.t = 0.0
        self.flash = 1.0
        self.dark = 0.0

    def update(self, dt: float, enc: GhostEncounter, eyes_closed: bool) -> None:
        self.t += dt
        self.flash = max(0.0, self.flash - dt / 0.12)
        target = 1.0 if (enc.state == ACTIVE and eyes_closed) else 0.0
        self.dark += (target - self.dark) * min(1.0, dt * 6)

    # --- drawing ------------------------------------------------------------

    def draw(self, surf, enc: GhostEncounter, hold_s: float, hint: str) -> None:
        if enc.state == ACTIVE:
            self._draw_ghost(
                surf, 0.5 + 0.4 * (1 - enc.time_left / enc.cfg.deadline_s), 1.0
            )
            self._draw_darkness(surf)
            self._draw_prompt(surf, enc, hold_s, hint)
        elif enc.state == PASSED:
            fade = max(0.0, enc.relief_left / enc.cfg.relief_s)
            self._draw_ghost(surf, 0.9 + (1 - fade) * 0.3, fade * 0.6)
            self.app_text(surf, "THE GHOST PASSES...", GOOD, 40)
        if self.flash > 0:
            surf.fill(
                tuple(int(120 * self.flash) for _ in range(3)),
                special_flags=pygame.BLEND_RGB_ADD,
            )

    def app_text(self, surf, text, color, y, font=None):
        font = font or self.app.font_big
        img = font.render(text, False, color)
        rect = img.get_rect(center=(S.W // 2, y))
        surf.blit(font.render(text, False, SHADOW), rect.move(1, 1))
        surf.blit(img, rect)

    def _draw_ghost(self, surf, scale: float, alpha: float) -> None:
        w, h = int(FIGURE_W * scale * 1.6), int(FIGURE_H * scale * 1.6)
        img = pygame.transform.scale(self.figure, (w, h))
        a = (150 + 40 * math.sin(self.t * 11)) * alpha * (1 - self.dark * 0.9)
        img.set_alpha(int(max(0, min(255, a))))
        wobble = math.sin(self.t * 3.0) * 6
        bob = math.sin(self.t * 2.2) * 4
        surf.blit(img, img.get_rect(center=(S.W // 2 + wobble, S.HORIZON + 26 + bob)))

    def _draw_darkness(self, surf) -> None:
        if self.dark > 0.02:
            veil = pygame.Surface((S.W, S.H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(215 * self.dark)))
            surf.blit(veil, (0, 0))

    def _draw_prompt(self, surf, enc: GhostEncounter, hold_s: float, hint: str) -> None:
        flash = int(self.t * 6) % 2 == 0
        self.app_text(surf, "CLOSE YOUR EYES!", BAD if flash else TEXT, 22)
        small = self.app.font_small
        self.app_text(surf, f"{hint} FOR {hold_s:g} SECONDS", DIM, 38, small)
        self._bar(surf, 52, enc.progress, GOOD)
        self._bar(surf, 60, enc.time_left / enc.cfg.deadline_s, BAD, height=3)

    def _bar(self, surf, y: int, frac: float, color, height: int = 5) -> None:
        bar = pygame.Rect(0, 0, 100, height)
        bar.midtop = (S.W // 2, y)
        pygame.draw.rect(surf, (6, 8, 20), bar)
        pygame.draw.rect(
            surf,
            color,
            (bar.x + 1, bar.y + 1, int((bar.w - 2) * max(0, min(1, frac))), bar.h - 2),
        )
