"""Procedural art for the extra events: roadside sprites and full-screen jump-scare close-ups."""

import math
import random

import pygame

from . import settings as S
from .art import Sprite, _surf

CX = S.W // 2


# --- roadside sprites (drawn facing right, scaled by the renderer) -------------


def _trump():
    s = _surf(24, 46)
    suit = (28, 32, 56)
    skin = (248, 128, 38)
    for x in (8, 13):
        pygame.draw.rect(s, (22, 24, 38), (x, 32, 4, 13))
    for x in (7, 12):
        pygame.draw.rect(s, (8, 8, 10), (x, 44, 6, 2))
    pygame.draw.polygon(s, suit, [(5, 16), (19, 16), (20, 34), (4, 34)])
    for x in (2, 19):
        pygame.draw.rect(s, suit, (x, 17, 3, 16))
        pygame.draw.rect(s, skin, (x, 33, 3, 3))
    pygame.draw.polygon(s, (240, 240, 244), [(9, 16), (15, 16), (12, 27)])
    pygame.draw.polygon(
        s, (205, 30, 42), [(11, 17), (13, 17), (14, 36), (12, 39), (10, 36)]
    )
    pygame.draw.rect(s, skin, (10, 13, 4, 4))
    pygame.draw.ellipse(s, skin, (6, 3, 12, 13))
    pygame.draw.polygon(
        s,
        (244, 204, 92),
        [(5, 9), (6, 3), (12, 0), (19, 2), (20, 9), (17, 6), (13, 4), (9, 5)],
    )
    pygame.draw.polygon(
        s, (244, 204, 92), [(12, 0), (22, 2), (21, 6), (15, 4)]
    )  # the swoop
    s.set_at((9, 9), (30, 40, 90))
    s.set_at((14, 9), (30, 40, 90))
    pygame.draw.rect(s, (200, 80, 80), (10, 13, 4, 1))
    return Sprite(s, 1800)


def _yeti():
    s = _surf(36, 50)
    fur, shade = (226, 232, 242), (168, 180, 204)
    for x in (9, 19):
        pygame.draw.rect(s, fur, (x, 36, 8, 13))
        pygame.draw.rect(s, shade, (x - 1, 47, 10, 3))
    pygame.draw.ellipse(s, shade, (5, 14, 26, 27))
    pygame.draw.ellipse(s, fur, (6, 13, 24, 25))
    for x in (0, 28):
        pygame.draw.ellipse(s, fur, (x, 16, 8, 28))
        pygame.draw.ellipse(s, shade, (x, 38, 8, 6))
    pygame.draw.ellipse(s, fur, (10, 1, 16, 16))
    pygame.draw.ellipse(s, (58, 68, 92), (13, 6, 10, 9))
    for x in (15, 20):
        pygame.draw.rect(s, (130, 225, 255), (x, 8, 2, 2))
    pygame.draw.rect(s, (30, 10, 16), (16, 12, 4, 2))
    for x in (16, 19):
        s.set_at((x, 13), (255, 255, 255))
    for x, y in ((10, 20), (24, 22), (14, 28), (20, 30), (8, 8), (27, 6)):
        pygame.draw.line(s, shade, (x, y), (x + 1, y + 3))
    return Sprite(s, 2800, (18 / 36, 9 / 50), "ice")


def _scooter_kid():
    s = _surf(28, 34)
    pygame.draw.rect(s, (40, 44, 60), (2, 28, 22, 2))
    for cx in (5, 23):
        pygame.draw.circle(s, (18, 18, 22), (cx, 31), 3)
        pygame.draw.circle(s, (120, 124, 140), (cx, 31), 1)
    pygame.draw.line(s, (150, 156, 170), (23, 28), (21, 14), 2)
    pygame.draw.rect(s, (150, 156, 170), (18, 13, 6, 2))
    pygame.draw.rect(s, (255, 244, 190), (24, 22, 2, 3))  # headlight
    for x in (10, 14):
        pygame.draw.rect(s, (40, 70, 140), (x, 20, 3, 9))
    pygame.draw.rect(s, (232, 110, 40), (9, 10, 9, 11))
    pygame.draw.line(s, (232, 110, 40), (17, 13), (20, 14), 2)
    pygame.draw.circle(s, (240, 190, 150), (13, 6), 4)
    pygame.draw.ellipse(s, (250, 212, 40), (8, 0, 11, 7))
    return Sprite(s, 1400, (25 / 28, 23 / 34))


