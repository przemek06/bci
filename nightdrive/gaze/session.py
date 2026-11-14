"""Calibration data collection: pure logic (no drawing), time is passed in."""

import numpy as np

from .. import settings as S
from .base import GazeFeatures
from .calibration import MOVING_TARGETS, TARGETS, GazeCalibration
from .geometry import GeometricCalibration, fit_geometry, usable


class CalibrationSession:
    def __init__(self, targets=None, block: int | None = None):
        """Default: a still-head round, then a round where the user moves their head."""
        self.block = block
        self.targets = list(targets) if targets else TARGETS + MOVING_TARGETS
        self.n_still = len(TARGETS) if targets is None else len(self.targets)
        self.index = 0
        self.t = 0.0
        self._samples: list[np.ndarray] = []
        self._last_t = -1.0
        self._features: list[np.ndarray] = []
        self._labels: list[tuple[float, float]] = []

    @property
    def done(self) -> bool:
        return self.index >= len(self.targets)

    @property
    def target(self) -> tuple[float, float] | None:
        return None if self.done else self.targets[self.index]

    @property
    def moving(self) -> bool:
        return self.index >= self.n_still

    @property
    def sampling(self) -> bool:
        return self.t >= S.CALIB_SETTLE

    @property
    def progress(self) -> float:
        return min(1.0, self.index / len(self.targets))

    def update(self, dt: float, f: GazeFeatures | None) -> None:
        if self.done:
            return
        self.t += dt
        if self.sampling and f is not None and f.t != self._last_t:
            self._last_t = f.t
            if f.quality >= S.GAZE_MIN_QUALITY and f.skew <= S.GAZE_MAX_SKEW:
                self._samples.append(f.values)
        if self.t >= S.CALIB_SETTLE + S.CALIB_SAMPLE:
            if len(self._samples) >= S.CALIB_MIN_SAMPLES:
                self._features.extend(self._samples)
                self._labels.extend([self.targets[self.index]] * len(self._samples))
                self.index += 1
            self.t = 0.0  # next target, or retry this one when too few samples
            self._samples = []

    def fit(self) -> GazeCalibration | GeometricCalibration:
        """Fits the regression and, when L2CS and several head poses are available, the
        geometric model; keeps whichever has the lower cross-validated error."""
        x, y = np.array(self._features), np.array(self._labels)
        reg = GazeCalibration.fit(x, y, block=self.block)
        if self.block and usable(x, self.block):
            try:
                geo = fit_geometry(x, y, self.block)
                if geo.error < reg.error:
                    return geo
            except (ValueError, np.linalg.LinAlgError):
                pass
        return reg
