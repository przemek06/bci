"""Sound for the eyes-closed ghost challenge (see nightdrive/ghost/).

Kept outside the ghost package so that stays self-contained: the drive scene feeds this object the
ghost's state every frame. Pure logic over a `sfx` object (play / play_random / loop / stop_loop), so
it is testable without any audio device.

Timeline:
  appears   a resonant stinger, an eerie bell, a moan; a low drone starts looping
  eyes open rattling chains, creaks and knocks around you, more often as the deadline nears
  eyes shut footsteps circling you in the dark
  passes    the drone stops; a swoosh and a sigh of relief
  gets you  the drone stops (the game-over scene plays the scream)
"""

import random

from . import settings as S

IDLE, ACTIVE, PASSED, DEAD = (
    "idle",
    "active",
    "passed",
    "dead",
)  # same values as ghost/encounter.py

SCARY = {  # what rattles around you with your eyes open: kind -> (variants, weight)
    "chain": (4, 5),
    "creak": (3, 3),
    "knock": (3, 2),
}
STEPS = 4


class GhostAudio:
    def __init__(self, sfx, ghost, rng=None):
        self.sfx = sfx
        self.ghost = ghost
        self.rng = rng or random.Random()
        self.state = IDLE
        self._scary_in = 0.0  # seconds until the next rattle / creak / knock
        self._step_in = 0.0
        self._step_side = 1

    def update(self, dt):
        enc = self.ghost.encounter
        if enc.state != self.state:
            self._changed(self.state, enc.state)
            self.state = enc.state
        if self.state != ACTIVE:
            return
        urgency = 1.0 - max(0.0, min(1.0, enc.time_left / enc.cfg.deadline_s))
        self.sfx.loop("ghost_rumble", S.GHOST_RUMBLE_VOLUME * (0.35 + 0.65 * urgency))
        eyes = self.ghost.eyes_state
        if eyes is not None and eyes.closed:
            self._footsteps(dt, urgency)
        else:
            self._rattles(dt, urgency)

    def stop(self):
        """Silence everything the ghost is making (leaving the drive scene, game over)."""
        self.sfx.stop_loop("ghost_rumble")
        self.state = IDLE

    # --- internals --------------------------------------------------------

    def _changed(self, old, new):
        if new == ACTIVE:
            self.sfx.play("ghost_appear")
            self._scary_in, self._step_in = 1.5, 0.0
            return
        if old == ACTIVE:
            self.sfx.stop_loop("ghost_rumble")
            if new == PASSED:
                self.sfx.play("ghost_relief")

    def _rattles(self, dt, urgency):
        self._scary_in -= dt
        if self._scary_in > 0:
            return
        kinds = list(SCARY)
        kind = self.rng.choices(kinds, weights=[SCARY[k][1] for k in kinds])[0]
        name = f"ghost_{kind}_{self.rng.randint(1, SCARY[kind][0])}"
        self.sfx.play(name, pan=self.rng.uniform(-1.0, 1.0))
        self._scary_in = self.rng.uniform(1.5, 3.0) * (1.0 - 0.5 * urgency)

    def _footsteps(self, dt, urgency):
        self._step_in -= dt
        if self._step_in > 0:
            return
        self._step_side = -self._step_side  # it circles you
        self.sfx.play(
            f"ghost_step_{self.rng.randint(1, STEPS)}", pan=0.8 * self._step_side
        )
        self._step_in = 0.9 - 0.35 * urgency
