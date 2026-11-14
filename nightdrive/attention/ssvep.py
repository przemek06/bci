"""SSVEP detection: is the player looking at the flickering button? Pure logic: no LSL, no drawing.

Looking at a light that flickers at f Hz makes the visual cortex oscillate at f Hz (and at its
harmonics 2f, 3f...). That shows as a peak in the occipital EEG spectrum. Two parts:

`ssvep_score_db`   how strong the peak is, as a signal-to-noise ratio in dB: the power at f and 2f
                   against the power of the neighbouring frequencies. Being a ratio, it does not
                   depend on electrode contact or amplifier gain.
`SsvepDetector`    turns a stream of those scores into a decision, once per attention:
                   1. calibrated on a baseline recorded while the flicker is visible but NOT
                      attended (the player looking at the road), which sets a threshold above the
                      player's own baseline (robust median + spread);
                   2. smooths the last few scores;
                   3. fires once the smoothed score has stayed above the threshold for `hold_s`
                      (a glance is not enough, a deliberate look is);
                   4. then disarms: to fire again the player must look away (score below a lower
                      release level) and `cooldown_s` must pass. Staring at the button never
                      toggles the lights back and forth.

Time is always passed in (`t`, seconds, any monotonic clock). Keep the stimulus frequency out of
the 8-12 Hz alpha band: alpha is large and would swamp the measurement (and the eyes-closed ghost
detection uses it).
"""

import math
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from statistics import median

import numpy as np


@dataclass(frozen=True)
class SsvepConfig:
    # --- the measurement ---
    window_s: float = (
        2.0  # seconds of EEG per measurement (longer = steadier but slower)
    )
    step_s: float = 0.25  # how often a new measurement is made
    harmonics: int = 2  # use f, 2f, ... up to this many
    signal_bw: float = (
        0.5  # Hz either side of a target counted as signal (at least one FFT bin)
    )
    noise_gap: float = (
        1.5  # noise bands start this far from the target (at least 3 FFT bins)
    )
    noise_span: float = 3.0  # ... and are this wide, on both sides
    # --- the decision ---
    smooth_n: int = 3  # average this many latest scores
    hold_s: float = 0.5  # the smoothed score must stay above the threshold this long
    cooldown_s: float = 2.0  # minimum time between two detections
    stale_s: float = 1.5  # no score for this long -> signal lost, hold resets
    # --- calibration ---
    calibration_s: float = 15.0  # baseline length (used by the light switch)
    k_spread: float = 3.0  # threshold = baseline median + k * spread ...
    min_rise_db: float = 3.0  # ... but at least this far above it,
    min_threshold_db: float = 3.0  # and never below this (about 2x the noise power),
    max_threshold_db: float = 12.0  # nor above this, so a baseline polluted by attention cannot lock the switch
    release_frac: float = (
        0.5  # re-arm level, as a fraction of the way from the baseline to the threshold
    )
    min_calib_scores: int = 10
    # --- choosing between several targets (SsvepSelector) ---
    select_margin_db: float = 1.0  # the best target must beat the runner-up by this much (in dB above threshold)
    release_s: float = (
        0.75  # with no target standing out for this long, nothing is selected any more
    )


def ssvep_score_db(window, fs, freq, cfg: SsvepConfig | None = None) -> float:
    """SNR in dB at `freq` (and its harmonics) of an EEG window shaped (channels, samples)."""
    cfg = cfg or SsvepConfig()
    x = np.atleast_2d(np.asarray(window, dtype=float))
    n = x.shape[1]
    x = (x - x.mean(axis=1, keepdims=True)) * np.hanning(n)
    power = np.abs(np.fft.rfft(x, axis=1)) ** 2
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    df = fs / n
    sig_half = max(cfg.signal_bw, df)
    gap = max(
        cfg.noise_gap, 3 * df
    )  # the Hann window's main lobe is about +-2 bins wide
    signal = 0.0
    noise = 0.0
    for h in range(1, cfg.harmonics + 1):
        f0 = freq * h
        if f0 + gap + cfg.noise_span > fs / 2:
            break  # beyond what the sampling rate can show
        dist = np.abs(freqs - f0)
        s_mask = dist <= sig_half
        n_mask = (dist >= gap) & (dist <= gap + cfg.noise_span)
        if not s_mask.any() or not n_mask.any():
            continue
        signal += float(power[:, s_mask].mean(axis=1).sum())
        noise += float(power[:, n_mask].mean(axis=1).sum())
    if signal <= 0 or noise <= 0:
        return 0.0
    return 10.0 * math.log10(signal / noise)


