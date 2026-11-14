"""Headlight state: a switch, plus random flicker that only an off/on cycle fixes. No drawing here."""

import random

from . import settings as S


class Headlights:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.flicker_enabled = False  # only while driving
        self.on = True
        self.flickering = False
        self.light = 1.0  # 0..1, what the renderer sees
        self.flicker_count = 0
        self.fixed_count = 0
        self._countdown = self.rng.uniform(*S.FLICKER_RANGE)
        self._level = 1.0  # current step of the flicker pattern
        self._step_timer = 0.0

    def reset(self):
        self.on, self.flickering, self.light, self._level = True, False, 1.0, 1.0
        self._countdown = self.rng.uniform(*S.FLICKER_RANGE)

    def toggle(self):
        """The switch. Turning flickering lights back on after switching them off fixes them."""
        self.on = not self.on
        if self.on and self.flickering:
            self.flickering = False
            self.fixed_count += 1
            self._countdown = self.rng.uniform(*S.FLICKER_RANGE)

    def update(self, dt):
        if self.flicker_enabled and self.on and not self.flickering:
            self._countdown -= dt
            if self._countdown <= 0:
                self.flickering = True
                self.flicker_count += 1
                self._step_timer = 0.0

        if not self.on:
            target = 0.0
        elif self.flickering:
            self._step_timer -= dt
            if (
                self._step_timer <= 0
            ):  # next burst: mostly dark or dim, sometimes fully lit
                self._level = self.rng.choice([0.0, 0.0, 0.15, 0.4, 1.0, 1.0])
                self._step_timer = self.rng.uniform(0.04, 0.35)
            target = self._level
        else:
            target = 1.0

        if self.flickering and self.on:
            self.light = target  # flicker is abrupt
        else:
            self.light += (target - self.light) * min(
                1.0, dt * 14
            )  # a quick fade for the switch
