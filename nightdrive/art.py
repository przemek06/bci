"""Procedural pixel art: roadside sprites, sky, hills, dashboard. Everything is drawn at 320x180."""

import math
import random

import pygame

from . import settings as S


class Sprite:
    def __init__(self, surf, world_h, glow=None, glow_color="warm"):
        self.surf = surf
        self.world_h = world_h  # height in world units
        self.aspect = surf.get_width() / surf.get_height()
        self.glow = glow  # (fx, fy) position of a light as a fraction of the sprite
        self.glow_color = glow_color


def _surf(w, h):
    return pygame.Surface((w, h), pygame.SRCALPHA)


def _pine():
    s = _surf(24, 40)
    pygame.draw.rect(s, (30, 22, 18), (10, 34, 4, 6))
    for top, bottom, half in ((2, 16, 6), (10, 26, 9), (18, 36, 11)):
        pygame.draw.polygon(
            s, (14, 34, 28), [(12, top), (12 - half, bottom), (12 + half, bottom)]
        )
        pygame.draw.polygon(
            s, (24, 56, 44), [(12, top), (12 - half, bottom), (12 - half + 3, bottom)]
        )
    return Sprite(s, 2600)


def _round_tree():
    s = _surf(28, 40)
    pygame.draw.rect(s, (36, 26, 20), (13, 24, 3, 16))
    for cx, cy, r in ((14, 14, 11), (8, 20, 8), (20, 20, 8)):
        pygame.draw.circle(s, (16, 40, 26), (cx, cy), r)
    pygame.draw.circle(s, (26, 60, 38), (10, 11), 5)
    return Sprite(s, 2400)


def _bush():
    s = _surf(24, 12)
    for cx, cy, r in ((8, 8, 4), (14, 6, 5), (19, 8, 4)):
        pygame.draw.circle(s, (14, 38, 24), (cx, cy), r)
    pygame.draw.circle(s, (24, 56, 36), (12, 4), 2)
    return Sprite(s, 500)


def _post():
    s = _surf(4, 14)
    pygame.draw.rect(s, (150, 150, 160), (0, 0, 4, 14))
    pygame.draw.rect(
        s, (230, 150, 40), (0, 2, 4, 3)
    )  # reflector catching the headlights
    return Sprite(s, 450)


def _lamp(on_left):
    # Drawn for the right side of the road (arm reaches left, towards the road).
    s = _surf(20, 56)
    pygame.draw.rect(s, (52, 54, 62), (15, 6, 2, 50))
    pygame.draw.rect(s, (52, 54, 62), (6, 4, 11, 2))
    pygame.draw.rect(s, (255, 232, 170), (3, 5, 4, 3))
    glow = (5 / 20, 6 / 56)
    if on_left:
        s = pygame.transform.flip(s, True, False)
        glow = (1 - glow[0], glow[1])
    return Sprite(s, 2800, glow)


def _deer():
    s = _surf(40, 36)
    body, light = (96, 66, 46), (122, 88, 60)
    for x in (8, 12, 26, 30):
        pygame.draw.rect(s, (66, 46, 32), (x, 22, 3, 14))
    pygame.draw.ellipse(s, body, (5, 11, 28, 15))
    pygame.draw.ellipse(s, light, (9, 12, 16, 4))
    pygame.draw.rect(s, body, (3, 13, 4, 3))
    pygame.draw.polygon(s, body, [(29, 16), (33, 6), (38, 8), (34, 20)])
    pygame.draw.polygon(s, body, [(33, 5), (38, 3), (40, 8), (35, 10)])
    for a, b in (((35, 3), (33, 0)), ((36, 3), (38, 0)), ((34, 2), (31, 1))):
        pygame.draw.line(s, (190, 180, 160), a, b)
    s.set_at((37, 5), (255, 60, 40))
    return Sprite(s, 2200, (37 / 40, 5 / 36), "red")


def _chicken():
    s = _surf(28, 30)
    for x in (12, 16):
        pygame.draw.line(s, (230, 150, 40), (x, 22), (x, 28))
        pygame.draw.rect(s, (230, 150, 40), (x - 1, 28, 3, 2))
    pygame.draw.polygon(s, (214, 214, 208), [(6, 14), (0, 6), (7, 10)])
    pygame.draw.ellipse(s, (238, 238, 230), (4, 10, 18, 14))
    pygame.draw.ellipse(s, (206, 206, 200), (8, 14, 9, 7))
    pygame.draw.circle(s, (238, 238, 230), (20, 8), 5)
    pygame.draw.circle(s, (220, 40, 50), (19, 2), 2)
    pygame.draw.circle(s, (220, 40, 50), (22, 2), 2)
    pygame.draw.polygon(s, (240, 170, 40), [(24, 8), (28, 10), (24, 11)])
    pygame.draw.rect(s, (220, 40, 50), (24, 12, 2, 3))
    pygame.draw.rect(s, (12, 12, 16), (19, 6, 7, 2))  # sunglasses
    pygame.draw.rect(s, (12, 12, 16), (16, 6, 3, 1))
    return Sprite(s, 1300)