def _truck():
    s = _surf(64, 40)
    pygame.draw.rect(s, (118, 122, 136), (0, 6, 44, 24))
    pygame.draw.rect(s, (90, 94, 108), (0, 6, 44, 3))
    pygame.draw.rect(s, (180, 60, 50), (4, 14, 20, 4))
    pygame.draw.rect(s, (196, 56, 40), (46, 12, 16, 18))
    pygame.draw.polygon(s, (196, 56, 40), [(46, 12), (56, 12), (62, 20), (46, 20)])
    pygame.draw.polygon(
        s, (255, 236, 150), [(53, 14), (58, 14), (61, 19), (53, 19)]
    )  # lit windscreen
    pygame.draw.rect(s, (24, 26, 34), (0, 30, 64, 4))
    pygame.draw.rect(s, (255, 250, 200), (61, 24, 3, 4))
    for cx in (10, 18, 46, 56):
        pygame.draw.circle(s, (14, 14, 18), (cx, 33), 5)
        pygame.draw.circle(s, (130, 134, 150), (cx, 33), 2)
    return Sprite(s, 2800, (62 / 64, 26 / 40))


def _deep_one():
    s = _surf(28, 46)
    skin, belly = (58, 112, 92), (150, 172, 132)
    for x in (8, 15):
        pygame.draw.rect(s, skin, (x, 34, 4, 10))
    for x in (6, 14):
        pygame.draw.ellipse(s, (40, 86, 76), (x, 42, 8, 4))
    pygame.draw.ellipse(s, skin, (5, 16, 18, 23))
    pygame.draw.ellipse(s, belly, (9, 20, 10, 15))
    for x in (1, 23):
        pygame.draw.rect(s, skin, (x, 18, 4, 18))
        pygame.draw.polygon(s, (40, 86, 76), [(x - 2, 36), (x + 6, 36), (x + 2, 41)])
    pygame.draw.polygon(s, (36, 84, 108), [(9, 8), (14, 0), (19, 8)])  # dorsal fin
    pygame.draw.ellipse(s, skin, (6, 5, 16, 14))
    for ex in (10, 18):
        pygame.draw.circle(s, (232, 224, 70), (ex, 10), 3)
        pygame.draw.rect(s, (0, 0, 0), (ex - 1, 10, 3, 1))
    pygame.draw.rect(s, (20, 30, 30), (9, 15, 10, 2))
    for x in range(9, 19, 2):
        s.set_at((x, 15), (240, 240, 220))
    for y in (19, 21):
        pygame.draw.line(s, (30, 70, 60), (6, y), (9, y))
        pygame.draw.line(s, (30, 70, 60), (19, y), (22, y))
    return Sprite(s, 2000, (14 / 28, 10 / 46), "acid")


def _monster():
    """A tall, thin figure by the road. Mostly a silhouette: you find it by its glowing eyes."""
    s = _surf(30, 64)
    body, rim = (10, 10, 16), (40, 42, 62)
    for x in (11, 16):  # long legs
        pygame.draw.rect(s, body, (x, 40, 3, 22))
        pygame.draw.rect(s, body, (x - 1, 61, 5, 3))
    pygame.draw.polygon(
        s, body, [(10, 14), (20, 14), (18, 42), (12, 42)]
    )  # narrow torso
    pygame.draw.line(s, rim, (10, 15), (12, 40), 1)
    for x0, x1 in ((10, 3), (20, 27)):  # arms that reach the knees
        pygame.draw.line(s, body, (x0, 16), (x1, 46), 2)
        for dx in (-1, 0, 1):  # long fingers
            pygame.draw.line(s, body, (x1, 46), (x1 + dx, 54), 1)
    pygame.draw.rect(s, body, (13, 9, 4, 6))  # neck
    pygame.draw.ellipse(s, body, (9, 0, 12, 14))  # long skull
    pygame.draw.line(s, rim, (9, 5), (11, 11), 1)
    for x in (12, 17):
        s.set_at((x, 6), (255, 50, 40))
    for x in range(12, 19):  # a thin pale grin
        s.set_at((x, 10), (190, 190, 180))
    return Sprite(s, 3400, (0.5, 6 / 64), "red")


