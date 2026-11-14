import time
from pathlib import Path

import numpy as np

from .. import settings as S
from .base import GazePoint, GazeSource
from .calibration import GazeCalibration


class GazeTracker:
    """Combines a gaze source with a calibration and smooths the result."""

    def __init__(self, source: GazeSource, calibration: GazeCalibration | None = None):
        self.source = source
        self.calibration = calibration
        self._smooth: np.ndarray | None = None
        self._last_t = -1.0
        self._point: GazePoint | None = None

    @property
    def ready(self) -> bool:
        return not self.source.needs_calibration or self.calibration is not None

    def start(self) -> None:
        self.source.start()

    def stop(self) -> None:
        self.source.stop()

    def set_calibration(self, cal: GazeCalibration | None) -> None:
        self.calibration = cal
        self._smooth = None

    def save_calibration(self) -> None:
        if self.calibration is not None:
            self.calibration.save(Path(S.GAZE_CALIBRATION_FILE))

    def update(self, now: float | None = None) -> GazePoint | None:
        """Pull the latest sample; returns the smoothed point or None if the gaze is lost."""
        now = time.monotonic() if now is None else now
        f = self.source.latest()
        if f is None or now - f.t > S.GAZE_STALE or not self.ready:
            self._smooth = None
            self._point = None
            return None
        if f.t != self._last_t:
            self._last_t = f.t
            if self.source.needs_calibration:
                if f.values.shape[0] != self.calibration.n_features:
                    return None
                xy = self.calibration.predict(f.values)[0]
            else:
                xy = f.values[:2]
            if self._smooth is None:
                self._smooth = xy
            else:
                self._smooth = self._smooth + S.GAZE_SMOOTHING * (xy - self._smooth)
            self._point = GazePoint(
                float(self._smooth[0]), float(self._smooth[1]), f.quality, f.t
            )
        return self._point

    @property
    def point(self) -> GazePoint | None:
        return self._point


class GazeMonitor:
    """Turns "looking away from the road for a while" into a discrete distraction trigger."""

    def __init__(self):
        self.away = 0.0
        self.cooldown = 0.0

    @staticmethod
    def is_away(p: GazePoint) -> bool:
        x0, y0, x1, y1 = S.GAZE_ROAD_BOX
        return not (x0 <= p.x <= x1 and y0 <= p.y <= y1)

    def update(self, dt: float, p: GazePoint | None) -> bool:
        self.cooldown = max(0.0, self.cooldown - dt)
        # no data or poor quality must never count as distraction, nor cancel one in progress
        if p is None or p.quality < S.GAZE_MIN_QUALITY:
            return False
        if not self.is_away(p):
            self.away = 0.0
            return False
        self.away += dt
        if self.away >= S.GAZE_AWAY_TIME and self.cooldown == 0.0:
            self.away = 0.0
            self.cooldown = S.GAZE_COOLDOWN
            return True
        return False
