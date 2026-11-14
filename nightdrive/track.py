"""Procedural looping track: a list of segments with curve, height and roadside props."""

import math
import random
from dataclasses import dataclass, field

from . import settings as S


@dataclass
class Prop:
    kind: str
    offset: float  # in road half-widths from the centre (+-1 is the road edge)


@dataclass
class Segment:
    index: int
    z1: float
    z2: float
    y1: float
    y2: float
    curve: float
    props: list = field(default_factory=list)
    marking: str | None = None  # "crosswalk" or "crossroads", painted by the renderer


def _ease_in(a, b, p):
    return a + (b - a) * p * p


def _ease_out(a, b, p):
    return a + (b - a) * (1 - (1 - p) ** 2)


def _ease_in_out(a, b, p):
    return a + (b - a) * (-math.cos(p * math.pi) / 2 + 0.5)


class Track:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.segments: list[Segment] = []
        self._marked: list[Segment] = []
        self._build_road()
        self.length = len(self.segments) * S.SEGMENT_LENGTH
        self._place_props()

    def segment_at(self, z):
        return self.segments[int(z // S.SEGMENT_LENGTH) % len(self.segments)]

    def mark(self, z, kind, count):
        """Paint `count` segments around world position `z` as a crosswalk or crossroads."""
        start = int(z // S.SEGMENT_LENGTH) - count // 2
        for i in range(count):
            seg = self.segments[(start + i) % len(self.segments)]
            seg.marking = kind
            self._marked.append(seg)

    def clear_marks(self):
        for seg in self._marked:
            seg.marking = None
        self._marked.clear()

    # --- road shape -------------------------------------------------------

    def _last_y(self):
        return self.segments[-1].y2 if self.segments else 0.0

    def _add_segment(self, curve, y):
        n = len(self.segments)
        L = S.SEGMENT_LENGTH
        self.segments.append(Segment(n, n * L, (n + 1) * L, self._last_y(), y, curve))

    def _add_road(self, enter, hold, leave, curve, height):
        """Ease into `curve`, hold it, ease out. `height` is the rise in segment lengths."""
        start_y = self._last_y()
        end_y = start_y + height * S.SEGMENT_LENGTH
        total = enter + hold + leave
        for n in range(enter):
            self._add_segment(
                _ease_in(0, curve, n / enter), _ease_in_out(start_y, end_y, n / total)
            )
        for n in range(hold):
            self._add_segment(curve, _ease_in_out(start_y, end_y, (enter + n) / total))
        for n in range(leave):
            self._add_segment(
                _ease_out(curve, 0, n / leave),
                _ease_in_out(start_y, end_y, (enter + hold + n) / total),
            )

    def _random_height(self, max_rise=22):
        # Keep the road between 0 and ~4000 units so it never drifts away.
        lo = max(-max_rise, -self._last_y() / S.SEGMENT_LENGTH)
        hi = min(max_rise, (4000 - self._last_y()) / S.SEGMENT_LENGTH)
        return self.rng.uniform(lo, hi)

    def _build_road(self):
        r = self.rng
        self._add_road(10, 30, 10, 0, 0)
        while len(self.segments) < S.TRACK_SEGMENTS:
            kind = r.choice(
                ["straight", "curve", "curve", "hill", "s_curve", "curvy_hill"]
            )
            side = r.choice([-1, 1])
            c = side * r.choice([1.5, 2.5, 4.0])
            if kind == "straight":
                self._add_road(10, r.randint(20, 60), 10, 0, 0)
            elif kind == "curve":
                self._add_road(
                    r.randint(20, 35), r.randint(30, 60), r.randint(20, 35), c, 0
                )
            elif kind == "hill":
                self._add_road(
                    r.randint(20, 30),
                    r.randint(20, 40),
                    r.randint(20, 30),
                    0,
                    self._random_height(),
                )
            elif kind == "s_curve":
                self._add_road(25, 30, 25, c, 0)
                self._add_road(25, 30, 25, -c, 0)
            else:
                self._add_road(25, 35, 25, c, self._random_height())
        # Come back to y=0 so the loop is seamless.
        self._add_road(25, 25, 25, 0, -self._last_y() / S.SEGMENT_LENGTH)
        self._add_segment(0, 0.0)

    # --- roadside props ---------------------------------------------------

    def _place_props(self):
        r = self.rng
        chunk = 150
        lamps_on = False
        density = 0.3
        for seg in self.segments:
            i = seg.index
            if i % chunk == 0:
                lamps_on = r.random() < 0.3
                density = r.uniform(0.1, 0.6)
            if i % 6 == 0:
                seg.props.append(Prop("post", -1.25))
                seg.props.append(Prop("post", 1.25))
            if lamps_on and i % 24 == 0:
                side = -1 if (i // 24) % 2 == 0 else 1
                seg.props.append(Prop("lamp_l" if side < 0 else "lamp_r", side * 1.4))
            if i % 2 == 0:
                for side in (-1, 1):
                    if r.random() < density:
                        kind = r.choice(["pine", "pine", "round", "bush"])
                        lo, hi = (1.5, 2.4) if kind == "bush" else (1.8, 4.5)
                        seg.props.append(Prop(kind, side * r.uniform(lo, hi)))
