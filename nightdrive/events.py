"""Things that jump out onto the road, and the director that runs event + QTE."""

import random
from dataclasses import dataclass

from . import settings as S
from .qte import SUCCESS, Qte, random_letter

IDLE, QTE, IMPACT, AFTERMATH, DEAD = "idle", "qte", "impact", "aftermath", "dead"


@dataclass(frozen=True)
class EventType:
    name: str
    kind: str  # "scary" or "funny"
    sprite: str
    saved_text: str
    over_text: str  # shown on the game-over screen
    idle_hop: float = 0.0  # how much the creature fidgets while standing on the road


CATALOGUE = [
    EventType("deer", "scary", "deer", "PHEW!", "THE DEER GOT YOU"),
    EventType(
        "chicken",
        "funny",
        "chicken",
        "COOL CHICKEN!",
        "FEATHERS EVERYWHERE!",
        idle_hop=0.04,
    ),
]


class Actor:
    """A creature on the road. It slides sideways towards `target_offset`."""

    def __init__(self, kind, z, offset, target_offset, idle_hop=0.0):
        self.kind = kind
        self.z = z
        self.offset = offset
        self.target_offset = target_offset
        self.idle_hop = idle_hop
        self.facing_left = target_offset < offset

    @property
    def moving(self):
        return abs(self.offset - self.target_offset) > 0.01

    def hop_amount(self):
        return 0.06 if self.moving else self.idle_hop

    def update(self, dt, speed=5.0):
        step = speed * dt
        delta = self.target_offset - self.offset
        self.offset += max(-step, min(step, delta))

    def run_to(self, target):
        self.facing_left = target < self.offset
        self.target_offset = target


class EventDirector:
    def __init__(self, world, rng=None):
        self.world = world
        self.rng = rng or random.Random()
        self.state = IDLE
        self.qte_window = (
            S.QTE_WINDOW
        )  # the scene may lengthen it, e.g. when focus can pass
        self.qte = None
        self.event = None
        self.actor = None
        self.message = None
        self.timer = 0.0
        self.history = []  # one dict per finished event, ready for logging later
        self._last_event = None
        self._last_letter = None

    # --- API used by the game ---------------------------------------------

    @property
    def active(self):
        return self.state != IDLE

    @property
    def saved_count(self):
        return sum(1 for h in self.history if h["result"] == SUCCESS)

    def trigger(self):
        """Start a random event. Returns False if one is already running."""
        if self.active:
            return False
        choices = [e for e in CATALOGUE if e.name != self._last_event] or CATALOGUE
        self.event = self.rng.choice(choices)
        self._last_event = self.event.name
        self._last_letter = random_letter(self.rng, self._last_letter)
        self.qte = Qte(self._last_letter, self.qte_window)

        w = self.world
        reach = max(w.speed, S.CRUISE_SPEED * 0.6) * self.qte_window
        lane = S.LANE_X + self.rng.uniform(-0.1, 0.1)
        side = self.rng.choice([-1, 1])
        self.actor = Actor(
            self.event.sprite,
            (w.position + reach) % w.track.length,
            side * 2.2,
            lane,
            self.event.idle_hop,
        )
        w.actors.append(self.actor)
        self.message = None
        self.state = QTE
        return True

    def press(self, letter):
        if self.state == QTE:
            self.qte.press(letter)

    def pass_by_focus(self):
        """Pass the running quick-time event with attention instead of the key."""
        if self.state == QTE:
            self.qte.succeed_by_focus()

    def reset(self):
        """Drop whatever is going on (e.g. when leaving to the menu)."""
        if self.actor in self.world.actors:
            self.world.actors.remove(self.actor)
        self.world.speed_rate = 0.8
        self.state, self.qte, self.actor, self.message = IDLE, None, None, None

    def update(self, dt):
        if self.actor:
            self.actor.update(dt)

        if self.state == QTE:
            self.qte.update(dt)
            if self.qte.result == SUCCESS:
                self._saved()
            elif self.qte.result:
                self.state = IMPACT
        elif self.state == IMPACT:
            if self._distance_ahead() <= S.IMPACT_DISTANCE:
                self._crash()
        elif self.state == AFTERMATH:
            self.timer -= dt
            if self.timer < 1.0:  # speed back up for the last second
                self.world.cruise = S.CRUISE_SPEED
                self.world.speed_rate = 0.8
            if self.timer <= 0:
                self.reset()

    # --- internals --------------------------------------------------------

    def _distance_ahead(self):
        length = self.world.track.length
        d = (self.actor.z - self.world.position) % length
        return d if d < length / 2 else d - length  # negative once we've passed it

    def _record(self):
        self.history.append(
            {
                "event": self.event.name,
                "letter": self.qte.letter,
                "result": self.qte.result,
                "reaction": self.qte.reaction,
                "input": self.qte.via,
            }
        )

    def _saved(self):
        self._record()
        self.message = self.event.saved_text
        self.timer = S.AFTERMATH_TIME
        self.state = AFTERMATH
        self.world.cruise = S.CRUISE_SPEED * S.BRAKE_SPEED
        self.world.speed_rate = 3.0
        self.actor.run_to(self.actor.offset + (3.5 if self.actor.offset >= 0 else -3.5))

    def _crash(self):
        """The car reached the creature: the run is over."""
        self._record()
        self.state = DEAD
