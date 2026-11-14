"""Attention index from EEG band powers. Pure logic: no LSL, no drawing.

    attention = (beta + gamma) / alpha      band powers summed over the channels,
                                            beta = low + mid + high beta (13-30 Hz)

Beta (13-30 Hz) and gamma (30-45 Hz) tend to rise when someone is alert and engaged; alpha tends to rise
when they are relaxed, drowsy or mind-wandering. (Theta is not used.) Absolute values differ between people, so
everything is relative to the person's own baseline:

1. The attention value is smoothed with a median over `smooth_s` (blink / jaw bursts do not
   move a median).
2. The baseline is the median of that smoothed value over the first `calibration_s` seconds
   of normal play; afterwards it keeps following the last `baseline_window_s` seconds, so it
   always means "how this person plays normally".
3. `level` = smoothed / baseline. 1.0 = normal, 0.7 = 30% below normal, 1.3 = 30% above.

Time is always passed in.
"""

import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

from .base import AttentionState


@dataclass(frozen=True)
class FocusConfig:
    calibration_s: float = 20.0  # baseline recording, after the settle period
    settle_s: float = 3.0  # ignore the first seconds (filters / FFT warm-up)
    smooth_s: float = (
        2.0  # median window: short, so the level reacts within a second or two
    )
    baseline_window_s: float = 300.0  # the baseline follows the last N seconds of play
    baseline_refresh_s: float = 2.0  # how often the rolling baseline is recomputed
    stale_s: float = 5.0  # no sample for this long -> quality 0
    min_calib_samples: int = 20


def engagement_index(bands: Sequence[float]) -> float | None:
    """`bands` = (theta, alpha, beta_low, beta_mid, beta_high, gamma) powers.
    None if the sample is unusable."""
    _theta, alpha, beta_low, beta_mid, beta_high, gamma = bands  # theta is not used
    num = beta_low + beta_mid + beta_high + gamma  # all beta waves plus gamma
    if alpha <= 0 or num < 0 or not math.isfinite(num / alpha):
        return None
    return num / alpha


class FocusEstimator:
    def __init__(self, config: FocusConfig | None = None) -> None:
        self.cfg = config or FocusConfig()
        self.calibrated = False
        self.baseline = 0.0
        # live values, for logging
        self.index: float | None = None  # latest raw attention value
        self.smoothed: float | None = None
        self.level = 1.0
        self._window: deque[tuple[float, float]] = deque()
        self._cal_start: float | None = None
        self._cal_values: list[tuple[float, float]] = []  # (t, smoothed)
        self._baseline_buf: deque[tuple[float, float]] = (
            deque()
        )  # rolling, after calibration
        self._last_baseline_t = float("-inf")
        self._last_sample_t: float | None = None

    def calibration_progress(self, t: float) -> float:
        if self.calibrated:
            return 1.0
        if self._cal_start is None:
            return 0.0
        elapsed = t - self._cal_start - self.cfg.settle_s
        return max(0.0, min(1.0, elapsed / self.cfg.calibration_s))

    def update(self, t: float, bands: Sequence[float] | None = None) -> AttentionState:
        """Feed one 6-band sample (see engagement_index), or None just to advance time."""
        cfg = self.cfg
        idx = engagement_index(bands) if bands is not None else None
        if idx is not None:
            self.index = idx
            self._last_sample_t = t
            if self._cal_start is None:
                self._cal_start = t
            self._window.append((t, idx))
        while self._window and self._window[0][0] < t - cfg.smooth_s:
            self._window.popleft()

        fresh = (
            self._last_sample_t is not None and t - self._last_sample_t <= cfg.stale_s
        )
        self.smoothed = (
            median(v for _, v in self._window) if self._window and fresh else None
        )

        if not self.calibrated:
            self._calibrate_step(t, idx is not None)
        elif self.smoothed is not None:
            if idx is not None:
                self._follow_baseline(t)
            if self.baseline > 0:
                self.level = self.smoothed / self.baseline

        return AttentionState(
            level=self.level if self.calibrated else 1.0,
            quality=1.0 if fresh else 0.0,
            t=t,
            calibrated=self.calibrated,
        )

    def _calibrate_step(self, t: float, got_sample: bool) -> None:
        cfg = self.cfg
        if self._cal_start is None:
            return
        elapsed = t - self._cal_start
        # Use the smoothed series (same statistic as live) once its window is full.
        if (
            got_sample
            and self.smoothed is not None
            and elapsed >= cfg.settle_s + cfg.smooth_s
        ):
            self._cal_values.append((t, self.smoothed))
        if (
            elapsed >= cfg.settle_s + cfg.calibration_s
            and len(self._cal_values) >= cfg.min_calib_samples
        ):
            self._baseline_buf.extend(self._cal_values)  # seed the rolling baseline
            self._set_baseline()
            self.calibrated = True

    def _follow_baseline(self, t: float) -> None:
        """Baseline = the person's recent normal play (rolling median).

        Over `baseline_window_s` a short attention drop barely moves it, but a start-up
        baseline that was not representative (electrodes settling, short calibration) gets
        corrected.
        """
        cfg = self.cfg
        self._baseline_buf.append((t, self.smoothed))
        while (
            self._baseline_buf and self._baseline_buf[0][0] < t - cfg.baseline_window_s
        ):
            self._baseline_buf.popleft()
        if t - self._last_baseline_t >= cfg.baseline_refresh_s:
            self._set_baseline()
            self._last_baseline_t = t

    def _set_baseline(self) -> None:
        values = [v for _, v in self._baseline_buf]
        if len(values) >= self.cfg.min_calib_samples:
            self.baseline = median(values)