@dataclass(frozen=True)
class SsvepState:
    calibrated: bool
    signal_ok: bool  # fresh scores are arriving
    score: float  # smoothed score in dB
    threshold: float
    attending: bool  # smoothed score currently above the threshold
    held_s: float  # how long it has been above
    triggered: bool  # True on exactly the update that fired a detection


class SsvepDetector:
    def __init__(self, config: SsvepConfig | None = None) -> None:
        self.cfg = config or SsvepConfig()
        self.baseline = 0.0
        self.threshold = self.cfg.max_threshold_db
        self.release = self.cfg.max_threshold_db
        self.calibrated = False
        self._scores: deque[float] = deque(maxlen=max(1, self.cfg.smooth_n))
        self._last_t: float | None = None
        self.reset()

    def calibrate(self, baseline_scores: Iterable[float]) -> None:
        """Set the threshold from scores recorded with the flicker visible but not attended."""
        values = [v for v in baseline_scores if math.isfinite(v)]
        if len(values) < self.cfg.min_calib_scores:
            raise ValueError(
                f"need at least {self.cfg.min_calib_scores} baseline scores, got {len(values)}"
            )
        cfg = self.cfg
        med = median(values)
        spread = 1.4826 * median(abs(v - med) for v in values)  # robust sigma
        rise = max(cfg.k_spread * spread, cfg.min_rise_db)
        self.baseline = med
        self.threshold = min(
            cfg.max_threshold_db, max(cfg.min_threshold_db, med + rise)
        )
        self.release = med + cfg.release_frac * (self.threshold - med)
        self.calibrated = True
        self._scores.clear()
        self._last_t = None
        self.reset()

    def reset(self) -> None:
        """Forget the hold progress and re-arm (the switch calls this when a new run starts)."""
        self._above_since: float | None = None
        self._armed = True
        self._fired_at = -math.inf

    def update(self, t: float, score: float | None = None) -> SsvepState:
        """Feed one score (or None just to advance time)."""
        cfg = self.cfg
        if score is not None and math.isfinite(score):
            self._scores.append(score)
            self._last_t = t
        signal_ok = self._last_t is not None and t - self._last_t <= cfg.stale_s
        smooth = sum(self._scores) / len(self._scores) if self._scores else 0.0
        triggered = False

        if not self.calibrated:
            return self._state(t, smooth, signal_ok, False)
        if not signal_ok or not self._scores:
            self._above_since = None  # cannot verify the attention: drop the progress
            return self._state(t, smooth, False, False)

        if smooth >= self.threshold:
            if self._above_since is None:
                self._above_since = t
            if (
                self._armed
                and t - self._above_since >= cfg.hold_s
                and t - self._fired_at >= cfg.cooldown_s
            ):
                triggered = True
                self._armed = False
                self._fired_at = t
        else:
            self._above_since = None
            if smooth < self.release:
                self._armed = True  # looked away: ready for the next one
        return self._state(t, smooth, signal_ok, triggered)

    def _state(
        self, t: float, score: float, signal_ok: bool, triggered: bool
    ) -> SsvepState:
        above = self.calibrated and self._above_since is not None
        return SsvepState(
            calibrated=self.calibrated,
            signal_ok=signal_ok,
            score=score,
            threshold=self.threshold,
            attending=above,
            held_s=t - self._above_since if above else 0.0,
            triggered=triggered,
        )


@dataclass(frozen=True)
class SelectorState:
    calibrated: bool
    signal_ok: bool
    selected: int | None  # the target the player is looking at, or None
    candidate: int | None  # who is currently ahead (may not have held long enough yet)
    scores: tuple[float, ...]  # smoothed score per target, dB
    thresholds: tuple[float, ...]  # per-target detection threshold, dB


