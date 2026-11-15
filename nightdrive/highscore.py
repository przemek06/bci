"""The best score ever reached, kept between runs in a small JSON file (data/ is git-ignored).

Pure bookkeeping, no drawing. A missing, corrupt or unwritable file never crashes the game: the best
score is then simply 0 (or not saved).
"""

import json
from pathlib import Path

from . import settings as S


class HighScore:
    def __init__(self, path=None) -> None:
        self.path = Path(S.HIGHSCORE_FILE if path is None else path)
        self.best = self._load()

    def _load(self) -> int:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return max(0, int(data["best"]))
        except (OSError, ValueError, KeyError, TypeError):
            return 0

    def submit(self, score: int) -> bool:
        """Call when a run ends. Returns True if `score` beats the best so far (and saves it).

        A tie is not a record, and neither is 0.
        """
        score = int(score)
        if score <= self.best:
            return False
        self.best = score
        self._save()
        return True

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"best": self.best}), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass  # read-only disk, etc.: the best only lives in memory this session
