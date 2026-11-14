import random

import pygame

from . import settings as S
from .events import DEAD, QTE, EventDirector

TEXT = (225, 228, 255)
DIM = (120, 128, 170)
ACCENT = (255, 120, 90)
GOOD = (120, 255, 160)
BAD = (255, 90, 80)


def draw_text(surf, text, font, color, center=None, topleft=None, shadow=(5, 6, 16)):
    img = font.render(text, False, color)
    rect = img.get_rect(center=center) if center else img.get_rect(topleft=topleft)
    if shadow:
        surf.blit(font.render(text, False, shadow), rect.move(1, 1))
    surf.blit(img, rect)


class MenuScene:
    OPTIONS = ("START", "QUIT")

    def __init__(self, app, world):
        self.app = app
        self.world = world
        self.world.cruise = S.MENU_SPEED
        self.selected = 0
        self.veil = pygame.Surface((S.W, S.H), pygame.SRCALPHA)
        self.veil.fill((2, 3, 12, 110))

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_UP, pygame.K_w):
            self.selected = (self.selected - 1) % len(self.OPTIONS)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.selected = (self.selected + 1) % len(self.OPTIONS)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._choose()
        elif event.key == pygame.K_ESCAPE:
            self.app.quit()

    def _choose(self):
        if self.OPTIONS[self.selected] == "START":
            self.app.set_scene(DriveScene(self.app, self.world))
        else:
            self.app.quit()

    def update(self, dt):
        self.world.update(dt)

    def draw(self, surf):
        self.world.draw(surf)
        surf.blit(self.veil, (0, 0))
        draw_text(
            surf,
            "NIGHT DRIVE",
            self.app.font_title,
            TEXT,
            center=(S.W // 2, 42),
            shadow=(120, 30, 40),
        )
        draw_text(
            surf,
            "a calm drive through the dark",
            self.app.font_small,
            DIM,
            center=(S.W // 2, 66),
        )
        for i, label in enumerate(self.OPTIONS):
            selected = i == self.selected
            text = f"> {label} <" if selected else label
            draw_text(
                surf,
                text,
                self.app.font,
                ACCENT if selected else TEXT,
                center=(S.W // 2, 96 + i * 16),
            )
        draw_text(
            surf,
            "UP/DOWN + ENTER    F11 FULLSCREEN",
            self.app.font_small,
            DIM,
            center=(S.W // 2, 100 + 52),
        )


class DriveScene:
    def __init__(self, app, world):
        self.app = app
        self.world = world
        self.world.cruise = S.CRUISE_SPEED
        self.rng = random.Random(app.seed)
        self.director = EventDirector(world, self.rng)
        self.auto_timer = self.rng.uniform(*S.AUTO_EVENT_RANGE)
        self.elapsed = 0.0

    def on_distracted(self):
        """Called when the player's attention drops. For now fired by a timer or the E key."""
        self.director.trigger()

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_ESCAPE:
            self.director.reset()
            self.app.set_scene(MenuScene(self.app, self.world))
        elif pygame.K_a <= event.key <= pygame.K_z:
            letter = chr(event.key).upper()
            if self.director.state == QTE:
                self.director.press(letter)
            elif letter == "E" and not self.director.active:
                self.on_distracted()  # debug: trigger an event now

    def update(self, dt):
        self.elapsed += dt
        self.world.update(dt)
        self.director.update(dt)
        if self.director.state == DEAD:
            self.app.set_scene(
                GameOverScene(
                    self.app,
                    self.world,
                    self.director.event,
                    self.elapsed,
                    self.director.saved_count,
                )
            )
            self.director.reset()
            return
        if not self.director.active:
            self.auto_timer -= dt
            if self.auto_timer <= 0:
                self.on_distracted()
                self.auto_timer = self.rng.uniform(*S.AUTO_EVENT_RANGE)

    def draw(self, surf):
        d = self.director
        self.world.draw(surf)
        if d.state == QTE:
            self._draw_prompt(surf, d.qte)
        elif d.message:
            draw_text(surf, d.message, self.app.font_big, GOOD, center=(S.W // 2, 40))
        if self.elapsed < 5:
            alpha = 255 if self.elapsed < 3.5 else int(255 * (5 - self.elapsed) / 1.5)
            hint = self.app.font_small.render("ESC - MENU", False, DIM)
            hint.set_alpha(alpha)
            surf.blit(hint, hint.get_rect(topright=(S.W - 6, 10)))

    def _draw_prompt(self, surf, qte):
        cx, top = S.W // 2, 16
        # border goes from white to red as time runs out
        r = qte.remaining
        color = (255, int(80 + 175 * r), int(80 + 175 * r))
        box = pygame.Rect(0, 0, 44, 44)
        box.midtop = (cx, top)
        pygame.draw.rect(surf, (6, 8, 20), box)
        pygame.draw.rect(surf, color, box, 2)
        draw_text(surf, qte.letter, self.app.font_title, color, center=box.center)
        bar = pygame.Rect(0, 0, 64, 5)
        bar.midtop = (cx, box.bottom + 4)
        pygame.draw.rect(surf, (6, 8, 20), bar)
        pygame.draw.rect(
            surf, color, (bar.x + 1, bar.y + 1, int((bar.w - 2) * r), bar.h - 2)
        )


class GameOverScene:
    """Jump scare close-up, fade to black, then the game-over screen."""

    def __init__(self, app, world, event, survived, saved):
        self.app = app
        self.world = world
        self.event = event
        self.survived = survived
        self.saved = saved
        self.image = app.assets.jumpscares[event.name]
        self.t = 0.0
        self.rng = random.Random()

    @property
    def can_continue(self):
        return self.t > S.JUMPSCARE_TIME + S.GAME_OVER_FADE + 0.3

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN or not self.can_continue:
            return
        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.world.speed = 0.0
            self.app.set_scene(DriveScene(self.app, self.world))
        elif event.key == pygame.K_ESCAPE:
            self.app.set_scene(MenuScene(self.app, self.world))

    def update(self, dt):
        self.t += dt
        self.world.update(dt)

    def draw(self, surf):
        surf.fill((0, 0, 0))
        if self.t < S.JUMPSCARE_TIME + S.GAME_OVER_FADE:
            self._draw_scare(surf)
        else:
            self._draw_game_over(surf)

    def _draw_scare(self, surf):
        t = self.t
        zoom = 1.1 + 0.25 * min(
            1.0, t / S.JUMPSCARE_TIME
        )  # slams in big, then creeps closer
        size = (int(S.W * zoom), int(S.H * zoom))
        img = pygame.transform.scale(self.image, size)
        amp = max(1, int(8 * (1 - t / S.JUMPSCARE_TIME)))
        ox = (S.W - size[0]) // 2 + self.rng.randint(-amp, amp)
        oy = (S.H - size[1]) // 2 + self.rng.randint(-amp, amp)
        surf.blit(img, (ox, oy))
        if int(t * 14) % 2 == 0 and t < S.JUMPSCARE_TIME:  # flicker
            veil = pygame.Surface((S.W, S.H), pygame.SRCALPHA)
            veil.fill((255, 0, 0, 50))
            surf.blit(veil, (0, 0))
        if t < 0.1:  # white flash on impact
            surf.fill((255, 255, 255), special_flags=pygame.BLEND_RGB_ADD)
        if self.event.kind == "funny" and t < S.JUMPSCARE_TIME:
            draw_text(
                surf,
                "BAWK!",
                self.app.font_title,
                (255, 255, 255),
                center=(S.W // 2, 160),
                shadow=(120, 30, 40),
            )
        if t > S.JUMPSCARE_TIME:  # fade out
            fade = min(1.0, (t - S.JUMPSCARE_TIME) / S.GAME_OVER_FADE)
            veil = pygame.Surface((S.W, S.H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * fade)))
            surf.blit(veil, (0, 0))

    def _draw_game_over(self, surf):
        cx = S.W // 2
        mins, secs = divmod(int(self.survived), 60)
        draw_text(
            surf,
            "GAME OVER",
            self.app.font_title,
            BAD,
            center=(cx, 40),
            shadow=(40, 6, 10),
        )
        draw_text(surf, self.event.over_text, self.app.font, TEXT, center=(cx, 74))
        draw_text(
            surf, f"TIME  {mins}:{secs:02d}", self.app.font, DIM, center=(cx, 100)
        )
        draw_text(surf, f"SAVED  {self.saved}", self.app.font, DIM, center=(cx, 116))
        if self.can_continue and int(self.t * 2) % 2 == 0:
            draw_text(
                surf,
                "ENTER - DRIVE AGAIN",
                self.app.font_small,
                ACCENT,
                center=(cx, 150),
            )
        if self.can_continue:
            draw_text(surf, "ESC - MENU", self.app.font_small, DIM, center=(cx, 164))
