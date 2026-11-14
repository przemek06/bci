"""The run's score. For now it only ticks up with time; later features feed it through `add()`.

Pure logic (no drawing, no pygame): the dashboard reads `display`, see art.draw_score.
"""

from . import settings as S

MAX_DISPLAY = 999_999  # the dashboard shows six digits


class Score:
    def __init__(self, per_second=None):
        self.per_second = S.SCORE_PER_SECOND if per_second is None else per_second
        self.value = 0.0
        self.history = []  # (points, reason) for everything added by `add`, ready for session logs

    def reset(self):
        self.value = 0.0
        self.history.clear()

    def update(self, dt):
        """Called every frame of a drive: the score rises with time."""
        self.value += self.per_second * dt

    def add(self, points, reason=""):
        """Bonus (or penalty, if negative) from something that happened, e.g. a saved QTE."""
        self.value = max(0.0, self.value + points)
        self.history.append((points, reason))

    @property
    def display(self):
        return min(
            MAX_DISPLAY, int(self.value + 1e-6)
        )  # 49.9999999 from float drift shows as 50
