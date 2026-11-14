"""CopChallenge: look away from the road for too long and the law gets involved.

Escalation while the player keeps not looking at the road (see COP_* in settings.py):
    2 s  a warning: EYES ON THE ROAD
    5 s  a cop shows up beside the car, sirens, screaming at you
    8 s  he pulls you over: game over
Looking back at the road for a moment calms everything down.

The logic (`CopEncounter`) takes `away` and `dt` and nothing else, so it is testable headless.
"""

import pygame

from . import settings as S
from .art import Sprite, make_glow
from .events import Actor, EventType

IDLE, WARNING, COP, BUSTED = "idle", "warning", "cop", "busted"

DEATH_EVENT = EventType(
    "cop", "scary", "cop", "", "YOU GOT PULLED OVER", "STEP OUT OF THE CAR!"
)


class CopEncounter:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.away = 0.0  # seconds of continuous inattention
        self.calm = 0.0  # seconds looking at the road since the last lapse
        self.state = IDLE

    @property
    def dead(self) -> bool:
        return self.state == BUSTED

    @property
    def active(self) -> bool:
        return self.state != IDLE

    @property
    def approach(self) -> float:
        """0..1 progress of the cop between showing up and pulling you over."""
        span = S.COP_BUST_TIME - S.COP_APPEAR_TIME
        return min(1.0, max(0.0, (self.away - S.COP_APPEAR_TIME) / span))

    def update(self, dt: float, away: bool | None) -> None:
        """`away` None means the eyes are untrackable: hold everything where it is."""
        if self.state == BUSTED or away is None:
            return
        if away:
            self.away += dt
            self.calm = 0.0
        elif self.away > 0.0:
            self.calm += dt
            if self.calm >= S.COP_REGAIN_TIME:
                self.away = 0.0
        if self.away >= S.COP_BUST_TIME:
            self.state = BUSTED
        elif self.away >= S.COP_APPEAR_TIME:
            self.state = COP
        elif self.away >= S.COP_WARN_TIME:
            self.state = WARNING
        else:
            self.state = IDLE


def make_cop_car(flip: bool) -> Sprite:
    """Rear view of a police car; `flip` swaps which side of the light bar is red."""
    s = pygame.Surface((44, 28), pygame.SRCALPHA)
    red, blue = (255, 50, 50), (60, 110, 255)
    for cx in (7, 37):
        pygame.draw.rect(s, (12, 12, 16), (cx - 4, 21, 8, 7))
    pygame.draw.polygon(s, (226, 230, 242), [(8, 14), (11, 5), (33, 5), (36, 14)])
    pygame.draw.rect(s, (20, 26, 46), (12, 7, 20, 6))
    pygame.draw.rect(s, (26, 30, 54), (2, 14, 40, 9))
    pygame.draw.rect(s, (226, 230, 242), (2, 17, 40, 2))
    pygame.draw.rect(s, (70, 72, 84), (1, 22, 42, 3))
    for x in (4, 34):
        pygame.draw.rect(s, (230, 40, 40), (x, 15, 6, 2))
    pygame.draw.rect(s, (235, 235, 235), (19, 20, 6, 2))
    left, right = (blue, red) if flip else (red, blue)
    pygame.draw.rect(s, left, (13, 1, 9, 4))
    pygame.draw.rect(s, right, (22, 1, 9, 4))
    return Sprite(s, 1800, (0.32, 0.1), "blue" if flip else "red")