def _hitchhiker(impostor):
    """A person with a thumb out. The impostor is the same drawing with faintly glowing eyes."""
    s = _surf(22, 44)
    for x in (7, 12):  # jeans and shoes
        pygame.draw.rect(s, (40, 58, 98), (x, 28, 3, 14))
        pygame.draw.rect(s, (20, 20, 26), (x - 1, 41, 5, 3))
    pygame.draw.rect(s, (122, 82, 42), (3, 13, 5, 14))  # backpack
    pygame.draw.rect(s, (92, 112, 146), (6, 13, 10, 16))  # hoodie
    pygame.draw.rect(s, (92, 112, 146), (4, 16, 3, 12))  # arm down
    pygame.draw.line(s, (92, 112, 146), (15, 15), (19, 8), 3)  # arm out, thumb up
    pygame.draw.rect(s, (224, 180, 150), (18, 4, 2, 4))
    pygame.draw.circle(s, (224, 180, 150), (11, 8), 4)  # head
    pygame.draw.polygon(s, (200, 62, 62), [(7, 7), (8, 2), (14, 2), (15, 7)])  # beanie
    eyes = (236, 236, 110) if impostor else (30, 30, 40)
    for x in (9, 13):
        s.set_at((x, 8), eyes)
    if not impostor:
        return Sprite(s, 1800)
    # a big-ish, bright glow that stays visible from afar: this is the tell
    return Sprite(s, 1800, (0.5, 8 / 44), "acid", glow_scale=0.34, glow_floor=0.8)


def make_sprites():
    return {
        "trump": _trump(),
        "yeti": _yeti(),
        "scooter": _scooter_kid(),
        "truck": _truck(),
        "deep_one": _deep_one(),
        "monster": _monster(),
        "hitchhiker": _hitchhiker(False),
        "impostor": _hitchhiker(True),
    }


# --- jump-scare close-ups (full 320x180 screens) -------------------------------


def _glow(surf, pos, radius, color):
    """Additive soft glow made of a few stepped circles."""
    layer = pygame.Surface((radius * 2, radius * 2))
    for i in range(4):
        r = int(radius * (1 - i / 4))
        k = (i + 1) / 4 * 0.5
        pygame.draw.circle(layer, tuple(int(c * k) for c in color), (radius, radius), r)
    surf.blit(
        layer, (pos[0] - radius, pos[1] - radius), special_flags=pygame.BLEND_RGB_ADD
    )


def _flag(s):
    """US flag filling the screen: 13 stripes, canton over the top 7, 50 stars."""
    stripe = [round(i * S.H / 13) for i in range(14)]
    for i in range(13):
        col = (178, 34, 52) if i % 2 == 0 else (244, 244, 248)
        pygame.draw.rect(s, col, (0, stripe[i], S.W, stripe[i + 1] - stripe[i]))
    canton_w, canton_h = round(0.76 * S.H), stripe[7]
    pygame.draw.rect(s, (40, 52, 130), (0, 0, canton_w, canton_h))
    for row in range(9):
        cols = 6 if row % 2 == 0 else 5
        for c in range(cols):
            x = 10 + c * 22 + (0 if cols == 6 else 11)
            y = 8 + row * 10
            pygame.draw.rect(s, (255, 255, 255), (x, y, 3, 3))


def _trump_scare():
    s = pygame.Surface((S.W, S.H))
    _flag(s)
    skin, shade = (248, 128, 38), (222, 100, 24)
    pygame.draw.polygon(
        s, (24, 28, 54), [(36, 180), (64, 148), (256, 148), (284, 180)]
    )  # suit
    pygame.draw.polygon(s, (244, 244, 248), [(132, 148), (188, 148), (160, 180)])
    pygame.draw.polygon(
        s, (205, 30, 42), [(151, 150), (169, 150), (173, 180), (147, 180)]
    )
    pygame.draw.rect(s, shade, (132, 128, 56, 24))  # blocky neck
    pygame.draw.rect(s, skin, (94, 74, 12, 30))  # ears
    pygame.draw.rect(s, skin, (214, 74, 12, 30))
    pygame.draw.rect(
        s, skin, (104, 28, 112, 124), border_radius=10
    )  # a very square head
    pygame.draw.rect(s, shade, (104, 132, 112, 20), border_radius=8)  # heavy jaw
    gold = (248, 208, 92)
    pygame.draw.polygon(
        s,
        gold,
        [
            (98, 66),
            (98, 34),
            (112, 10),
            (160, 2),
            (214, 10),
            (222, 36),
            (222, 66),
            (210, 50),
            (160, 38),
            (112, 50),
        ],
    )
    pygame.draw.polygon(
        s, gold, [(150, 2), (252, 14), (244, 36), (190, 24)]
    )  # the swoop
    pygame.draw.polygon(
        s, (224, 176, 70), [(112, 50), (160, 38), (210, 50), (190, 46), (140, 52)]
    )
    for ex in (126, 170):  # small, squinting eyes
        pygame.draw.rect(s, (255, 255, 255), (ex, 80, 26, 9))
        pygame.draw.rect(s, (50, 90, 170), (ex + 9, 80, 8, 9))
        pygame.draw.rect(s, (0, 0, 0), (ex + 11, 82, 4, 5))
        pygame.draw.line(
            s, (214, 170, 80), (ex - 2, 72), (ex + 28, 76 if ex < 150 else 68), 4
        )
        pygame.draw.line(s, shade, (ex, 79), (ex + 26, 79), 2)
    pygame.draw.polygon(s, shade, [(154, 90), (166, 90), (172, 112), (148, 112)])
    pygame.draw.rect(s, (110, 20, 30), (126, 120, 68, 24))  # shouting, square mouth
    pygame.draw.rect(s, (250, 250, 244), (130, 120, 60, 7))
    pygame.draw.rect(s, (220, 80, 100), (146, 134, 28, 10))
    pygame.draw.line(s, shade, (122, 118), (198, 118), 2)
    return s


