"""Background music: a shuffled playlist of quiet tracks that fades and ducks smoothly."""

import random

import pygame

from . import settings as S


class Music:
    def __init__(self, enabled=True, rng=None):
        self.rng = rng or random.Random()
        self.tracks = [
            (S.MUSIC_DIR / f"{name}.mp3", gain) for name, gain in S.MUSIC_PLAYLIST
        ]
        self.tracks = [t for t in self.tracks if t[0].exists()]
        # Without an audio device (or without the files) the game simply stays silent.
        self.ok = bool(enabled and self.tracks and pygame.mixer.get_init())
        self.duck = False  # turned on while a QTE is running
        self.playing = False
        self.level = 0.0  # current smoothed volume
        self.gain = 1.0  # loudness correction of the current track
        self._queue = []
        self._last = None

    @property
    def target(self):
        return S.MUSIC_VOLUME * (S.MUSIC_DUCK if self.duck else 1.0)

    def start(self):
        """Begin (or keep) playing, fading in. Safe to call repeatedly."""
        if self.ok and not self.playing:
            self.playing = True
            self.level = 0.0
            self._next()

    def stop(self):
        """Cut the music dead, e.g. for a jump scare."""
        if self.ok and self.playing:
            self.playing = False
            pygame.mixer.music.stop()

    def update(self, dt):
        if not self.ok or not self.playing:
            return
        rate = 6.0 if self.target < self.level else 0.7  # duck fast, fade in slowly
        self.level += (self.target - self.level) * min(1.0, dt * rate)
        pygame.mixer.music.set_volume(max(0.0, min(1.0, self.level * self.gain)))
        if not pygame.mixer.music.get_busy():
            self._next()

    def _next(self):
        for _ in range(len(self.tracks)):
            if not self._queue:
                self._queue = self.tracks[:]
                self.rng.shuffle(self._queue)
                if len(self._queue) > 1 and self._queue[-1][0] == self._last:
                    self._queue.reverse()  # don't repeat the track we just heard
            path, gain = self._queue.pop()
            try:
                pygame.mixer.music.load(str(path))
                pygame.mixer.music.set_volume(0.0)
                pygame.mixer.music.play()
            except pygame.error as exc:
                print(f"music: cannot play {path.name}: {exc}")
                continue
            self._last, self.gain = path, gain
            return
        self.ok = False  # nothing playable