def make_cop_scare() -> pygame.Surface:
    """Full-screen close-up: an angry cop's face pressed against the window."""
    w, h = S.W, S.H
    s = pygame.Surface((w, h))
    s.fill((6, 8, 24))
    for i in range(0, w, 40):  # flashlight beam
        pygame.draw.polygon(
            s, (20 + i // 40, 28, 56), [(w, 0), (w, h), (i, h // 2 + 20)]
        )
    skin, dark = (226, 178, 140), (10, 12, 30)
    pygame.draw.ellipse(s, skin, (80, 20, 160, 190))
    pygame.draw.rect(s, dark, (70, 6, 180, 46))  # cap
    pygame.draw.rect(s, (8, 8, 12), (84, 50, 152, 12))
    pygame.draw.circle(s, (230, 200, 70), (160, 28), 9)
    for ex in (112, 176):  # mirrored sunglasses with a red glint
        pygame.draw.rect(s, (8, 8, 12), (ex, 76, 40, 24))
        pygame.draw.line(s, (200, 40, 50), (ex + 6, 82), (ex + 18, 82), 2)
    pygame.draw.line(s, (8, 8, 12), (104, 68), (152, 76), 4)  # angry brows
    pygame.draw.line(s, (8, 8, 12), (216, 68), (168, 76), 4)
    pygame.draw.ellipse(s, (70, 16, 20), (124, 122, 72, 52))  # yelling mouth
    pygame.draw.rect(s, (240, 240, 240), (132, 124, 56, 10))
    pygame.draw.rect(s, (200, 40, 50), (0, 0, w, 6))  # light bar
    pygame.draw.rect(s, (40, 90, 255), (w // 2, 0, w // 2, 6))
    return s


class CopChallenge:
    """Drives the police car: it creeps up on your left, and if you keep looking away it
    overtakes, cuts in front and brakes you to a stop. Look back at the road and it drops
    behind you again, out of sight."""

    def __init__(self, app, world) -> None:
        self.app = app
        self.world = world
        self.encounter = CopEncounter()
        sprites = app.assets.sprites
        sprites.setdefault("cop_a", make_cop_car(False))
        sprites.setdefault("cop_b", make_cop_car(True))
        app.assets.glows.setdefault("blue", make_glow((0.3, 0.5, 1.0)))
        app.assets.jumpscares.setdefault("cop", make_cop_scare())
        self.death_event = DEATH_EVENT
        self.t = 0.0
        self.gap = (
            S.COP_HIDDEN_GAP
        )  # world units ahead of the player (negative: behind)
        self.offset = S.COP_LEFT_OFFSET
        self.actor: Actor | None = None
        self.bust_t = 0.0
        self.stopped = 0.0  # seconds since the busted car came to a halt
        self._state = IDLE
        self._braking = False

    @property
    def away(self) -> float:
        return self.encounter.away

    @property
    def active(self) -> bool:
        return self.encounter.active

    @property
    def dead(self) -> bool:
        """Busted and the car has come to a stop (or it took too long)."""
        return self.encounter.dead and (
            self.stopped >= S.COP_STOP_HOLD or self.bust_t > 6.0
        )

    def reset(self) -> None:
        self.encounter.reset()
        self._state = IDLE
        self.gap = S.COP_HIDDEN_GAP
        self.offset = S.COP_LEFT_OFFSET
        self.stopped = self.bust_t = 0.0
        self._remove_actor()
        if self._braking:
            self._braking = False
            self.world.cruise = S.CRUISE_SPEED
        self.app.sfx.stop_loop("siren")

    def _remove_actor(self) -> None:
        if self.actor in self.world.actors:
            self.world.actors.remove(self.actor)
        self.actor = None

    def update(self, dt: float, away: bool | None) -> None:
        self.t += dt
        enc = self.encounter
        enc.update(dt, away)
        sfx = self.app.sfx
        if enc.state != self._state:
            if enc.state == WARNING and self._state == IDLE:
                sfx.play("alert")
            elif enc.state == BUSTED:
                self._braking = True
                self.world.cruise = 0.0
                self.world.speed_rate = 1.2
            self._state = enc.state
        self._move_car(dt)
        if self.actor and enc.state in (COP, BUSTED):
            sfx.loop("siren")
        else:
            sfx.stop_loop("siren")

    def _move_car(self, dt: float) -> None:
        enc = self.encounter
        if enc.state == BUSTED:
            gap, offset = S.COP_STOP_GAP, S.LANE_X  # cut in front of the player
        elif enc.state == COP:
            gap = S.COP_ALONGSIDE_GAP + S.COP_OVERTAKE_GAP * enc.approach
            offset = S.COP_LEFT_OFFSET
        else:
            gap, offset = S.COP_HIDDEN_GAP, S.COP_LEFT_OFFSET
        rate = min(1.0, dt * (2.5 if enc.state != IDLE else 1.5))
        self.gap += (gap - self.gap) * rate
        self.offset += (offset - self.offset) * min(1.0, dt * 1.5)
        world = self.world
        visible = self.gap >= S.COP_VISIBLE_GAP
        if visible and self.actor is None:
            self.actor = Actor("cop_a", 0.0, self.offset, self.offset)
            world.actors.append(self.actor)
        elif not visible and self.actor is not None:
            self._remove_actor()
        if self.actor:
            self.actor.z = (world.position + self.gap) % world.track.length
            self.actor.offset = self.offset
            self.actor.kind = "cop_a" if int(self.t * 4) % 2 == 0 else "cop_b"
        if enc.state == BUSTED:
            self.bust_t += dt
            if world.speed < S.CRUISE_SPEED * 0.03:
                self.stopped += dt

    def draw(self, surf) -> None:
        enc = self.encounter
        if enc.state == IDLE:
            return
        app = self.app
        blink = int(self.t * 4) % 2 == 0
        if enc.state == WARNING:
            if blink:
                _text(surf, app, "EYES ON THE ROAD!", app.font_big, (255, 190, 60), 40)
            return
        flip = int(self.t * 5) % 2 == 0  # red/blue light wash
        veil = pygame.Surface((S.W, S.H), pygame.SRCALPHA)
        veil.fill((255, 30, 40, 44) if flip else (40, 90, 255, 44))
        surf.blit(veil, (0, 0))
        if enc.state == BUSTED:
            _text(surf, app, "PULL OVER!", app.font_big, (255, 90, 80), 40)
            return
        shake = int(2 * enc.approach) * (1 if blink else -1)
        _text(surf, app, "EYES ON THE ROAD!!", app.font_big, (255, 90, 80), 40 + shake)
        left = max(0.0, S.COP_BUST_TIME - enc.away)
        _text(
            surf,
            app,
            f"PULLING YOU OVER IN {left:.0f}",
            app.font_small,
            (255, 190, 60),
            62,
        )


def _text(surf, app, text, font, color, y) -> None:
    shadow = font.render(text, False, (5, 6, 16))
    img = font.render(text, False, color)
    r = img.get_rect(center=(S.W // 2, y))
    surf.blit(shadow, r.move(1, 1))
    surf.blit(img, r)