def make_sprites():
    return {
        "pine": _pine(),
        "round": _round_tree(),
        "bush": _bush(),
        "deer": _deer(),
        "chicken": _chicken(),
        "post": _post(),
        "lamp_l": _lamp(True),
        "lamp_r": _lamp(False),
    }


def make_glow(tint=(1.0, 0.9, 0.55)):
    """Stepped radial glow, meant to be blitted with BLEND_RGB_ADD."""
    s = pygame.Surface((33, 33))
    steps = ((16, 0.06), (11, 0.17), (6, 0.45), (3, 0.85))
    for r, k in steps:
        pygame.draw.circle(s, tuple(int(255 * k * c) for c in tint), (16, 16), r)
    return s


def make_pool():
    """Soft warm patch of headlight on the road, blitted additively."""
    s = pygame.Surface((260, 56))
    bands = ((2, 2, 1), (4, 3, 1), (6, 5, 2), (8, 7, 3), (10, 9, 4), (12, 10, 5))
    for i, col in enumerate(bands):
        grow = 1 - i / len(bands)
        w, h = 260 * grow, 56 * grow
        pygame.draw.ellipse(s, col, ((260 - w) / 2, (56 - h) / 2, w, h))
    return s


def make_sky():
    """Looping sky tile: gradient + moon. Stars are drawn per frame so they can twinkle."""
    tile = pygame.Surface((S.BG_WIDTH, S.HORIZON + 4))
    top, bottom = (2, 4, 14), (26, 34, 66)
    for y in range(tile.get_height()):
        p = min(1.0, y / S.HORIZON) ** 1.5
        pygame.draw.line(
            tile,
            tuple(int(a + (b - a) * p) for a, b in zip(top, bottom)),
            (0, y),
            (S.BG_WIDTH, y),
        )
    halo = _surf(80, 80)
    for r, a in ((36, 14), (28, 20), (20, 30)):
        pygame.draw.circle(halo, (110, 125, 190, a), (40, 40), r)
    tile.blit(halo, (430 - 40, 36 - 40))
    pygame.draw.circle(tile, (226, 230, 212), (430, 36), 11)
    for cx, cy, r in ((426, 32, 3), (434, 40, 2), (433, 30, 2)):
        pygame.draw.circle(tile, (196, 202, 190), (cx, cy), r)
    return tile


def make_stars(rng):
    stars = []
    for _ in range(120):
        stars.append(
            (
                rng.randrange(S.BG_WIDTH),
                rng.randrange(S.HORIZON - 14),
                rng.uniform(0, 6.28),
                rng.uniform(1, 3),
            )
        )
    return stars


def draw_stars(surf, stars, offset, t):
    for x, y, phase, rate in stars:
        sx = int((x - offset) % S.BG_WIDTH)
        if sx >= S.W:
            continue
        b = 0.55 + 0.45 * math.sin(t * rate + phase)
        surf.set_at((sx, y), (int(200 * b), int(210 * b), int(255 * b)))


