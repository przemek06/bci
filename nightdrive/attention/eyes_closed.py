"""Eyes-closed detection from relative alpha. Pure logic: no LSL, no drawing.

Closing the eyes makes occipital alpha rise sharply. The detector:

1. is calibrated on a short eyes-open recording (robust median + spread),
   which sets a threshold above the player's own open-eyes level;
2. smooths the live signal with a short moving average;
3. calls the eyes "closed" once the average crosses the threshold, and keeps
   that state until it falls clearly below a lower release level (hysteresis);
4. times how long the eyes stayed closed. Brief dips shorter than `grace_s`
   do not reset the timer, so one noisy window does not fail the player;
5. latches `passed` once the eyes were closed for `hold_s`.

Time is always passed in (`t`, seconds, any monotonic clock).
"""

import math
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class EyesClosedConfig:
    smooth_s: float = 1.0  # moving-average window
    hold_s: float = 2.0  # eyes must stay closed this long to pass
    grace_s: float = 0.5  # dips shorter than this do not reset the hold timer
    stale_s: float = 1.5  # no sample for this long -> signal lost, hold resets
    k_spread: float = 3.0  # threshold = baseline + k * spread ...
    min_rise: float = 0.10  # ... but at least this much above baseline
    release_frac: float = 0.6  # release level, as a fraction of the way to threshold
    max_threshold: float = 0.95
    min_calib_samples: int = 10


@dataclass(frozen=True)
class EyesClosedState:
    calibrated: bool
    signal_ok: bool  # fresh samples are arriving
    score: float  # smoothed relative alpha
    threshold: float
    closed: bool
    held_s: float  # how long the eyes have been closed (0 if open)
    passed: bool  # held for hold_s at some point since reset()


class EyesClosedDetector:
    def __init__(self, config: EyesClosedConfig | None = None) -> None:
        self.cfg = config or EyesClosedConfig()
        self.baseline = 0.0
        self.threshold = 1.0
        self.release = 1.0
        self.calibrated = False
        self._window: deque[tuple[float, float]] = deque()
        self._last_sample_t: float | None = None
        self.reset()

    def calibrate(self, open_eyes_values: Iterable[float]) -> None:
        """Set the threshold from relative-alpha values recorded with eyes open."""
        values = [v for v in open_eyes_values if math.isfinite(v)]
        if len(values) < self.cfg.min_calib_samples:
            raise ValueError(
                f"need at least {self.cfg.min_calib_samples} calibration samples, "
                f"got {len(values)}"
            )
        med = median(values)
        spread = 1.4826 * median(abs(v - med) for v in values)  # robust sigma
        rise = max(self.cfg.k_spread * spread, self.cfg.min_rise)
        self.baseline = med
        self.threshold = min(self.cfg.max_threshold, med + rise)
        self.release = med + self.cfg.release_frac * (self.threshold - med)
        self.calibrated = True
        self._window.clear()
        self._last_sample_t = None
        self.reset()

    def reset(self) -> None:
        """Forget the hold progress (call when a new 'close your eyes' prompt starts)."""
        self._closed = False
        self._closed_since: float | None = None
        self._below_since: float | None = None
        self._passed = False

    def update(self, t: float, value: float | None = None) -> EyesClosedState:
        """Feed one relative-alpha sample (or None just to advance time)."""
        cfg = self.cfg
        if value is not None and math.isfinite(value):
            self._window.append((t, value))
            self._last_sample_t = t
        while self._window and self._window[0][0] < t - cfg.smooth_s:
            self._window.popleft()

        signal_ok = (
            self._last_sample_t is not None and t - self._last_sample_t <= cfg.stale_s
        )
        score = (
            sum(v for _, v in self._window) / len(self._window) if self._window else 0.0
        )

        if not self.calibrated:
            return self._state(t, score, signal_ok)

        if not signal_ok or not self._window:
            # Cannot verify the eyes: drop the hold progress.
            self._closed = False
            self._closed_since = None
            self._below_since = None
        else:
            limit = self.release if self._closed else self.threshold
            if score >= limit:
                self._below_since = None
                if not self._closed:
                    self._closed = True
                    self._closed_since = t
            elif self._closed:
                if self._below_since is None:
                    self._below_since = t
                if t - self._below_since > cfg.grace_s:
                    self._closed = False
                    self._closed_since = None
                    self._below_since = None

        return self._state(t, score, signal_ok)

    def _state(self, t: float, score: float, signal_ok: bool) -> EyesClosedState:
        held = (
            t - self._closed_since
            if self._closed and self._closed_since is not None
            else 0.0
        )
        self._passed = self._passed or (self.calibrated and held >= self.cfg.hold_s)
        return EyesClosedState(
            calibrated=self.calibrated,
            signal_ok=signal_ok,
            score=score,
            threshold=self.threshold,
            closed=self._closed,
            held_s=held,
            passed=self._passed,
        )
