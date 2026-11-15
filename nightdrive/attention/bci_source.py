"""AttentionSource backed by the `NightDriveBands` LSL stream (tools/gpype_alpha_stream.py)."""

import time
from collections import deque
from collections.abc import Callable

from .base import AttentionState
from .focus_index import FocusConfig, FocusEstimator


class BciAttention:
    mode = "bci"
    needs_calibration = True  # the baseline is recorded from the player's own signal

    def __init__(
        self,
        reader=None,
        config: FocusConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if reader is None:
            from ..lsl.band_reader import BandReader  # lazy: other modes need no pylsl

            reader = BandReader()
        self.reader = reader
        self.estimator = FocusEstimator(config)
        self._clock = clock
        self._started = False  # becomes True once the stream has been seen
        self._bands: tuple[float, ...] | None = None
        self._recent: deque[tuple[float, tuple[float, ...]]] = (
            deque()
        )  # for the log averages
        self.log = None

    @property
    def calibrated(self) -> bool:
        return self.estimator.calibrated

    @property
    def calibration_progress(self) -> float:
        """0..1 while the baseline is being recorded."""
        return self.estimator.calibration_progress(self._clock())

    @property
    def waiting_for_stream(self) -> bool:
        """True until the headset stream has been seen (the baseline cannot start before)."""
        return not self._started

    def start(self) -> None:
        self.reader.start()

    def stop(self) -> None:
        self.reader.stop()

    @property
    def status_text(self) -> str:
        est = self.estimator
        if not self._started:
            return "ATTENTION: WAITING FOR STREAM"
        if not est.calibrated:
            return f"ATTENTION: CALIBRATING {int(est.calibration_progress(self._clock()) * 100)}%"
        return "" if self.reader.connected else "ATTENTION: SIGNAL LOST"

    @property
    def debug_text(self) -> str:
        est, now = self.estimator, self._clock()
        if not self._started:
            return "waiting for the NightDriveBands stream..."
        if not est.calibrated:
            return (
                f"calibrating {int(est.calibration_progress(now) * 100):3d}% "
                f"(play normally, eyes open)  {self._beta_gamma_text(now)}"
            )
        if est.smoothed is None:
            return "NO SIGNAL"
        shares = ""
        if self._bands and sum(self._bands) > 0:
            total = sum(self._bands)
            shares = (
                "  T/A/bL/bM/bH/G "
                + "/".join(f"{100 * b / total:2.0f}" for b in self._bands)
                + "%"
            )
        return (
            f"ratio {est.index:.2f}  med {est.smoothed:.2f}  base {est.baseline:.2f}  "
            f"level {est.level:.2f} ({(est.level - 1) * 100:+.0f}%)  {self._beta_gamma_text(now)}"
            f"{shares}"
        )

    def _beta_gamma_text(self, now: float) -> str:
        """Beta (low + mid + high) and gamma band power (summed over channels): latest value and the mean over
        the smoothing window (the same last few seconds the attention value is smoothed over)."""
        if self._bands is None:
            return ""
        cutoff = now - self.estimator.cfg.smooth_s
        recent = [b for t, b in self._recent if t >= cutoff] or [self._bands]
        out = []
        for name, idx in (("beta", (2, 3, 4)), ("gamma", (5,))):
            raw = sum(self._bands[i] for i in idx)
            avg = sum(sum(b[i] for i in idx) for b in recent) / len(recent)
            out.append(f"{name} raw {raw:.1f} avg {avg:.1f}")
        return "  ".join(out)

    def update(self, ignore: bool = False) -> AttentionState:
        now = self._clock()
        samples = self.reader.drain()
        if not self._started:
            if self.reader.connected:
                self._started = True  # drop anything buffered before play began
            samples = []
        if ignore:
            samples = []
        for s in samples:
            self.estimator.update(s.t, s.value)
            self._bands = s.value
            self._recent.append((s.t, s.value))
        cutoff = now - self.estimator.cfg.smooth_s
        while self._recent and self._recent[0][0] < cutoff:
            self._recent.popleft()
        return self.estimator.update(now)
