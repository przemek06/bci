"""Focus to pass a quick-time event: instead of pressing the letter, the player can focus hard.

While a quick-time event is running, the attention level (see attention/focus_index.py:
1.0 = this person's normal, 1.4 = 40% above) is watched. The *average* level over the last
`avg_s` seconds is compared with `pass_level`: while the average is at or above it, progress
moves forward; while it is below, progress simply stops (it is not reset, unless `drain` is
set above 0). Once `hold_s` seconds of progress have been collected, the event is passed,
exactly as if the right key had been pressed. So one bad moment costs time, never the progress
already made.

Focusing takes a moment to get into, so for the first `delay_s` seconds of an event nothing counts
and no bars show (the player can settle, like the ghost's relax phase); counting then starts from
zero.

Focusing takes longer than a key press, so when focus can be used (the attention source is
calibrated and has a fresh signal) the event window is `delay_s + qte_window_s` instead of the
usual short one. Otherwise nothing changes: letters only, normal window.

`FocusMeter` is pure logic (time passed in). `FocusPass` is the glue the drive scene uses.
"""

from collections import deque
from dataclasses import dataclass

import pygame

from . import settings as S
from .attention.base import AttentionState

CYAN = (120, 220, 255)
DIM = (120, 128, 170)
SHADOW = (5, 6, 16)


@dataclass(frozen=True)
class FocusPassConfig:
    pass_level: float = 1.0  # level at or above this = focusing hard (40% above normal)
    hold_s: float = 1.5  # ... for this long (in total) to pass
    avg_s: float = 1.0  # the level is averaged over this window before comparing it
    drain: float = 0.0  # while below: 0 = progress holds still; >0 = it drains this many times faster than it fills
    delay_s: float = (
        2.0  # at the start of an event nothing counts and no bars show (time to settle)
    )
    qte_window_s: float = 5.0  # time allowed AFTER the delay when focus can pass it (else the normal window)
    min_quality: float = 0.5  # below this the signal is not trusted
    log_interval_s: float = 1.0


class FocusMeter:
    """Progress towards passing: time collected while the average attention level is high."""

    def __init__(self, config: FocusPassConfig | None = None) -> None:
        self.cfg = config or FocusPassConfig()
        self.held = 0.0
        self.passed = False
        self._t = 0.0
        self._levels: deque[tuple[float, float]] = (
            deque()
        )  # (time, level), last avg_s only

    @property
    def progress(self) -> float:
        return min(1.0, self.held / self.cfg.hold_s)

    @property
    def counting(self) -> bool:
        """False during the first `delay_s` seconds, while the player settles."""
        return self._t >= self.cfg.delay_s

    @property
    def avg_level(self) -> float | None:
        """Average attention level over the last `avg_s` seconds (None before any sample)."""
        if not self._levels:
            return None
        return sum(v for _, v in self._levels) / len(self._levels)

    def reset(self) -> None:
        self.held = 0.0
        self.passed = False
        self._t = 0.0
        self._levels.clear()

    def update(self, dt: float, att: AttentionState) -> bool:
        """Feed the current attention state. Returns True once the player has passed."""
        self._t += dt
        if not self.counting:  # still settling: nothing is recorded and nothing counts
            return self.passed
        usable = att.calibrated and att.quality >= self.cfg.min_quality
        if usable:
            self._levels.append((self._t, att.level))
        while self._levels and self._levels[0][0] < self._t - self.cfg.avg_s:
            self._levels.popleft()
        avg = self.avg_level
        if usable and avg is not None and avg >= self.cfg.pass_level:
            self.held += dt
        elif (
            self.cfg.drain > 0
        ):  # optional: slip = lose progress (default: just stand still)
            self.held = max(0.0, self.held - self.cfg.drain * dt)
        if self.held >= self.cfg.hold_s:
            self.passed = True
        return self.passed


