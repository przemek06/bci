"""The driving world: position, speed, and drawing of the whole first-person view."""

import math

from . import art
from . import settings as S
from .renderer import RoadRenderer
from .track import Track


class World:
    def __init__(self, assets, seed=None):
        self.art = assets
        self.track = Track(seed)
        self.renderer = RoadRenderer(self.track, assets)
        self.position = 0.0
        self.speed = 0.0
        self.cruise = S.MENU_SPEED
        self.speed_rate = 0.8  # how fast speed approaches cruise
        self.actors = []  # creatures on the road, see events.py
        self.t = 0.0
        self.steer = 0.0
        self.player_x = S.LANE_X
        self.bg_offsets = [0.0, 0.0, 0.0]  # sky, far hills, near hills

    def update(self, dt):
        self.t += dt
        self.speed += (self.cruise - self.speed) * min(1.0, dt * self.speed_rate)
        self.position = (self.position + self.speed * dt) % self.track.length
        seg = self.track.segment_at(self.position)
        travelled = self.speed * dt / S.SEGMENT_LENGTH
        for i, k in enumerate((S.PARALLAX_SKY, S.PARALLAX_FAR, S.PARALLAX_NEAR)):
            self.bg_offsets[i] += k * seg.curve * travelled
        target = max(-0.6, min(0.6, seg.curve * 0.12))
        self.steer += (target - self.steer) * min(1.0, dt * 3)
        self.player_x = (
            S.LANE_X + 0.05 * math.sin(self.t * 0.4) + 0.03 * math.sin(self.t * 0.9)
        )

    def draw(self, surf):
        a = self.art
        surf.fill(S.FOG_COLOR)
        sky_x = -(self.bg_offsets[0] % S.BG_WIDTH)
        surf.blit(a.sky, (sky_x, 0))
        surf.blit(a.sky, (sky_x + S.BG_WIDTH, 0))
        art.draw_stars(surf, a.stars, self.bg_offsets[0], self.t)
        for i, (layer, _) in enumerate(a.hills, start=1):
            x = -(self.bg_offsets[i] % S.BG_WIDTH)
            surf.blit(layer, (x, 0))
            surf.blit(layer, (x + S.BG_WIDTH, 0))
        self.renderer.draw(surf, self.position, self.player_x, self.actors, self.t)

        speed_frac = min(1.0, self.speed / S.CRUISE_SPEED) * 0.6
        dy = round(0.6 * math.sin(self.t * 5.0) * min(1.0, self.speed / S.CRUISE_SPEED))
        surf.blit(a.cockpit, (0, dy))
        art.draw_gauge(surf, speed_frac, dy)
        art.draw_wheel(surf, self.steer, dy)
