"""How the player flips the headlights: the dashboard button, behind a small interface.

The button always flickers (see `stimulus_lit`): the flicker is the visual stimulus an SSVEP brain-
computer interface picks up from the occipital EEG. Two implementations:

`ClickLightSwitch`   click the button with the mouse.
`SsvepLightSwitch`   look at the button: the EEG shows the flicker frequency and the lights toggle.
                     (The mouse still works as a fallback.)

A new input only has to subclass `LightSwitch`, return True from `update()` when it decides the player
wants the lights toggled, and set `stimulus_hz` to the frequency it looks for.

Keep the stimulus frequency out of the 8-12 Hz alpha band: the eyes-closed ghost detection uses it.
"""

import math
import time

import pygame

from . import art
from . import settings as S
from .attention.ssvep import SsvepConfig, SsvepDetector, ssvep_score_db


def stimulus_level(now, hz, wave="square"):
    """Brightness 0..1 of a flickering light at time `now` (seconds).

    "square" is on/off (what `stimulus_lit` says); "sine" is a sampled sinusoid of luminance, which works for
    any frequency at a given refresh rate (the standard way to stimulate at e.g. 7.5 or 17 Hz on a 60 Hz screen).
    `hz` <= 0 means steady, fully lit.
    """
    if hz <= 0:
        return 1.0
    if wave == "sine":
        return 0.5 * (1.0 + math.sin(2.0 * math.pi * hz * now))
    return 1.0 if stimulus_lit(now, hz) else 0.0


def stimulus_lit(now, hz):
    """Is the flickering button in its lit half-cycle at time `now` (seconds)? 50% duty square wave.

    `hz` <= 0 means "steady": always lit. At 60 FPS, the frequencies 30, 15, 10, 7.5 and 6 Hz
    (60 / 2k) fit a whole number of frames per half-cycle, which keeps the square wave exact; others (20 Hz is
    1.5 frames per half-cycle) get an uneven duty cycle, so use `stimulus_level` with a sine for those.
    """
    if hz <= 0:
        return True
    return (now * hz * 2) % 2 < 1


class LightSwitch:
    """Decides when the player wants the headlights toggled. Subclass this for a new input."""

    stimulus_hz = (
        S.HEADLIGHT_BUTTON_HZ
    )  # the frequency the dashboard button flickers at
    hover = False  # is the pointer over the button? (only a mouse has one)
    status_text = ""  # a short HUD message while the input is not ready ("" if fine)

    def start(self):
        """Open any stream / device. Called once when the app starts."""

    def stop(self):
        """Close it again. Called once when the app quits."""

    def handle_event(self, event):
        """Offered every pygame event. Return True to toggle the headlights."""
        return False

    def update(self, dt):
        """Called once per frame while driving. Return True to toggle the headlights."""
        return False


class ClickLightSwitch(LightSwitch):
    """Click the button on the dashboard with the mouse."""

    HIT_PAD = 3  # a little forgiving: the dashboard bobs by a pixel

    def __init__(self, app):
        self.app = app
        self.stimulus_hz = S.HEADLIGHT_BUTTON_HZ

    def _over_button(self, window_pos):
        p = self.app.window_to_canvas(window_pos)
        return p is not None and art.LIGHT_BUTTON.inflate(
            2 * self.HIT_PAD, 2 * self.HIT_PAD
        ).collidepoint(p)

    def handle_event(self, event):
        return (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self._over_button(event.pos)
        )

    def update(self, dt):
        self.hover = self._over_button(pygame.mouse.get_pos())
        return False