class FocusPass:
    def __init__(self, app, config: FocusPassConfig | None = None) -> None:
        self.app = app
        self.cfg = config or FocusPassConfig()
        self.source = app.attention
        self.meter = FocusMeter(self.cfg)
        self.att: AttentionState | None = None
        self.t = 0.0
        self._qte_active = False
        self._announced = False  # "counting starts now" was logged for this event
        self._last_log = float("-inf")

    @property
    def ready(self) -> bool:
        """Can focus pass a quick-time event right now?"""
        a = self.att
        return a is not None and a.calibrated and a.quality >= self.cfg.min_quality

    def qte_window(self, default: float) -> float:
        """Time limit for a quick-time event that starts now."""
        return self.cfg.delay_s + self.cfg.qte_window_s if self.ready else default

    def update(self, dt: float, qte_active: bool, paused: bool = False) -> bool:
        """Call every drive frame. `paused` (a ghost is on screen) tells the source to ignore
        data, since closed eyes distort the EEG. Returns True when focus passes the event."""
        self.t += dt
        self.att = att = self.source.update(ignore=paused)
        passed = False
        if qte_active and not paused:
            if not self._qte_active:
                self.meter.reset()
                self._announced = False
                self._emit(
                    f"QTE started: {'press the key OR focus' if getattr(self.app, 'qte_keys', True) else 'focus'} "
                    f"(counting starts in {self.cfg.delay_s:g}s; "
                    f"then average level >= {self.cfg.pass_level:g} for {self.cfg.hold_s:g}s in total)"
                    if self.ready
                    else "QTE started: letters only (attention not ready)"
                )
            passed = self.meter.update(dt, att)
            if self.meter.counting and not self._announced:
                self._announced = True
                if self.ready:
                    self._emit("settle time is over: counting the focus now")
            if passed:
                self._emit(f"QTE PASSED BY FOCUS (level {att.level:.2f})")
        elif not qte_active:
            self.meter.reset()
        self._qte_active = qte_active
        self._log_status(att, qte_active)
        return passed

    def _emit(self, text: str) -> None:
        log = getattr(self.source, "log", None)
        if log:
            log(f"[focus] {text}")

    def _log_status(self, att: AttentionState, qte_active: bool) -> None:
        log = getattr(self.source, "log", None)
        if not log or self.t - self._last_log < self.cfg.log_interval_s:
            return
        self._last_log = self.t
        if qte_active and not self.meter.counting:
            state = "QTE focus: settling, not counting yet"
        elif qte_active:
            state = (
                f"QTE focus {self.meter.held:.1f}/{self.cfg.hold_s:g}s, "
                f"avg level {self.meter.avg_level or 0:.2f} (need >= {self.cfg.pass_level:g})"
            )
        else:
            state = "idle"
        log(f"[attention] {self.source.debug_text}  |  {state}")

    @staticmethod
    def _label(surf, font, text: str) -> None:
        img = font.render(text, False, CYAN)
        rect = img.get_rect(center=(S.W // 2, 79))
        surf.blit(font.render(text, False, SHADOW), rect.move(1, 1))
        surf.blit(img, rect)

    def draw(self, surf, keys_enabled: bool = True) -> None:
        """Small focus meter under the quick-time prompt (call while a QTE is running)."""
        if not self.ready:
            return
        font = self.app.font_small
        hint = (
            "OR FOCUS" if keys_enabled else "FOCUS"
        )  # "OR" only while the keys also work
        if (
            not self.meter.counting
        ):  # settling: just the hint, no numbers and no bar yet
            self._label(surf, font, hint)
            return
        avg = self.meter.avg_level
        level = (
            self.att.level if avg is None else avg
        )  # show what the rule actually compares
        self._label(surf, font, f"{hint}  {level:.1f} / {self.cfg.pass_level:.1f}")
        bar = pygame.Rect(0, 0, 64, 5)
        bar.midtop = (S.W // 2, 86)
        pygame.draw.rect(surf, (6, 8, 20), bar)
        fill = int((bar.w - 2) * self.meter.progress)
        pygame.draw.rect(surf, CYAN, (bar.x + 1, bar.y + 1, fill, bar.h - 2))
