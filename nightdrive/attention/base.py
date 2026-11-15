"""The only thing the game knows about the brain: an `AttentionSource` giving `AttentionState`."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AttentionState:
    level: float  # attention relative to this person's baseline: 1.0 = normal, 0.7 = 30% below
    quality: float  # 0..1, 0 = no fresh signal
    t: float  # game clock (time.monotonic)
    calibrated: bool = True  # False while the baseline is still being recorded


class AttentionSource(Protocol):
    mode: str
    log: object  # callable(str) or None: where the live monitor lines go
    status_text: str  # short message for the HUD / console ("" when fine)
    debug_text: str  # one-line description of the current internals, for the log
    needs_calibration: (
        bool  # True if the player must sit through a baseline recording first
    )
    calibrated: (
        bool  # True once there is a baseline (sources that need none are always True)
    )

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def update(self, ignore: bool = False) -> AttentionState:
        """Call every frame. `ignore=True` discards incoming data (e.g. while eyes are closed)."""
        ...
