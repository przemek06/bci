"""GhostChallenge: the one object the drive scene talks to.

A ghost appears suddenly and the player must keep their eyes closed for a few seconds
(detected from alpha waves via `app.eyes`, or by holding SPACE in keyboard mode).
Fail to do it before the deadline and the ghost kills the run.

Integration surface (see the hooks in scenes.py):
    ghost = GhostChallenge(app)
    ghost.update(dt, busy)         every frame; `busy` = another event is running
    ghost.draw(surf)               after the world is drawn
    ghost.trigger(busy)            start one now (debug key G)
    ghost.active / ghost.dead / ghost.death_event / ghost.passed_count / ghost.reset()
"""

import random

from ..events import EventType
from .encounter import ACTIVE, GhostConfig, GhostEncounter
from .visuals import GhostVisuals

DEATH_EVENT = EventType(
    "ghost", "scary", "ghost", "THE GHOST PASSES...", "THE GHOST GOT YOU"
)


class GhostChallenge:
    def __init__(self, app, config: GhostConfig | None = None) -> None:
        self.cfg = config or GhostConfig()
        self.eyes = app.eyes
        self.encounter = GhostEncounter(self.cfg)
        self.visuals = GhostVisuals(app)
        # Own RNG so the ghost never disturbs the seeded sequence of the road events.
        self.rng = random.Random(None if app.seed is None else app.seed + 1)
        self.timer = self.rng.uniform(*self.cfg.first_delay)
        self.eyes_state = None
        self.death_event = DEATH_EVENT
        self.app = app

    # --- state used by the scene -------------------------------------------

    @property
    def active(self) -> bool:
        return self.encounter.active

    @property
    def dead(self) -> bool:
        return self.encounter.dead

    @property
    def passed_count(self) -> int:
        return self.encounter.passed_count

    def reset(self) -> None:
        self.encounter.reset()
        self.visuals.reset()

    def trigger(self, busy: bool = False) -> bool:
        """Start a ghost now. Refused while something else is going on or EEG is not ready."""
        if busy or self.active or not self.eyes.ready:
            if not self.eyes.ready:
                self._log("ghost refused: EEG not ready (calibrating or no signal)")
            return False
        self.eyes.begin_challenge()
        self.encounter.start()
        self.visuals.start()
        self._log(
            f"GHOST appeared: keep eyes closed {self.eyes.detector.cfg.hold_s:g}s "
            f"within {self.cfg.deadline_s:g}s"
        )
        return True

    def _log(self, text: str) -> None:
        log = getattr(self.eyes, "log", None)
        if log:
            log(f"[ghost] {text}")

    # --- per frame ------------------------------------------------------------

    def update(self, dt: float, busy: bool = False) -> None:
        state = self.eyes_state = self.eyes.update()
        enc = self.encounter
        was_active = enc.state == ACTIVE
        if enc.state == ACTIVE:
            hold_s = self.eyes.detector.cfg.hold_s
            enc.update(
                dt, min(1.0, state.held_s / hold_s), state.passed, state.signal_ok
            )
        elif enc.active:  # relief / dead
            enc.update(dt)
        elif not busy and self.eyes.ready:
            self.timer -= dt
            if self.timer <= 0:
                self.timer = self.rng.uniform(*self.cfg.interval)
                self.trigger(busy)
        if was_active and enc.state != ACTIVE:
            outcomes = {
                "passed": "SURVIVED: eyes held closed long enough",
                "dead": "DEAD: eyes were not held closed in time",
                "idle": "ghost left: EEG signal lost, no penalty",
            }
            self._log(outcomes.get(enc.state, enc.state))
        self.visuals.update(dt, enc, bool(state.closed))

    def draw(self, surf) -> None:
        hold_s = self.eyes.detector.cfg.hold_s
        self.visuals.draw(surf, self.encounter, hold_s, self.eyes.hint)
        if not self.active and self.eyes.status_text:
            font = self.app.font_small
            img = font.render(self.eyes.status_text, False, (120, 128, 170))
            surf.blit(img, (6, 6))