class SsvepLightSwitch(ClickLightSwitch):
    """Look at the flickering button to toggle the headlights. The mouse still works as a fallback.

    The raw occipital EEG comes from the `NightDriveEEG` LSL stream (tools/gpype_eeg_stream.py for the
    headset, tools/ssvep_sim_stream.py without one). Every `step_s` the last `window_s` seconds are
    measured (`ssvep_score_db`) and fed to an `SsvepDetector`.

    Calibration happens while driving, in the first `calibration_s` seconds after the stream is
    seen: the button flickers and the player should keep looking at the road. That baseline sets the
    threshold, and no toggling happens until it is done. A detection needs the player to hold their
    look for about `hold_s`, and a second one needs them to look away first.
    """

    GAP_S = 1.0  # a longer gap between updates means we were out of the drive scene

    def __init__(
        self,
        app,
        reader=None,
        config=None,
        clock=time.monotonic,
        log=None,
        log_interval_s=0.5,
    ):
        super().__init__(app)
        if reader is None:
            from .lsl.eeg_reader import EegReader  # lazy: click mode needs no pylsl

            reader = EegReader()
        self.reader = reader
        self.cfg = config or SsvepConfig()
        self.detector = SsvepDetector(self.cfg)
        self.log = log
        self._clock = clock
        self._log_interval_s = log_interval_s
        self._last_log = float("-inf")
        self._cal_scores = []
        self._cal_start = None
        self._next_eval = 0.0
        self._last_update = None
        self.last_score = None

    def start(self):
        self.reader.start()

    def stop(self):
        self.reader.stop()

    @property
    def ready(self):
        """Calibrated and the stream is alive: the player can toggle the lights with their eyes."""
        return self.detector.calibrated and self.reader.connected

    @property
    def calibration_progress(self):
        if self.detector.calibrated:
            return 1.0
        if self._cal_start is None:
            return 0.0
        return max(
            0.0, min(1.0, (self._clock() - self._cal_start) / self.cfg.calibration_s)
        )

    @property
    def status_text(self):
        if not self.detector.calibrated:
            if self._cal_start is None:
                return "SSVEP: WAITING FOR EEG STREAM"
            return f"SSVEP: CALIBRATING {int(self.calibration_progress * 100)}%  LOOK AT THE ROAD"
        return "" if self.reader.connected else "SSVEP: SIGNAL LOST"

    def update(self, dt):
        super().update(dt)  # hover, for the mouse fallback
        now = self._clock()
        if self._last_update is not None and now - self._last_update > self.GAP_S:
            self._new_session()  # we were in the menu: nothing measured then counts
        self._last_update = now
        return bool(self._measure(now))

    # --- internals --------------------------------------------------------------------

    def _new_session(self):
        self._cal_scores.clear()
        self._cal_start = None
        self.detector.reset()

    def _measure(self, now):
        """Returns True on the frame a detection fires."""
        cfg = self.cfg
        if not self.reader.connected:
            if self.detector.calibrated:
                self.detector.update(now)  # time passes: the signal goes stale
            return False
        if now < self._next_eval:
            return False
        window = self.reader.window(cfg.window_s)
        if window is None:
            return False
        self._next_eval = now + cfg.step_s
        score = ssvep_score_db(window, self.reader.sampling_rate, self.stimulus_hz, cfg)
        self.last_score = score

        if not self.detector.calibrated:
            if self._cal_start is None:
                self._cal_start = now
                self._emit(
                    f"calibrating for {cfg.calibration_s:g} s: look at the road, not the button"
                )
            self._cal_scores.append(score)
            if (
                now - self._cal_start >= cfg.calibration_s
                and len(self._cal_scores) >= cfg.min_calib_scores
            ):
                self.detector.calibrate(self._cal_scores)
                d = self.detector
                self._emit(
                    f"CALIBRATED from {len(self._cal_scores)} scores: baseline {d.baseline:.1f} dB "
                    f"-> threshold {d.threshold:.1f} dB (re-arm below {d.release:.1f} dB)"
                )
            else:
                self._log_state(
                    now, f"calibrating {int(self.calibration_progress * 100):3d}%"
                )
            return False

        state = self.detector.update(now, score)
        self._log_state(now, "ATTENDING" if state.attending else "looking away", state)
        if state.triggered:
            self._emit(
                f"DETECTED: toggling the headlights (score {state.score:.1f} dB)"
            )
        return state.triggered

    def _emit(self, text):
        if self.log:
            self.log(f"[ssvep] {text}")

    def _log_state(self, now, label, state=None):
        if not self.log or now - self._last_log < self._log_interval_s:
            return
        self._last_log = now
        raw = f"{self.last_score:6.1f}" if self.last_score is not None else "   -- "
        if state is None:
            self._emit(f"score {raw} dB  {label}")
        else:
            self._emit(
                f"score {raw} dB  avg {state.score:6.1f}  thr {state.threshold:5.1f}  "
                f"{label:13s} held {state.held_s:3.1f}s"
            )


def _print_flush(text):
    print(text, flush=True)


def make_light_switch(mode, app, log=True):
    if mode == "click":
        return ClickLightSwitch(app)
    if mode == "ssvep":
        return SsvepLightSwitch(app, log=_print_flush if log else None)
    raise ValueError(f"unknown light switch {mode!r}")