def _yeti_scare():
    s = pygame.Surface((S.W, S.H))
    s.fill((8, 14, 28))
    rng = random.Random(2)
    _glow(s, (CX, 90), 130, (60, 110, 190))
    for _ in range(90):  # blowing snow
        x, y = rng.randrange(S.W), rng.randrange(S.H)
        pygame.draw.line(s, (200, 220, 245), (x, y), (x - 4, y + 2))
    fur, shade = (222, 230, 242), (158, 172, 200)
    pygame.draw.ellipse(s, shade, (50, 4, 220, 190))
    pygame.draw.ellipse(s, fur, (56, 8, 208, 176))
    for _ in range(160):  # fur strokes
        x, y = rng.randrange(60, 260), rng.randrange(10, 180)
        pygame.draw.line(
            s, shade, (x, y), (x + rng.randint(-5, 5), y + rng.randint(6, 12)), 2
        )
    for sign in (-1, 1):  # jagged side tufts
        pygame.draw.polygon(
            s,
            fur,
            [
                (CX + sign * 100, 40),
                (CX + sign * 150, 20),
                (CX + sign * 128, 70),
                (CX + sign * 160, 90),
                (CX + sign * 110, 110),
            ],
        )
    pygame.draw.ellipse(s, (48, 58, 82), (104, 50, 112, 112))
    pygame.draw.polygon(
        s,
        (30, 38, 58),
        [(106, 70), (160, 80), (214, 70), (214, 62), (160, 70), (106, 62)],
    )  # brow
    for ex in (CX - 26, CX + 26):
        _glow(s, (ex, 86), 26, (110, 210, 255))
        pygame.draw.ellipse(s, (16, 30, 44), (ex - 15, 76, 30, 20))
        pygame.draw.ellipse(s, (150, 235, 255), (ex - 12, 78, 24, 16))
        pygame.draw.ellipse(s, (240, 255, 255), (ex - 6, 81, 12, 10))
        pygame.draw.rect(s, (0, 0, 0), (ex - 1, 78, 3, 16))
    for nx in (CX - 8, CX + 8):
        pygame.draw.ellipse(s, (16, 18, 30), (nx - 4, 108, 8, 6))
    pygame.draw.polygon(
        s, (30, 8, 16), [(124, 122), (196, 122), (206, 150), (160, 168), (114, 150)]
    )
    pygame.draw.ellipse(s, (190, 70, 90), (140, 146, 40, 18))
    for i in range(6):
        x = 128 + i * 12
        pygame.draw.polygon(s, (250, 250, 240), [(x, 122), (x + 12, 122), (x + 6, 142)])
    for x in (118, 198):
        pygame.draw.polygon(s, (250, 250, 240), [(x, 150), (x + 6, 150), (x + 3, 128)])
    return s