class SsvepSelector:
    """Which of several flickering targets is the player looking at? A continuous readout, not a one-shot.

    Each target has its own frequency and so its own score and its own threshold (calibrated from its own
    baseline: the player looking at none of them). A target is a *candidate* while its smoothed score is
    above its threshold, and the candidate with the biggest lead over its threshold wins, provided it beats
    the runner-up by `select_margin_db` (otherwise it is ambiguous and nobody is picked). A candidate that
    holds for `hold_s` becomes the selection and stays until another one holds, or until nobody stands
    out for `release_s`.
    """

    def __init__(self, n_targets: int, config: SsvepConfig | None = None) -> None:
        if n_targets < 1:
            raise ValueError("need at least one target")
        self.n = n_targets
        self.cfg = config or SsvepConfig()
        self.calibrated = False
        self.thresholds = [self.cfg.max_threshold_db] * n_targets
        self._scores = [
            deque(maxlen=max(1, self.cfg.smooth_n)) for _ in range(n_targets)
        ]
        self._last_t: float | None = None
        self.reset()

    def calibrate(self, baseline_scores) -> None:
        """`baseline_scores[i]` are target i's scores recorded while the player looked at none of them."""
        if len(baseline_scores) != self.n:
            raise ValueError(
                f"expected baselines for {self.n} targets, got {len(baseline_scores)}"
            )
        cfg = self.cfg
        thresholds = []
        for scores in baseline_scores:
            values = [v for v in scores if math.isfinite(v)]
            if len(values) < cfg.min_calib_scores:
                raise ValueError(
                    f"need at least {cfg.min_calib_scores} baseline scores per target, got {len(values)}"
                )
            med = median(values)
            spread = 1.4826 * median(abs(v - med) for v in values)
            rise = max(cfg.k_spread * spread, cfg.min_rise_db)
            # no absolute floor here (unlike SsvepDetector): each target idles at its own level, and low
            # frequencies sit on stronger background EEG, so a target is judged against its own baseline
            thresholds.append(min(cfg.max_threshold_db, med + rise))
        self.thresholds = thresholds
        self.calibrated = True
        for q in self._scores:
            q.clear()
        self._last_t = None
        self.reset()

    def reset(self) -> None:
        self._selected: int | None = None
        self._candidate: int | None = None
        self._candidate_since: float | None = None
        self._nobody_since: float | None = None

    def update(self, t: float, scores=None) -> SelectorState:
        """Feed one score per target (or None just to advance time)."""
        cfg = self.cfg
        if scores is not None and len(scores) != self.n:
            raise ValueError(f"expected {self.n} scores, got {len(scores)}")
        if scores is not None and all(math.isfinite(v) for v in scores):
            for q, v in zip(self._scores, scores, strict=True):
                q.append(v)
            self._last_t = t
        signal_ok = self._last_t is not None and t - self._last_t <= cfg.stale_s
        smooth = [sum(q) / len(q) if q else 0.0 for q in self._scores]

        if self.calibrated and signal_ok and all(self._scores):
            self._decide(t, smooth)
        elif self.calibrated and not signal_ok:
            self.reset()  # cannot verify anything: nobody is selected
        return SelectorState(
            calibrated=self.calibrated,
            signal_ok=signal_ok,
            selected=self._selected,
            candidate=self._candidate,
            scores=tuple(smooth),
            thresholds=tuple(self.thresholds),
        )

    def _decide(self, t: float, smooth) -> None:
        cfg = self.cfg
        lead = [s - th for s, th in zip(smooth, self.thresholds, strict=True)]
        order = sorted(range(self.n), key=lambda i: lead[i], reverse=True)
        best = order[0]
        runner_up = lead[order[1]] if self.n > 1 else -math.inf
        winner = (
            best
            if lead[best] >= 0 and lead[best] - runner_up >= cfg.select_margin_db
            else None
        )

        if winner is None:
            self._candidate = self._candidate_since = None
            if self._selected is not None:
                if self._nobody_since is None:
                    self._nobody_since = t
                if t - self._nobody_since >= cfg.release_s:
                    self._selected = None
                    self._nobody_since = None
            return
        self._nobody_since = None
        if winner != self._candidate:
            self._candidate, self._candidate_since = winner, t
        if winner != self._selected and t - self._candidate_since >= cfg.hold_s:
            self._selected = winner