def _hill_layer(rng, color, base, amps, spike):
    layer = _surf(S.BG_WIDTH, S.HORIZON + 4)
    spikes = [rng.randint(0, spike) for _ in range(S.BG_WIDTH // 4)]
    for x in range(S.BG_WIDTH):
        h = base
        for freq, amp, phase in amps:
            h += amp * math.sin(2 * math.pi * freq * x / S.BG_WIDTH + phase)
        h += spikes[x // 4]
        pygame.draw.line(layer, color, (x, int(S.HORIZON - h)), (x, S.HORIZON + 3))
    return layer


def make_hills(rng):
    far = _hill_layer(
        rng, (12, 18, 36), 18, ((3, 8, 1.3), (7, 5, 0.4), (13, 3, 2.0)), 1
    )
    near = _hill_layer(
        rng, (7, 11, 22), 9, ((5, 5, 2.0), (11, 3, 1.0), (23, 2, 0.5)), 5
    )
    return [(far, S.PARALLAX_FAR), (near, S.PARALLAX_NEAR)]


# --- cockpit ---------------------------------------------------------------

DASH = (6, 6, 10)
DASH_EDGE = (34, 38, 52)


def make_cockpit():
    s = _surf(S.W, S.H)
    # roof strip and A-pillars
    pygame.draw.polygon(
        s, DASH, [(0, 0), (S.W, 0), (S.W, 4), (S.W - 40, 6), (40, 6), (0, 4)]
    )
    pygame.draw.polygon(s, DASH, [(0, 0), (14, 0), (4, 60), (0, 70)])
    pygame.draw.polygon(s, DASH, [(S.W, 0), (S.W - 14, 0), (S.W - 4, 60), (S.W, 70)])
    # rear-view mirror
    pygame.draw.rect(s, DASH, (146, 5, 28, 10))
    pygame.draw.rect(s, (28, 32, 46), (148, 7, 24, 6))
    # dashboard
    top = S.H - 34
    pts = [
        (0, top + 6),
        (60, top + 2),
        (118, top - 4),
        (202, top - 4),
        (260, top + 2),
        (S.W, top + 6),
        (S.W, S.H),
        (0, S.H),
    ]
    pygame.draw.polygon(s, DASH, pts)
    pygame.draw.lines(s, DASH_EDGE, False, pts[:-2], 1)
    # instrument panel
    pygame.draw.rect(s, (10, 13, 18), (128, S.H - 36, 64, 9))
    return s


def draw_gauge(surf, speed_frac, dy):
    """Row of ticks on the instrument panel: green to amber as speed rises."""
    lit = round(speed_frac * 16)
    for i in range(16):
        col = (40, 200, 120) if i < 10 else (230, 170, 50)
        if i >= lit:
            col = (22, 28, 32)
        pygame.draw.rect(surf, col, (132 + i * 4, S.H - 33 + dy, 3, 3))


def draw_wheel(surf, angle, dy):
    cx, cy, rx, ry = S.W // 2, S.H + 10 + dy, 52, 36
    rim, hi = (24, 24, 30), (62, 64, 78)
    pygame.draw.ellipse(surf, rim, (cx - rx, cy - ry, 2 * rx, 2 * ry), 4)
    pygame.draw.arc(
        surf,
        hi,
        (cx - rx, cy - ry, 2 * rx, 2 * ry),
        math.radians(60),
        math.radians(120),
        1,
    )
    # spokes and a 12 o'clock marker that turn with the wheel
    for a in (0.0, math.pi):
        ex, ey = (
            cx + math.cos(a + angle) * (rx - 2),
            cy + math.sin(a + angle) * (ry - 2),
        )
        pygame.draw.line(surf, rim, (cx, cy), (ex, ey), 3)
    mx, my = (
        cx + math.cos(-math.pi / 2 + angle) * rx,
        cy + math.sin(-math.pi / 2 + angle) * ry,
    )
    pygame.draw.rect(surf, (200, 60, 50), (int(mx) - 1, int(my) - 1, 3, 3))
    pygame.draw.circle(surf, (14, 14, 18), (cx, cy), 9)


# --- jump scares (full-screen close-ups) ---------------------------------------


def _deer_scare():
    w, h = S.W, S.H
    s = pygame.Surface((w, h))
    s.fill((6, 2, 4))
    for r, col in ((150, (24, 4, 6)), (110, (38, 6, 8)), (72, (56, 10, 10))):
        pygame.draw.circle(s, col, (w // 2, 90), r)
    cx = w // 2
    bone, shade = (212, 202, 176), (150, 140, 118)
    for sign in (-1, 1):
        beam = [
            (cx + sign * 40, 38),
            (cx + sign * 66, 22),
            (cx + sign * 90, 14),
            (cx + sign * 116, 2),
        ]
        pygame.draw.lines(s, shade, False, [(x, y + 2) for x, y in beam], 6)
        pygame.draw.lines(s, bone, False, beam, 5)
        for (x0, y0), (x1, y1) in (
            ((66, 22), (60, 0)),
            ((90, 14), (96, -6)),
            ((48, 32), (56, 62)),
            ((78, 18), (82, 44)),
        ):
            pygame.draw.line(s, bone, (cx + sign * x0, y0), (cx + sign * x1, y1), 3)
        # ears
        pygame.draw.polygon(
            s,
            (66, 46, 34),
            [(cx + sign * 52, 46), (cx + sign * 96, 36), (cx + sign * 76, 78)],
        )
        pygame.draw.polygon(
            s,
            (120, 66, 66),
            [(cx + sign * 58, 50), (cx + sign * 86, 44), (cx + sign * 74, 70)],
        )
    face = [
        (118, 30),
        (202, 30),
        (218, 70),
        (206, 112),
        (192, 148),
        (178, 172),
        (142, 172),
        (128, 148),
        (114, 112),
        (102, 70),
    ]
    pygame.draw.polygon(s, (84, 58, 40), face)
    pygame.draw.polygon(
        s,
        (60, 40, 28),
        [(118, 30), (136, 30), (130, 110), (126, 148), (114, 112), (102, 70)],
    )
    pygame.draw.polygon(
        s,
        (60, 40, 28),
        [(202, 30), (184, 30), (190, 110), (194, 148), (206, 112), (218, 70)],
    )
    pygame.draw.ellipse(s, (128, 100, 78), (cx - 30, 118, 60, 50))
    # glowing eyes
    for ex in (cx - 32, cx + 32):
        halo = _surf(70, 50)
        pygame.draw.ellipse(halo, (255, 40, 20, 60), (0, 0, 70, 50))
        s.blit(halo, (ex - 35, 70 - 25))
        pygame.draw.ellipse(s, (8, 2, 2), (ex - 17, 60, 34, 22))
        pygame.draw.ellipse(s, (235, 40, 20), (ex - 14, 62, 28, 18))
        pygame.draw.ellipse(s, (255, 210, 70), (ex - 9, 64, 18, 14))
        pygame.draw.rect(s, (0, 0, 0), (ex - 1, 61, 3, 20))  # slit pupil
        pygame.draw.rect(s, (255, 255, 255), (ex - 10, 65, 3, 2))
    # nostrils and a mouth full of teeth
    for nx in (cx - 9, cx + 9):
        pygame.draw.ellipse(s, (20, 10, 10), (nx - 4, 124, 8, 6))
    pygame.draw.polygon(
        s, (30, 4, 8), [(cx - 24, 138), (cx + 24, 138), (cx + 18, 166), (cx - 18, 166)]
    )
    for i in range(7):
        x = cx - 22 + i * 7
        pygame.draw.polygon(s, (240, 236, 220), [(x, 138), (x + 7, 138), (x + 3, 150)])
        pygame.draw.polygon(
            s, (240, 236, 220), [(x + 1, 165), (x + 6, 165), (x + 3, 154)]
        )
    return s


def _chicken_scare():
    w, h = S.W, S.H
    s = pygame.Surface((w, h))
    s.fill((255, 226, 80))
    cx = w // 2
    for i in range(0, 360, 30):  # sunburst
        a0, a1 = math.radians(i), math.radians(i + 15)
        pygame.draw.polygon(
            s,
            (255, 190, 60),
            [
                (cx, 90),
                (cx + math.cos(a0) * 300, 90 + math.sin(a0) * 300),
                (cx + math.cos(a1) * 300, 90 + math.sin(a1) * 300),
            ],
        )
    for x in (cx - 28, cx, cx + 28):
        pygame.draw.circle(s, (220, 40, 50), (x, 28 if x == cx else 34), 16)
    pygame.draw.circle(s, (240, 240, 232), (cx, 92), 70)
    pygame.draw.circle(s, (214, 214, 206), (cx, 100), 70, 4)
    # sunglasses
    pygame.draw.rect(s, (12, 12, 16), (cx - 62, 64, 124, 30), border_radius=8)
    pygame.draw.rect(s, (60, 62, 80), (cx - 56, 68, 20, 4))
    pygame.draw.rect(s, (60, 62, 80), (cx + 12, 68, 20, 4))
    pygame.draw.rect(s, (12, 12, 16), (cx - 6, 66, 12, 5))
    # beak (wide open) and tongue
    pygame.draw.polygon(s, (245, 170, 40), [(cx - 34, 100), (cx + 34, 100), (cx, 128)])
    pygame.draw.polygon(s, (190, 120, 20), [(cx - 30, 134), (cx + 30, 134), (cx, 160)])
    pygame.draw.polygon(s, (120, 20, 30), [(cx - 26, 130), (cx + 26, 130), (cx, 146)])
    pygame.draw.ellipse(s, (230, 70, 90), (cx - 12, 134, 24, 12))
    pygame.draw.ellipse(s, (220, 40, 50), (cx - 8, 150, 16, 26))  # wattle
    return s


def make_jumpscares():
    return {"deer": _deer_scare(), "chicken": _chicken_scare()}


class Art:
    """All generated assets, built once."""

    def __init__(self, seed=0):
        rng = random.Random(seed)
        self.sprites = make_sprites()
        self.glows = {"warm": make_glow(), "red": make_glow((1.0, 0.2, 0.15))}
        self.pool = make_pool()
        self.sky = make_sky()
        self.stars = make_stars(rng)
        self.hills = make_hills(rng)
        self.cockpit = make_cockpit()
        self.jumpscares = make_jumpscares()