def _scooter_scare():
    s = pygame.Surface((S.W, S.H))
    s.fill((10, 10, 18))
    _glow(s, (CX, 150), 150, (255, 240, 170))
    for i in range(0, 360, 24):  # blinding headlight rays
        a = math.radians(i)
        pygame.draw.line(
            s,
            (90, 84, 50),
            (CX, 150),
            (CX + math.cos(a) * 320, 150 + math.sin(a) * 320),
            3,
        )
    pygame.draw.circle(s, (255, 252, 220), (CX, 150), 20)
    pygame.draw.rect(s, (60, 64, 80), (50, 150, 220, 8))  # handlebars
    pygame.draw.rect(s, (30, 32, 40), (50, 150, 26, 12))
    pygame.draw.rect(s, (30, 32, 40), (244, 150, 26, 12))
    pygame.draw.polygon(
        s, (232, 110, 40), [(70, 180), (100, 130), (220, 130), (250, 180)]
    )  # hoodie
    pygame.draw.ellipse(s, (240, 190, 150), (104, 24, 112, 116))
    pygame.draw.polygon(
        s,
        (250, 212, 40),
        [
            (98, 70),
            (104, 20),
            (160, 2),
            (216, 20),
            (222, 70),
            (200, 50),
            (160, 44),
            (120, 50),
        ],
    )
    pygame.draw.rect(s, (220, 160, 20), (98, 62, 124, 6))  # helmet rim
    for ex in (134, 186):  # furious eyes
        pygame.draw.ellipse(s, (255, 255, 255), (ex - 14, 78, 28, 22))
        pygame.draw.circle(s, (30, 30, 40), (ex, 90), 6)
    pygame.draw.line(s, (60, 40, 30), (116, 70), (150, 84), 5)
    pygame.draw.line(s, (60, 40, 30), (204, 70), (170, 84), 5)
    pygame.draw.ellipse(s, (110, 20, 30), (138, 108, 44, 28))
    pygame.draw.rect(s, (255, 255, 255), (144, 108, 32, 6))
    pygame.draw.line(s, (60, 60, 70), (118, 130), (138, 150), 2)  # chin strap
    return s


def _truck_scare():
    s = pygame.Surface((S.W, S.H))
    s.fill((6, 8, 14))
    pygame.draw.rect(s, (28, 30, 38), (0, 150, S.W, 30))
    pygame.draw.rect(s, (22, 26, 36), (48, 8, 224, 150))  # cab front
    pygame.draw.rect(s, (14, 18, 30), (60, 14, 200, 40))  # windscreen
    pygame.draw.polygon(s, (36, 44, 66), [(70, 14), (120, 14), (96, 54), (70, 54)])
    for x in (92, 120, 200, 228):  # roof lights
        pygame.draw.circle(s, (255, 170, 40), (x, 10), 4)
    pygame.draw.rect(s, (70, 74, 86), (100, 66, 120, 64))  # grille
    for y in range(70, 128, 8):
        pygame.draw.rect(s, (150, 154, 168), (104, y, 112, 3))
    pygame.draw.circle(s, (190, 60, 50), (CX, 98), 10)
    pygame.draw.rect(s, (150, 154, 168), (30, 140, 260, 16))  # bumper
    for hx in (62, 258):
        _glow(s, (hx, 100), 90, (255, 245, 180))
        pygame.draw.circle(s, (255, 253, 232), (hx, 100), 22)
        pygame.draw.circle(s, (255, 255, 255), (hx, 100), 12)
    return s


