"""Synthetic occipital EEG for trying SSVEP without a headset (the demo, the simulator tool, the tests).

`SimulatedEeg` makes noise + alpha + mains hum, plus, while the simulated player "looks" at a
flickering light, the response of the visual cortex at its frequency (fundamental and 2nd harmonic).
`SimulatedSource` stands in for `lsl.eeg_reader.EegReader`, driven by the wall clock: no network, no
thread.
"""

import time

import numpy as np

from .. import settings as S

SAMPLING_RATE = 250


class SimulatedEeg:
    """Synthetic EEG in microvolts, generated in chunks with continuous phase."""

    def __init__(
        self,
        fs=SAMPLING_RATE,
        channels=3,
        freq=S.HEADLIGHT_BUTTON_HZ,
        seed=0,
        ssvep_uv=3.0,
    ):
        self.fs, self.channels, self.freq, self.ssvep_uv = fs, channels, freq, ssvep_uv
        self.rng = np.random.default_rng(seed)
        self.n = 0  # samples generated so far (keeps the phase continuous)
        self._slow = np.zeros(channels)  # leaky integrator: a 1/f-ish background
        self._gain = 1.0 + 0.15 * self.rng.standard_normal(
            channels
        )  # electrodes differ a little
        self._phase = self.rng.uniform(0, 2 * np.pi, channels)

    def chunk(self, n, attending=False, freq=None):
        """`n` samples, shaped (n, channels). While `attending`, the player is looking at the light
        flickering at `freq` (default: the one given at construction)."""
        f = self.freq if freq is None else freq
        t = (self.n + np.arange(n)) / self.fs
        out = np.empty((n, self.channels))
        for c in range(self.channels):
            white = 8.0 * self.rng.standard_normal(n)
            slow = np.empty(n)
            s = self._slow[c]
            for i in range(
                n
            ):  # leaky integrator, so low frequencies dominate like real EEG
                s = 0.98 * s + 0.6 * white[i]
                slow[i] = s
            self._slow[c] = s
            alpha = 6.0 * np.sin(2 * np.pi * 10.0 * t + self._phase[c])
            mains = 2.0 * np.sin(2 * np.pi * 50.0 * t)
            sig = white * 0.5 + slow * 0.6 + alpha + mains
            if attending:
                sig = sig + self.ssvep_uv * np.sin(2 * np.pi * f * t + self._phase[c])
                sig = sig + 0.5 * self.ssvep_uv * np.sin(
                    2 * np.pi * 2 * f * t + 2 * self._phase[c]
                )
            out[:, c] = sig * self._gain[c]
        self.n += n
        return out


class SimulatedSource:
    """A stand-in for EegReader: `window()` / `connected` / `sampling_rate` / `start()` / `stop()`.

    Call `look_at(hz)` to say which flicker frequency the simulated player is looking at (None = none).
    """

    sampling_rate = SAMPLING_RATE
    connected = True

    def __init__(self, seed=0, strength=4.0, clock=time.monotonic, keep_s=10.0):
        self.eeg = SimulatedEeg(seed=seed, ssvep_uv=strength)
        self._clock = clock
        self._keep = int(keep_s * SAMPLING_RATE)
        self._data = np.zeros((self.eeg.channels, 0))
        self._last = None
        self._owed = 0.0
        self.looking_at = None

    def start(self):
        self._last = self._clock()

    def stop(self):
        pass

    def look_at(self, hz):
        self._advance()  # what happened until now happened under the old gaze
        self.looking_at = hz

    def window(self, seconds):
        self._advance()
        n = round(seconds * SAMPLING_RATE)
        return self._data[:, -n:].copy() if self._data.shape[1] >= n else None

    def _advance(self):
        now = self._clock()
        if self._last is None:
            self._last = now
        self._owed += (now - self._last) * SAMPLING_RATE
        self._last = now
        n = int(self._owed)
        if n <= 0:
            return
        self._owed -= n
        n = min(n, self._keep)  # after a long stall, only the newest second matters
        chunk = self.eeg.chunk(n, self.looking_at is not None, self.looking_at).T
        self._data = np.concatenate([self._data, chunk], axis=1)[:, -self._keep :]
