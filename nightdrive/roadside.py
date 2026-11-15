"""Roadside encounters. Pure logic (no drawing): the scene draws the actors and the HUD hint.

Monster   It stands by the road. While it can see you, its suspicion fills in proportion to how
          bright your headlights are, and drains when they are off. Full suspicion = it gets you.
          Turn the lights off in time, drive past, and you earn a bonus.
Hitchhiker  Stands on the right shoulder. ENTER picks them up (points) while they are close.
          Some are impostors: picking one up loses the run. The tell is a faint glow in their
          eyes (see creature_art._hitchhiker). Skipping anyone costs nothing.

One encounter at a time, and none while a QTE event or the ghost is running (`busy`).
"""

import random

from . import settings as S
from .events import Actor, EventType

IDLE, MONSTER, LUNGE, HITCH, BOARDING, RESULT, DEAD = (
    "idle",
    "monster",
    "lunge",
    "hitch",
    "boarding",
    "result",
    "dead",
)

# What the game-over scene shows (the images and sounds are looked up by name: "monster", "impostor")
MONSTER_DEATH = EventType(
    "monster", "scary", "monster", "IT DIDN'T SEE YOU", "THE MONSTER SAW YOU"
)
IMPOSTOR_DEATH = EventType(
    "impostor",
    "scary",
    "impostor",
    "THANKS FOR THE RIDE!",
    "THE HITCHHIKER WAS NOT HUMAN",
    "NICE CAR...",
)

MONSTER_SIDE = 1.9  # lateral offset of the monster from the road centre
HITCH_SIDE = 1.35  # hitchhikers wait on the right shoulder
PICKUP_BEHIND = 500  # still close enough to open the door when you are this far past