def _deep_one_scare():
    s = pygame.Surface((S.W, S.H))
    s.fill((4, 16, 20))
    rng = random.Random(7)
    _glow(s, (CX, 90), 140, (20, 80, 60))
    skin, dark = (66, 120, 100), (36, 84, 76)
    for x in range(100, 230, 14):  # spiky dorsal crest
        pygame.draw.polygon(
            s, (30, 86, 112), [(x, 40), (x + 7, -6 + abs(x - CX) // 3), (x + 14, 40)]
        )
    pygame.draw.ellipse(s, dark, (70, 18, 180, 168))
    pygame.draw.ellipse(s, skin, (76, 22, 168, 158))
    for _ in range(70):  # mottled scales
        x, y = rng.randrange(84, 236), rng.randrange(30, 170)
        pygame.draw.circle(s, dark, (x, y), rng.randint(2, 4))
    for ex in (CX - 52, CX + 52):
        _glow(s, (ex, 66), 36, (230, 220, 60))
        pygame.draw.circle(s, (20, 40, 30), (ex, 66), 26)
        pygame.draw.circle(s, (236, 226, 70), (ex, 66), 23)
        pygame.draw.rect(s, (0, 0, 0), (ex - 20, 64, 40, 5))  # horizontal slit pupil
        pygame.draw.circle(s, (255, 255, 255), (ex - 9, 56), 3)
    for sign in (-1, 1):  # gills
        for i in range(4):
            pygame.draw.line(
                s,
                (22, 60, 54),
                (CX + sign * 78, 96 + i * 8),
                (CX + sign * 64, 100 + i * 8),
                2,
            )
    pygame.draw.ellipse(s, (14, 24, 26), (CX - 6, 96, 4, 8))
    pygame.draw.polygon(
        s, (20, 8, 14), [(104, 118), (216, 118), (200, 164), (120, 164)]
    )  # wide mouth
    for i in range(10):
        x = 108 + i * 11
        pygame.draw.polygon(s, (236, 240, 220), [(x, 118), (x + 8, 118), (x + 4, 134)])
        pygame.draw.polygon(
            s, (236, 240, 220), [(x + 4, 163), (x + 12, 163), (x + 8, 146)]
        )
    return s


def _monster_scare():
    """It was looking at you the whole time: a huge face at the windscreen, long fingers on the glass."""
    s = pygame.Surface((S.W, S.H))
    s.fill((4, 2, 6))
    rng = random.Random(9)
    pygame.draw.ellipse(s, (8, 8, 14), (60, 6, 200, 210))
    pygame.draw.arc(
        s, (44, 46, 70), (60, 6, 200, 210), math.radians(40), math.radians(140), 3
    )
    for ex in (CX - 40, CX + 40):
        _glow(s, (ex, 76), 44, (255, 40, 30))
        pygame.draw.ellipse(s, (20, 2, 4), (ex - 22, 62, 44, 28))
        pygame.draw.ellipse(s, (240, 40, 30), (ex - 19, 64, 38, 24))
        pygame.draw.ellipse(s, (255, 200, 150), (ex - 10, 68, 20, 16))
        pygame.draw.rect(s, (0, 0, 0), (ex - 1, 63, 3, 26))  # slit pupil
    pygame.draw.polygon(
        s, (22, 2, 6), [(96, 116), (224, 116), (212, 160), (108, 160)]
    )  # a grin that is far too wide
    for i in range(18):
        x = 100 + i * 7
        pygame.draw.polygon(s, (226, 224, 214), [(x, 116), (x + 7, 116), (x + 3, 130)])
        pygame.draw.polygon(
            s, (226, 224, 214), [(x + 1, 159), (x + 6, 159), (x + 3, 146)]
        )
    for side in (-1, 1):  # hands pressed against the glass
        base = 0 if side < 0 else S.W
        for k in range(5):
            y = 70 + k * 16
            pygame.draw.line(
                s,
                (14, 14, 22),
                (base, y + 14),
                (base - side * (50 + rng.randint(0, 24)), y),
                5,
            )
            pygame.draw.circle(
                s, (150, 150, 140), (base - side * (50 + rng.randint(0, 24)), y), 2
            )
    return s


def _impostor_scare():
    """The friendly face smiles. Then the smile keeps going."""
    s = pygame.Surface((S.W, S.H))
    s.fill((16, 14, 22))
    _glow(s, (CX, 80), 120, (40, 70, 20))
    pygame.draw.ellipse(s, (222, 180, 148), (82, 30, 156, 148))
    pygame.draw.polygon(
        s,
        (200, 62, 62),
        [
            (84, 80),
            (92, 22),
            (160, 6),
            (228, 22),
            (236, 80),
            (200, 60),
            (160, 54),
            (120, 60),
        ],
    )  # the beanie
    pygame.draw.rect(s, (170, 40, 40), (84, 72, 152, 10))
    for ex in (CX - 34, CX + 34):
        _glow(s, (ex, 98), 40, (180, 255, 60))
        pygame.draw.circle(s, (240, 244, 120), (ex, 98), 20)
        pygame.draw.circle(s, (20, 30, 10), (ex, 98), 6)
    pygame.draw.arc(
        s, (60, 20, 20), (98, 80, 124, 110), math.radians(200), math.radians(340), 3
    )
    pygame.draw.rect(
        s, (30, 4, 8), (96, 132, 128, 28), border_radius=14
    )  # a grin from ear to ear
    for i in range(20):
        pygame.draw.rect(s, (246, 244, 236), (100 + i * 6, 132, 4, 12))
        pygame.draw.rect(s, (246, 244, 236), (100 + i * 6, 148, 4, 11))
    return s


def make_jumpscares():
    return {
        "trump": _trump_scare(),
        "yeti": _yeti_scare(),
        "scooter": _scooter_scare(),
        "truck": _truck_scare(),
        "deep_one": _deep_one_scare(),
        "monster": _monster_scare(),
        "impostor": _impostor_scare(),
    }
