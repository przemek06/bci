import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pygame

from nightdrive import settings as S
from nightdrive.art import Art
from nightdrive.headlights import Headlights
from nightdrive.world import World


def make(enabled=True, seed=1):
    h = Headlights(random.Random(seed))
    h.flicker_enabled = enabled
    return h


def run(h, seconds, dt=1 / 60):
    for _ in range(int(seconds / dt)):
        h.update(dt)


def test_flicker_starts_after_the_countdown_only_when_enabled():
    h = make(enabled=False)
    run(h, S.FLICKER_RANGE[1] + 1)
    assert not h.flickering
    h = make()
    run(h, S.FLICKER_RANGE[0] - 1)
    assert not h.flickering
    run(h, S.FLICKER_RANGE[1])
    assert h.flickering and h.flicker_count == 1


def test_flicker_is_fixed_only_by_off_then_on():
    h = make()
    run(h, S.FLICKER_RANGE[1] + 1)
    assert h.flickering
    h.toggle()  # off: still broken
    assert not h.on and h.flickering and h.fixed_count == 0
    h.toggle()  # on again: fixed
    assert h.on and not h.flickering and h.fixed_count == 1
    run(h, 1.0)
    assert h.light > 0.99


def test_toggling_healthy_lights_is_not_a_fix():
    h = make()
    h.toggle()
    h.toggle()
    assert h.fixed_count == 0 and not h.flickering


def test_no_flicker_while_switched_off():
    h = make()
    h.toggle()
    run(h, S.FLICKER_RANGE[1] * 2)
    assert not h.flickering and h.light < 0.01


def test_flicker_actually_varies_the_light():
    h = make()
    run(h, S.FLICKER_RANGE[1] + 1)
    levels = set()
    for _ in range(300):
        h.update(1 / 60)
        levels.add(round(h.light, 2))
    assert len(levels) >= 3 and min(levels) < 0.2 and max(levels) > 0.9


def brightness(world, light):
    surf = pygame.Surface((S.W, S.H))
    world.headlights.light = light
    world.draw(surf)
    return np.asarray(pygame.surfarray.array3d(surf), dtype=float)[
        :, S.HORIZON + 5 :
    ].mean()


def test_lights_off_make_the_road_much_darker():
    world = World(Art(), seed=2)
    world.update(0.1)
    on, off = brightness(world, 1.0), brightness(world, 0.0)
    assert off < on * 0.8
    assert brightness(world, 0.5) < on
