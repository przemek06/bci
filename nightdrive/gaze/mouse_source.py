import time

import numpy as np

from .base import GazeFeatures


class MouseGazeSource:
    """Non-hardware fallback: the mouse pointer stands in for the gaze (already screen coordinates)."""

    needs_calibration = False

    def __init__(self, get_pos):
        self._get_pos = get_pos  # () -> (x, y) normalised to the canvas

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def latest(self) -> GazeFeatures:
        return GazeFeatures(
            np.array(self._get_pos(), dtype=float), 1.0, time.monotonic()
        )

    def status(self) -> str:
        return "mouse"
