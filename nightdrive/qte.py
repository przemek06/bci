"""Quick-time event logic: press the prompted letter (or pass by focus) before time runs out.
No drawing here."""

import random
import string
from dataclasses import dataclass

SUCCESS, WRONG_KEY, TIMEOUT = "success", "wrong_key", "timeout"


def random_letter(rng: random.Random, avoid: str | None = None) -> str:
    return rng.choice([c for c in string.ascii_uppercase if c != avoid])


@dataclass
class Qte:
    letter: str
    window: float
    elapsed: float = 0.0
    result: str | None = None
    reaction: float | None = (
        None  # seconds from prompt to key press (or to the focus pass)
    )
    via: str = "key"  # how it was answered: "key" or "focus"

    @property
    def remaining(self) -> float:
        """Fraction of the time window left, 1.0 -> 0.0."""
        return max(0.0, 1.0 - self.elapsed / self.window)

    def update(self, dt: float):
        if self.result is None:
            self.elapsed += dt
            if self.elapsed >= self.window:
                self.result = TIMEOUT

    def succeed_by_focus(self):
        """The player passed with their attention instead of the key."""
        if self.result is None:
            self.reaction = self.elapsed
            self.via = "focus"
            self.result = SUCCESS

    def press(self, letter: str):
        """A wrong letter fails immediately, so mashing keys doesn't work."""
        if self.result is None:
            self.reaction = self.elapsed
            self.result = SUCCESS if letter.upper() == self.letter else WRONG_KEY
