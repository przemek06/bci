"""Ghost encounter state machine. Pure logic: no drawing, no EEG, time is a parameter.

Flow: IDLE -> ACTIVE (ghost appears, player must keep eyes closed) -> PASSED or DEAD.
The caller says how far the player got (`progress` 0..1, `passed`) every frame;
this class only owns the deadline and the outcome.
"""

from dataclasses import dataclass

IDLE, ACTIVE, PASSED, DEAD = "idle", "active", "passed", "dead"


@dataclass(frozen=True)
class GhostConfig:
    first_delay: tuple[float, float] = (20.0, 35.0)  # seconds until the first ghost
    interval: tuple[float, float] = (35.0, 60.0)  # seconds between ghosts
    deadline_s: float = 10.0  # time allowed to keep the eyes closed for the full hold
    relief_s: float = 2.2  # how long the "ghost passes" message stays
    signal_grace_s: float = (
        4.0  # EEG lost this long during a ghost -> ghost leaves, no death
    )


class GhostEncounter:
    def __init__(self, config: GhostConfig | None = None) -> None:
        self.cfg = config or GhostConfig()
        self.passed_count = 0
        self.reset()

    def reset(self) -> None:
        self.state = IDLE
        self.time_left = 0.0
        self.progress = 0.0
        self.relief_left = 0.0
        self._lost_s = 0.0

    @property
    def active(self) -> bool:
        return self.state != IDLE

    @property
    def dead(self) -> bool:
        return self.state == DEAD

    def start(self) -> bool:
        if self.active:
            return False
        self.state = ACTIVE
        self.time_left = self.cfg.deadline_s
        self.progress = 0.0
        self._lost_s = 0.0
        return True

    def update(
        self,
        dt: float,
        progress: float = 0.0,
        passed: bool = False,
        signal_ok: bool = True,
    ) -> None:
        if self.state == ACTIVE:
            self.progress = progress
            if passed:
                self.state = PASSED
                self.relief_left = self.cfg.relief_s
                self.passed_count += 1
            elif not signal_ok:
                # Cannot verify the eyes: pause the deadline, give up after a grace period
                # rather than killing the player for a hardware hiccup.
                self._lost_s += dt
                if self._lost_s > self.cfg.signal_grace_s:
                    self.reset()
            else:
                self._lost_s = 0.0
                self.time_left -= dt
                if self.time_left <= 0:
                    self.time_left = 0.0
                    self.state = DEAD
        elif self.state == PASSED:
            self.relief_left -= dt
            if self.relief_left <= 0:
                self.reset()
