"""Pseudo-3D road renderer (segment projection, OutRun style) with night fog."""

import math

import pygame

from . import settings as S


class RoadRenderer:
    def __init__(self, track, art):
        self.track = track
        self.art = art
        self.fog = []  # visibility 0..1 per segment distance
        self.palette = []  # per distance, per colour band: (grass, rumble, road, lane)
        self._glow_cache = {}
        for n in range(S.DRAW_DISTANCE):
            f = 1 / math.exp((n / S.DRAW_DISTANCE) ** 2 * S.FOG_DENSITY)
            self.fog.append(f)
            bands = []
            for band in (0, 1):
                cols = [
                    S.GRASS[band],
                    S.RUMBLE[band],
                    S.ROAD[band],
                    S.LANE if band == 0 else None,
                ]
                bands.append([self._mix(c, f) if c else None for c in cols])
            self.palette.append(bands)

    @staticmethod
    def _mix(color, f):
        return tuple(int(fc + (c - fc) * f) for c, fc in zip(color, S.FOG_COLOR))

    def draw(self, surf, position, player_x, actors=(), t=0.0):
        track, L = self.track, S.SEGMENT_LENGTH
        segs, count = track.segments, len(track.segments)
        base = segs[int(position // L) % count]
        base_pct = (position % L) / L
        cam_y = S.CAMERA_HEIGHT + base.y1 + (base.y2 - base.y1) * base_pct
        cam_x = player_x * S.ROAD_WIDTH
        x, dx = 0.0, -base.curve * base_pct
        max_y = S.H
        hw, hh = S.W / 2, S.H / 2
        poly = pygame.draw.polygon
        visible = []

        for n in range(S.DRAW_DISTANCE):
            idx = base.index + n
            seg = segs[idx % count]
            cam_z = position - (track.length if idx >= count else 0)
            tz1, tz2 = seg.z1 - cam_z, seg.z2 - cam_z
            cx1, cx2 = cam_x - x, cam_x - x - dx
            x += dx
            dx += seg.curve
            if tz1 <= S.CAMERA_DEPTH:
                continue
            s1, s2 = S.CAMERA_DEPTH / tz1, S.CAMERA_DEPTH / tz2
            sx1, sx2 = hw - s1 * cx1 * hw, hw - s2 * cx2 * hw
            sy1 = round(S.HORIZON - s1 * (seg.y1 - cam_y) * hh)
            sy2 = round(S.HORIZON - s2 * (seg.y2 - cam_y) * hh)
            sw1, sw2 = s1 * S.ROAD_WIDTH * hw, s2 * S.ROAD_WIDTH * hw
            visible.append((n, seg, sx1, sy1, s1, max_y, sx2, sy2, tz1))
            if sy2 >= sy1 or sy2 >= max_y:
                continue

            grass, rumble, road, lane = self.palette[n][
                (seg.index // S.RUMBLE_LENGTH) % 2
            ]
            pygame.draw.rect(surf, grass, (0, sy2, S.W, sy1 - sy2 + 1))
            r1, r2 = sw1 / 6, sw2 / 6
            poly(
                surf,
                rumble,
                [
                    (sx1 - sw1 - r1, sy1),
                    (sx1 - sw1, sy1),
                    (sx2 - sw2, sy2),
                    (sx2 - sw2 - r2, sy2),
                ],
            )
            poly(
                surf,
                rumble,
                [
                    (sx1 + sw1 + r1, sy1),
                    (sx1 + sw1, sy1),
                    (sx2 + sw2, sy2),
                    (sx2 + sw2 + r2, sy2),
                ],
            )
            poly(
                surf,
                road,
                [
                    (sx1 - sw1, sy1),
                    (sx1 + sw1, sy1),
                    (sx2 + sw2, sy2),
                    (sx2 - sw2, sy2),
                ],
            )
            if lane:
                l1, l2 = sw1 / 32, sw2 / 32
                poly(
                    surf,
                    lane,
                    [
                        (sx1 - l1, sy1),
                        (sx1 + l1, sy1),
                        (sx2 + l2, sy2),
                        (sx2 - l2, sy2),
                    ],
                )
            max_y = sy1

        # Headlight pool on the road just ahead
        surf.blit(
            self.art.pool,
            (S.W // 2 - 130, S.H - 70),
            special_flags=pygame.BLEND_RGB_ADD,
        )
        self._draw_props(surf, visible, actors, t)

    def _draw_props(self, surf, visible, actors, t):
        count = len(self.track.segments)
        by_seg = {}
        for a in actors:
            by_seg.setdefault(int(a.z // S.SEGMENT_LENGTH) % count, []).append(a)

        for n, seg, sx, sy, scale, clip, sx2, sy2, tz1 in reversed(visible):
            f = self.fog[n]
            for prop in seg.props:
                self._blit_sprite(surf, prop.kind, sx, sy, scale, clip, prop.offset, f)
            for a in by_seg.get(seg.index, ()):
                pct = max(0.0, min(1.0, (a.z - seg.z1) / S.SEGMENT_LENGTH))
                tz = tz1 + pct * S.SEGMENT_LENGTH
                ax = sx + (sx2 - sx) * pct
                ay = sy + (sy2 - sy) * pct
                hop = a.hop_amount() * abs(math.sin(t * 12))
                self._blit_sprite(
                    surf,
                    a.kind,
                    ax,
                    ay,
                    S.CAMERA_DEPTH / tz,
                    clip,
                    a.offset,
                    f,
                    flip=a.facing_left,
                    hop=hop,
                )

    def _blit_sprite(
        self, surf, kind, sx, sy, scale, clip, offset, f, flip=False, hop=0.0
    ):
        hw, hh = S.W / 2, S.H / 2
        spr = self.art.sprites[kind]
        dh = spr.world_h * scale * hh
        dw = dh * spr.aspect
        iw, ih = int(dw), int(dh)
        if iw < 1 or ih < 1 or iw > S.W * 2:
            return
        x = sx + scale * offset * S.ROAD_WIDTH * hw - dw / 2
        y = sy - dh - hop * dh
        if x + dw < 0 or x > S.W:
            return
        visible_h = int(clip - y)  # rows above the hill crest that clips us
        if visible_h <= 0:
            return
        img = pygame.transform.scale(spr.surf, (iw, ih))
        if flip:
            img = pygame.transform.flip(img, True, False)
        shade = int(255 * f)
        img.fill((shade, shade, shade), special_flags=pygame.BLEND_RGB_MULT)
        surf.blit(img, (int(x), int(y)), area=(0, 0, iw, min(ih, visible_h)))
        if spr.glow:
            fx = 1 - spr.glow[0] if flip else spr.glow[0]
            self._draw_glow(
                surf, x + dw * fx, y + dh * spr.glow[1], dh, f, spr.glow_color
            )

    def _draw_glow(self, surf, gx, gy, sprite_h, f, color="warm"):
        radius = max(2, int(sprite_h * 0.16))
        level = int((0.3 + 0.7 * f) * 8)
        key = (radius, level, color)
        glow = self._glow_cache.get(key)
        if glow is None:
            glow = pygame.transform.scale(
                self.art.glows[color], (2 * radius, 2 * radius)
            )
            v = int(255 * level / 8)
            glow.fill((v, v, v), special_flags=pygame.BLEND_RGB_MULT)
            self._glow_cache[key] = glow
        surf.blit(
            glow,
            (int(gx) - radius, int(gy) - radius),
            special_flags=pygame.BLEND_RGB_ADD,
        )
