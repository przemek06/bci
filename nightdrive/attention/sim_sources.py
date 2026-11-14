"""Non-BCI attention sources, so the game runs and can be tested without a headset."""

import math
import random
import time
from collections.abc import Callable

from .base import AttentionState


class NullAttention:
    """No attention input: the game behaves exactly as without the feature."""

    mode = "off"
    log = None
    status_text = ""
    debug_text = ""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def update(self, ignore: bool = False) -> AttentionState:
        return AttentionState(
            level=1.0, quality=0.0, t=time.monotonic(), calibrated=False
        )


class RandomAttention:
    """Attention level drifts slowly around 1.0 (an Ornstein-Uhlenbeck random walk)."""

    mode = "random"
    log = None
    status_text = ""

    def __init__(
        self,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
        tau_s: float = 20.0,
        sigma: float = 0.12,
    ) -> None:
        self._rng = rng or random.Random()
        self._clock = clock
        self._tau = tau_s
        self._sigma = sigma
        self._last: float | None = None
        self.level = 1.0

    @property
    def debug_text(self) -> str:
        return f"random walk  level {self.level:.2f}"

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def update(self, ignore: bool = False) -> AttentionState:
        now = self._clock()
        dt = 0.0 if self._last is None else min(now - self._last, 0.25)
        self._last = now
        self.level += (1.0 - self.level) * dt / self._tau
        self.level += self._sigma * math.sqrt(dt) * self._rng.gauss(0, 1)
        self.level = max(0.0, min(2.0, self.level))
        return AttentionState(self.level, 1.0, now, True)


class KeyboardAttention:
    """Hold UP to raise and DOWN to lower the simulated attention level (1.0 = normal); it stays where you leave it."""

    mode = "keyboard"
    log = None
    status_text = ""

    def __init__(
        self,
        direction: Callable[[], int],  # +1 raising, -1 lowering, 0 idle
        clock: Callable[[], float] = time.monotonic,
        rate_per_s: float = 0.3,
    ) -> None:
        self._direction = direction
        self._clock = clock
        self._rate = rate_per_s
        self._last: float | None = None
        self.level = 1.0

    @property
    def debug_text(self) -> str:
        return f"keyboard (UP/DOWN)  level {self.level:.2f}"

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def update(self, ignore: bool = False) -> AttentionState:
        now = self._clock()
        dt = 0.0 if self._last is None else min(now - self._last, 0.25)
        self._last = now
        self.level = max(
            0.0, min(2.0, self.level + self._direction() * self._rate * dt)
        )
        return AttentionState(self.level, 1.0, now, True)
