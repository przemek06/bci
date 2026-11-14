"""Focus to pass a quick-time event: instead of pressing the letter, the player can focus hard.

While a quick-time event is running, the attention level (see attention/focus_index.py:
1.0 = this person's normal, 1.4 = 40% above) is watched. If it stays at or above `pass_level`
for `hold_s` seconds, the event is passed, exactly as if the right key had been pressed.

Focusing takes longer than a key press, so when focus can be used (the attention source is
calibrated and has a fresh signal) the event window is `qte_window_s` instead of the usual
short one. Otherwise nothing changes: letters only, normal window.

`FocusMeter` is pure logic (time passed in). `FocusPass` is the glue the drive scene uses.
"""

from dataclasses import dataclass

import pygame

from . import settings as S
from .attention.base import AttentionState

CYAN = (120, 220, 255)
DIM = (120, 128, 170)
SHADOW = (5, 6, 16)


@dataclass(frozen=True)
class FocusPassConfig:
    pass_level: float = 1.4  # level at or above this = focusing hard (40% above normal)
    hold_s: float = 1.0  # ... for this long to pass
    drain: float = (
        2.0  # while below, progress drains this many times faster than it fills
    )
    qte_window_s: float = (
        5.0  # event time limit when focus can pass it (else the normal one)
    )
    min_quality: float = 0.5  # below this the signal is not trusted
    log_interval_s: float = 1.0


class FocusMeter:
    """How long (leaky) the attention level has been high."""

    def __init__(self, config: FocusPassConfig | None = None) -> None:
        self.cfg = config or FocusPassConfig()
        self.held = 0.0
        self.passed = False

    @property
    def progress(self) -> float:
        return min(1.0, self.held / self.cfg.hold_s)

    def reset(self) -> None:
        self.held = 0.0
        self.passed = False

    def update(self, dt: float, att: AttentionState) -> bool:
        """Feed the current attention state. Returns True once the player has passed."""
        usable = att.calibrated and att.quality >= self.cfg.min_quality
        if usable and att.level >= self.cfg.pass_level:
            self.held += dt
        else:
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
        self._last_log = float("-inf")

    @property
    def ready(self) -> bool:
        """Can focus pass a quick-time event right now?"""
        a = self.att
        return a is not None and a.calibrated and a.quality >= self.cfg.min_quality

    def qte_window(self, default: float) -> float:
        """Time limit for a quick-time event that starts now."""
        return self.cfg.qte_window_s if self.ready else default

    def update(self, dt: float, qte_active: bool, paused: bool = False) -> bool:
        """Call every drive frame. `paused` (a ghost is on screen) tells the source to ignore
        data, since closed eyes distort the EEG. Returns True when focus passes the event."""
        self.t += dt
        self.att = att = self.source.update(ignore=paused)
        passed = False
        if qte_active and not paused:
            if not self._qte_active:
                self.meter.reset()
                self._emit(
                    f"QTE started: press the key OR focus (level >= {self.cfg.pass_level:g} "
                    f"for {self.cfg.hold_s:g}s)"
                    if self.ready
                    else "QTE started: letters only (attention not ready)"
                )
            passed = self.meter.update(dt, att)
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
        state = (
            f"QTE focus {self.meter.held:.1f}/{self.cfg.hold_s:g}s "
            f"(need level >= {self.cfg.pass_level:g})"
            if qte_active
            else "idle"
        )
        log(f"[attention] {self.source.debug_text}  |  {state}")

    def draw(self, surf) -> None:
        """Small focus meter under the quick-time prompt (call while a QTE is running)."""
        if not self.ready:
            return
        font = self.app.font_small
        level = self.att.level
        text = f"OR FOCUS  {level:.1f} / {self.cfg.pass_level:.1f}"
        img = font.render(text, False, CYAN)
        rect = img.get_rect(center=(S.W // 2, 79))
        surf.blit(font.render(text, False, SHADOW), rect.move(1, 1))
        surf.blit(img, rect)
        bar = pygame.Rect(0, 0, 64, 5)
        bar.midtop = (S.W // 2, 86)
        pygame.draw.rect(surf, (6, 8, 20), bar)
        fill = int((bar.w - 2) * self.meter.progress)
        pygame.draw.rect(surf, CYAN, (bar.x + 1, bar.y + 1, fill, bar.h - 2))