class RoadsideDirector:
    def __init__(self, world, score, sfx, rng=None, seen_hints=None):
        # `seen_hints` outlives a single run (the App keeps it), so retrying never repeats the tutorial
        self.seen_hints = seen_hints if seen_hints is not None else set()
        self._show_hint = False  # does the current encounter show its on-screen hints?
        self.world = world
        self.score = score
        self.sfx = sfx
        self.rng = rng or random.Random()
        self.mode = IDLE
        self.actor = None
        self.impostor = False
        self.suspicion = 0.0  # 0..1, how close the monster is to noticing you
        self.timer = 0.0
        self.message = None
        self.death_event = None
        self.survived_count = 0  # monsters avoided + real passengers delivered
        self._base_offset = MONSTER_SIDE
        self._next_monster = self.rng.uniform(*S.ROADSIDE_FIRST_DELAY)
        self._next_hitch = self.rng.uniform(*S.ROADSIDE_FIRST_DELAY)

    # --- state for the scene ------------------------------------------------

    @property
    def active(self):
        return self.mode != IDLE

    @property
    def dead(self):
        return self.mode == DEAD

    @property
    def can_pick_up(self):
        if self.mode != HITCH:
            return False
        return -PICKUP_BEHIND <= self._ahead(self.actor.z) <= S.HITCH_PICKUP_RANGE

    @property
    def hint(self):
        """(text, kind) for the HUD, or None. kind: warn | calm | info | dim | good.

        The warnings are a one-time tutorial: only the first monster and the first hitchhiker of
        the game show them. Afterwards there is just the creature by the road. The result message
        (points earned) is feedback, so it always shows.
        """
        if self.mode == RESULT:
            return self.message, "good"
        if not self._show_hint:
            return None
        if self.mode == MONSTER:
            if self.world.headlights.light > 0.3:
                return "MONSTER! LIGHTS OFF!", "warn"
            return "STAY DARK...", "calm"
        if self.mode == HITCH:
            if self.can_pick_up:
                return "ENTER - PICK UP", "info"
            return "HITCHHIKER AHEAD", "dim"
        if self.mode == BOARDING:
            return "...", "dim"
        return None

    @property
    def shows_suspicion_bar(self):
        """The suspicion bar is part of the monster tutorial too."""
        return self.mode == MONSTER and self._show_hint

    def _claim_hint(self, kind):
        """True the first time `kind` ("monster" / "hitchhiker") is seen, unless hints are always on."""
        first = kind not in self.seen_hints
        self.seen_hints.add(kind)
        return first or not S.ROADSIDE_HINTS_ONLY_FIRST

    # --- starting encounters ---------------------------------------------------

    def start_monster(self):
        if self.mode != IDLE:
            return False
        side = self.rng.choice([-1, 1])
        self._base_offset = side * MONSTER_SIDE
        self.actor = Actor(
            "monster", self._spawn_z(), self._base_offset, self._base_offset, 0.0, 1.0
        )
        self.world.actors.append(self.actor)
        self.suspicion = 0.0
        self.mode = MONSTER
        self._show_hint = self._claim_hint("monster")
        self.sfx.play("monster_growl")
        return True

    def start_hitchhiker(self, impostor=None):
        """`impostor` None means random (HITCH_IMPOSTOR_CHANCE)."""
        if self.mode != IDLE:
            return False
        self.impostor = (
            self.rng.random() < S.HITCH_IMPOSTOR_CHANCE
            if impostor is None
            else impostor
        )
        self.actor = Actor(
            "impostor" if self.impostor else "hitchhiker",
            self._spawn_z(),
            HITCH_SIDE,
            HITCH_SIDE,
            0.015,  # shifts its weight a little
        )
        self.world.actors.append(self.actor)
        self.mode = HITCH
        self._show_hint = self._claim_hint("hitchhiker")
        return True

    def pick_up(self):
        """ENTER: stop for the hitchhiker. Returns True if the door opened."""
        if not self.can_pick_up:
            return False
        self._remove_actor()
        self.sfx.play("pickup")
        self.world.speed *= 0.35  # a stop-and-go
        self.mode = BOARDING
        self.timer = S.HITCH_BOARDING_TIME
        return True

    def reset(self):
        """Drop whatever is going on (leaving the drive, a new run)."""
        self._remove_actor()
        self.sfx.stop_loop("monster_rumble")
        self.mode = IDLE
        self.suspicion = 0.0
        self.message = None
        self.death_event = None
        self._rearm()

    # --- per frame ---------------------------------------------------------------

    def update(self, dt, busy=False):
        if self.mode == IDLE:
            if busy:
                return
            self._next_monster -= dt
            self._next_hitch -= dt
            if (
                S.HEADLIGHTS_ENABLED and self._next_monster <= 0
            ):  # the monster needs the lights
                self.start_monster()
            elif S.HITCHHIKERS_ENABLED and self._next_hitch <= 0:
                self.start_hitchhiker()
            return
        if self.actor:
            self.actor.update(dt)
        if self.mode == MONSTER:
            self._watch(dt)
        elif self.mode == LUNGE:
            self.timer -= dt
            if self.timer <= 0:
                self._die(MONSTER_DEATH)
        elif self.mode == HITCH:
            if (
                self._ahead(self.actor.z) < -S.HITCH_PASS_DISTANCE
            ):  # drove past: no harm done
                self._remove_actor()
                self.mode = IDLE
                self._rearm()
        elif self.mode == BOARDING:
            self.timer -= dt
            if self.timer <= 0:
                self._boarded()
        elif self.mode == RESULT:
            self.timer -= dt
            if self.timer <= 0:
                self.mode = IDLE
                self.message = None
                self._rearm()

    # --- internals -----------------------------------------------------------------

    def _watch(self, dt):
        ahead = self._ahead(self.actor.z)
        in_sight = -S.MONSTER_SIGHT_BEHIND <= ahead <= S.MONSTER_SIGHT_AHEAD
        light = max(0.0, min(1.0, self.world.headlights.light))
        if in_sight:
            rate = light / S.MONSTER_NOTICE_TIME - (1.0 - light) / S.MONSTER_CALM_TIME
        else:
            rate = -1.0 / S.MONSTER_CALM_TIME
        self.suspicion = max(0.0, min(1.0, self.suspicion + rate * dt))
        self.actor.target_offset = self._base_offset * (
            1.0 - 0.3 * self.suspicion
        )  # it creeps closer
        if self.suspicion > 0:
            self.sfx.loop("monster_rumble", S.GHOST_RUMBLE_VOLUME * self.suspicion)
        else:
            self.sfx.stop_loop("monster_rumble")

        if self.suspicion >= 1.0:  # it saw you
            self.mode = LUNGE
            self.timer = S.MONSTER_LUNGE_TIME
            self.actor.speed = 8.0
            self.actor.run_to(S.LANE_X)
            self.sfx.stop_loop("monster_rumble")
        elif ahead < -S.MONSTER_SIGHT_BEHIND:  # drove past unseen
            self._remove_actor()
            self.sfx.stop_loop("monster_rumble")
            self.suspicion = 0.0
            self.score.add(S.MONSTER_BONUS, "avoided the monster")
            self.survived_count += 1
            self.sfx.play("exhale")
            self._result("IT DIDN'T SEE YOU")

    def _boarded(self):
        if self.impostor:
            self._die(IMPOSTOR_DEATH)
            return
        self.score.add(S.HITCH_BONUS, "hitchhiker")
        self.survived_count += 1
        self.sfx.play("saved")
        self._result(f"+{S.HITCH_BONUS} THANKS FOR THE RIDE")

    def _result(self, text):
        self.message = text
        self.timer = S.ROADSIDE_RESULT_TIME
        self.mode = RESULT

    def _die(self, event):
        self.death_event = event
        self.mode = DEAD

    def _remove_actor(self):
        if self.actor in self.world.actors:
            self.world.actors.remove(self.actor)
        self.actor = None

    def _rearm(self):
        """Roll the time until the next monster and the next hitchhiker."""
        self._next_monster = self.rng.uniform(*S.MONSTER_INTERVAL)
        self._next_hitch = self.rng.uniform(*S.HITCH_INTERVAL)

    def _spawn_z(self):
        return (
            self.world.position + S.ROADSIDE_SPAWN_DISTANCE
        ) % self.world.track.length

    def _ahead(self, z):
        """Distance from the car to world position z; negative once we've passed it."""
        length = self.world.track.length
        d = (z - self.world.position) % length
        return d if d < length / 2 else d - length
