"""Things that jump out onto the road, and the director that runs event + QTE."""

import random
from dataclasses import dataclass

from . import settings as S
from .qte import SUCCESS, Qte, random_letter

IDLE, QTE, IMPACT, AFTERMATH, DEAD = "idle", "qte", "impact", "aftermath", "dead"


@dataclass(frozen=True)
class EventType:
    name: str  # also the key of the jump-scare image
    kind: str  # "scary" or "funny"
    sprite: str
    saved_text: str
    over_text: str  # shown on the game-over screen
    scare_text: str = ""  # shouted over the jump scare
    idle_hop: float = 0.0  # how much the creature fidgets while standing on the road
    start_offset: float = 2.2  # lateral offset it jumps in from
    slide: float = 5.0  # lateral speed (road half-widths per second)
    crosses: bool = False  # leaves on the far side instead of going back
    marking: str | None = (
        None  # road paint under the event: "crosswalk" or "crossroads"
    )


CATALOGUE = [
    EventType("deer", "scary", "deer", "PHEW!", "THE DEER GOT YOU"),
    EventType(
        "chicken",
        "funny",
        "chicken",
        "COOL CHICKEN!",
        "YOU HIT THE CHICKEN",
        "BAWK!",
        idle_hop=0.04,
    ),
    EventType(
        "trump",
        "funny",
        "trump",
        "TREMENDOUS!",
        "YOU GOT FIRED",
        "YOU'RE FIRED!",
        idle_hop=0.03,
    ),
    EventType("yeti", "scary", "yeti", "PHEW!", "THE YETI GOT YOU"),
    EventType(
        "scooter",
        "funny",
        "scooter",
        "SAFE!",
        "THE SCOOTER KID WAS NOT AMUSED",
        "HEY!!",
        start_offset=3.5,
        slide=6.0,
        crosses=True,
        marking="crosswalk",
    ),
    EventType(
        "truck",
        "scary",
        "truck",
        "CLOSE ONE!",
        "THE TRUCK GOT YOU",
        "HOOONK!",
        start_offset=7.0,
        slide=9.0,
        crosses=True,
        marking="crossroads",
    ),
    EventType(
        "deep_one", "scary", "deep_one", "NOT TODAY, CTHULHU!", "THE DEEP ONES GOT YOU"
    ),
]


class Actor:
    """A creature on the road. It slides sideways towards `target_offset`."""

    def __init__(self, kind, z, offset, target_offset, idle_hop=0.0, speed=5.0):
        self.kind = kind
        self.z = z
        self.offset = offset
        self.target_offset = target_offset
        self.idle_hop = idle_hop
        self.speed = speed
        self.entry_side = (
            1 if offset >= target_offset else -1
        )  # which side it came from
        self.facing_left = target_offset < offset

    @property
    def moving(self):
        return abs(self.offset - self.target_offset) > 0.01

    def hop_amount(self):
        return 0.06 if self.moving else self.idle_hop

    def update(self, dt):
        step = self.speed * dt
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
        self.qte = None
        self.event = None
        self.actor = None  # the creature on the road
        self.message = None
        self.timer = 0.0
        self.mark_z = (
            None  # where road paint was put down, so we can remove it once passed
        )
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

    def trigger(self, event=None):
        """Start an event (random unless one is given). Returns False if one is already running."""
        if self.active:
            return False
        choices = [e for e in CATALOGUE if e.name != self._last_event] or CATALOGUE
        ev = self.event = event or self.rng.choice(choices)
        self._last_event = ev.name
        self._last_letter = random_letter(self.rng, self._last_letter)
        w = self.world
        # Bad headlights mean less time to react, and the creature appears closer too.
        lights = w.headlights
        window = (
            S.QTE_WINDOW_DARK if (not lights.on or lights.flickering) else S.QTE_WINDOW
        )
        self.qte = Qte(self._last_letter, window)
        reach = max(w.speed, S.CRUISE_SPEED * 0.6) * window
        z = (w.position + reach) % w.track.length
        lane = S.LANE_X + self.rng.uniform(-0.1, 0.1)
        side = self.rng.choice([-1, 1])
        self.actor = Actor(
            ev.sprite, z, side * ev.start_offset, lane, ev.idle_hop, ev.slide
        )
        w.actors.append(self.actor)
        if ev.marking:
            w.track.mark(z, ev.marking, 4 if ev.marking == "crosswalk" else 6)
            self.mark_z = z
        self.message = None
        self.state = QTE
        return True

    def press(self, letter):
        if self.state == QTE:
            self.qte.press(letter)

    def reset(self):
        """Drop whatever is going on (e.g. when leaving to the menu)."""
        self._end_event()
        self._clear_marks()

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
            if self._ahead(self.actor.z) <= S.IMPACT_DISTANCE:
                self._crash()
        elif self.state == AFTERMATH:
            self.timer -= dt
            if self.timer < 1.0:  # speed back up for the last second
                self.world.cruise = S.CRUISE_SPEED
                self.world.speed_rate = 0.8
            if self.timer <= 0:
                self._end_event()
        if (
            self.mark_z is not None
            and self.state in (IDLE, AFTERMATH)
            and self._ahead(self.mark_z) < -3000
        ):
            self._clear_marks()

    # --- internals --------------------------------------------------------

    def _ahead(self, z):
        """Distance from the car to world position z; negative once we've passed it."""
        length = self.world.track.length
        d = (z - self.world.position) % length
        return d if d < length / 2 else d - length

    def _record(self):
        self.history.append(
            {
                "event": self.event.name,
                "letter": self.qte.letter,
                "result": self.qte.result,
                "reaction": self.qte.reaction,
                "window": self.qte.window,
            }
        )

    def _saved(self):
        self._record()
        self.message = self.event.saved_text
        self.timer = S.AFTERMATH_TIME
        self.state = AFTERMATH
        self.world.cruise = S.CRUISE_SPEED * S.BRAKE_SPEED
        self.world.speed_rate = 3.0
        a = self.actor
        if self.event.crosses:  # carry on across the road
            a.run_to(-a.entry_side * (abs(a.offset) + 3.5))
        else:  # retreat the way it came
            a.run_to(a.entry_side * (abs(a.offset) + 3.5))

    def _crash(self):
        """The car reached the creature: the run is over."""
        self._record()
        self.state = DEAD

    def _end_event(self):
        if self.actor in self.world.actors:
            self.world.actors.remove(self.actor)
        self.actor = self.qte = self.message = None
        self.world.speed_rate = 0.8
        self.state = IDLE

    def _clear_marks(self):
        self.world.track.clear_marks()
        self.mark_z = None
