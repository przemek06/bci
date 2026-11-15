"""SSVEP detection: is the player looking at the flickering button? Pure logic: no LSL, no drawing.

Looking at a light that flickers at f Hz makes the visual cortex oscillate at f Hz (and at its
harmonics 2f, 3f...). That shows as a peak in the occipital EEG spectrum. Two parts:

`ssvep_score_db`   how strong the response at f is, as a dB-like score, by `SsvepConfig.method`:
                   "fbcca" (default: filter-bank canonical correlation with sin/cos references),
                   "cca" (the plain version) or "psd" (power at f and 2f against the neighbouring
                   frequencies). CCA follows the standard SSVEP literature and the open-source
                   SSVEP Analysis Toolbox. All are ratios, so they do not depend on electrode
                   contact or amplifier gain.
`SsvepDetector`    turns a stream of those scores into a decision, once per attention:
                   1. calibrated on a baseline recorded while the flicker is visible but NOT
                      attended (the player looking at the road), which sets a threshold above the
                      player's own baseline (robust median + spread);
                   2. smooths the last few scores (median: a single spike is ignored);
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
    method: str = "fbcca"  # "fbcca" (default), "cca" or "psd" (peak vs neighbouring bands), see ssvep_score_db
    harmonics: int = 2  # use f, 2f, ... up to this many
    max_harmonic_hz: float = 38.0  # CCA references stop below this (the headset stream is band-passed to 40 Hz)
    fb_subbands: int = 4  # FBCCA: number of band-pass sub-bands
    fb_low_hz: float = 5.0  # FBCCA: sub-band k passes fb_low_hz * k up to fb_high_hz (set just below the lowest target)
    fb_high_hz: float = 90.0
    fb_a: float = 1.25  # FBCCA sub-band weight w(n) = n ** -a + b (Chen et al. 2015)
    fb_b: float = 0.25
    signal_bw: float = (
        0.5  # Hz either side of a target counted as signal (at least one FFT bin)
    )
    noise_gap: float = (
        1.5  # noise bands start this far from the target (at least 3 FFT bins)
    )
    noise_span: float = 3.0  # ... and are this wide, on both sides
    # --- the decision ---
    smooth_n: int = (
        3  # median of this many latest scores (one spike, e.g. a blink, never counts)
    )
    hold_s: float = 0.5  # the smoothed score must stay above the threshold this long
    cooldown_s: float = 2.0  # minimum time between two detections
    stale_s: float = 1.5  # no score for this long -> signal lost, hold resets
    # --- calibration ---
    calibration_s: float = 15.0  # baseline length (used by the light switch)
    k_spread: float = 2.5  # threshold = baseline median + k * spread (3.0 missed weak 6-7.5 Hz targets; 2.5 keeps false alarms near 1%) ...
    min_rise_db: float = 3.0  # ... but at least this far above it,
    min_threshold_db: float | None = (
        None  # and never below this, if set (3.0 suited the "psd" measure; the CCA scores need no floor),
    )
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


# --- CCA and filter-bank CCA ---------------------------------------------------------------------------------
# Adapted from the standard method in the SSVEP literature and its open-source implementations (see CLAUDE.md):
# the SSVEP Analysis Toolbox (pikipity/SSVEP-Analysis-Toolbox: `gen_ref_sin`, `canoncorr`, argmax over stimuli)
# and Chen et al. 2015 for the filter bank (weights w(n) = n^-1.25 + 0.25, statistic sum w(n) * rho_n^2).


def reference_signals(freq, fs, n, harmonics):
    """Sine and cosine at `freq` and its harmonics: shape (2 * harmonics, n)."""
    t = np.arange(n) / fs
    rows = []
    for h in range(1, harmonics + 1):
        rows.append(np.sin(2 * np.pi * h * freq * t))
        rows.append(np.cos(2 * np.pi * h * freq * t))
    return np.array(rows)


def canonical_correlations(x, y):
    """Canonical correlations between x (samples, a) and y (samples, b), largest first.

    Orthonormalise each (centred) set, then the singular values of Qx' Qy are the correlations. Rank-deficient
    inputs (e.g. two channels that are identical) are handled by dropping the redundant directions.
    """

    def basis(m):
        m = m - m.mean(axis=0)
        u, sv, _ = np.linalg.svd(m, full_matrices=False)
        return (
            u[:, sv > 1e-10 * max(sv[0], 1e-300)] if sv.size and sv[0] > 0 else u[:, :0]
        )

    qx, qy = basis(np.asarray(x, float)), basis(np.asarray(y, float))
    if qx.shape[1] == 0 or qy.shape[1] == 0:
        return np.zeros(0)
    return np.clip(np.linalg.svd(qx.T @ qy, compute_uv=False), 0.0, 1.0)


def _harmonics_for(freq, cfg: SsvepConfig) -> int:
    """How many harmonics fit below `max_harmonic_hz` (at least the fundamental)."""
    return max(1, min(cfg.harmonics, int(cfg.max_harmonic_hz // freq)))


def cca_rho(window, fs, freq, cfg: SsvepConfig | None = None) -> float:
    """Standard CCA: the largest canonical correlation between the EEG (channels, samples) and sin/cos references."""
    cfg = cfg or SsvepConfig()
    x = np.atleast_2d(np.asarray(window, dtype=float))
    refs = reference_signals(freq, fs, x.shape[1], _harmonics_for(freq, cfg))
    rho = canonical_correlations(x.T, refs.T)
    return float(rho[0]) if rho.size else 0.0


def filter_bank(window, fs, cfg: SsvepConfig):
    """The window band-passed into `fb_subbands` sub-bands [fb_low_hz * k, fb_high_hz] (4th-order Chebyshev, zero phase)."""
    from scipy.signal import cheby1, sosfiltfilt

    x = np.atleast_2d(np.asarray(window, dtype=float))
    high = min(cfg.fb_high_hz, 0.9 * fs / 2)
    bands = []
    for k in range(1, cfg.fb_subbands + 1):
        low = cfg.fb_low_hz * k
        if low >= high * 0.9:
            break
        sos = cheby1(4, 1, [low, high], btype="bandpass", fs=fs, output="sos")
        bands.append(sosfiltfilt(sos, x, axis=1))
    return bands or [x]


def fbcca_stat(window, fs, freq, cfg: SsvepConfig | None = None) -> float:
    """Filter-bank CCA statistic in 0..1: sum_n w(n) rho_n^2 / sum_n w(n), with w(n) = n^-a + b."""
    cfg = cfg or SsvepConfig()
    bands = filter_bank(window, fs, cfg)
    weights = np.array([n**-cfg.fb_a + cfg.fb_b for n in range(1, len(bands) + 1)])
    rhos = np.array([cca_rho(b, fs, freq, cfg) for b in bands])
    return float(np.sum(weights * rhos**2) / np.sum(weights))


def _correlation_to_db(r2) -> float:
    """Map a squared correlation (0..1) to a dB scale, 10 log10(r2 / (1 - r2)): like an SNR, so the same
    calibration (baseline + spread, in dB) applies to every method."""
    r2 = min(max(float(r2), 1e-6), 1.0 - 1e-6)
    return 10.0 * math.log10(r2 / (1.0 - r2))


def ssvep_score_db(window, fs, freq, cfg: SsvepConfig | None = None) -> float:
    """How strongly is there an SSVEP at `freq`, in dB, for an EEG window shaped (channels, samples)?

    cfg.method picks the measure: "psd" (peak against neighbouring frequencies), "cca" (canonical correlation
    with sin/cos references) or "fbcca" (filter-bank CCA). All return a dB-like score that rises with the
    response, so the calibration and decision logic below does not care which one is used.
    """
    cfg = cfg or SsvepConfig()
    if cfg.method == "cca":
        return _correlation_to_db(cca_rho(window, fs, freq, cfg) ** 2)
    if cfg.method == "fbcca":
        return _correlation_to_db(fbcca_stat(window, fs, freq, cfg))
    if cfg.method == "psd":
        return _psd_score_db(window, fs, freq, cfg)
    raise ValueError(f"unknown SSVEP method {cfg.method!r}: use psd, cca or fbcca")


def _psd_score_db(window, fs, freq, cfg: SsvepConfig) -> float:
    """Power-spectrum measure: SNR in dB of the peak at `freq` (and harmonics) against the neighbouring bands."""
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
        floor = -math.inf if cfg.min_threshold_db is None else cfg.min_threshold_db
        self.threshold = min(cfg.max_threshold_db, max(floor, med + rise))
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
            if self._last_t is not None and t - self._last_t > cfg.stale_s:
                self._scores.clear()  # scores from before a gap say nothing about now
            self._scores.append(score)
            self._last_t = t
        signal_ok = self._last_t is not None and t - self._last_t <= cfg.stale_s
        smooth = median(self._scores) if self._scores else 0.0
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
            if self._last_t is not None and t - self._last_t > cfg.stale_s:
                for q in self._scores:
                    q.clear()  # scores from before a gap say nothing about now
            for q, v in zip(self._scores, scores, strict=True):
                q.append(v)
            self._last_t = t
        signal_ok = self._last_t is not None and t - self._last_t <= cfg.stale_s
        smooth = [median(q) if q else 0.0 for q in self._scores]

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
