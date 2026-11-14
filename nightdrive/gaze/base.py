from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class GazeFeatures:
    """Raw output of a source: a camera-space feature vector (or screen xy for pre-mapped sources)."""

    values: np.ndarray
    quality: float  # 0..1
    t: float  # time.monotonic() of the frame
    skew: float = (
        0.0  # multi-camera: age difference between the oldest and newest camera frame
    )


@dataclass(frozen=True)
class GazePoint:
    """Where the player looks, in canvas coordinates normalised to 0..1 (may fall slightly outside)."""

    x: float
    y: float
    quality: float
    t: float


class GazeSource(Protocol):
    needs_calibration: bool

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def latest(self) -> GazeFeatures | None: ...

    def status(self) -> str: ...
