"""Where "are the eyes closed?" comes from: the keyboard (no hardware) or the BCI.

Both sources feed the same `EyesClosedDetector`, so the keyboard path exercises
exactly the same hold/grace/pass logic as the real headset.

Common interface (used by the game):
    start() / stop()
    update() -> EyesClosedState      call once per frame
    begin_challenge()                reset hold progress when a ghost appears
    ready: bool                      can a challenge be run right now?
    status_text: str                 short HUD message when not ready ("" if fine)
    hint: str                        how the player closes their "eyes" in this mode
    detector                         for hold_s etc.
"""

import time
from collections.abc import Callable

from .eyes_closed import EyesClosedConfig, EyesClosedDetector, EyesClosedState

# Synthetic relative-alpha levels used by the keyboard source.
KEY_OPEN, KEY_CLOSED = 0.1, 0.8


class KeyboardEyes:
    """Hold a key to simulate closed eyes."""

    mode = "keyboard"
    hint = "HOLD SPACE"
    status_text = ""
    ready = True
    log = None

    def __init__(
        self,
        is_down: Callable[[], bool],
        config: EyesClosedConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._is_down = is_down
        self._clock = clock
        self.detector = EyesClosedDetector(config)
        self.detector.calibrate([KEY_OPEN] * self.detector.cfg.min_calib_samples)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def begin_challenge(self) -> None:
        self.detector.reset()

    def update(self) -> EyesClosedState:
        return self.detector.update(
            self._clock(), KEY_CLOSED if self._is_down() else KEY_OPEN
        )


class BciEyes:
    """Relative alpha from the LSL stream. Calibrates itself on the player's open eyes.

    `update()` is called every frame by the app (menu, drive, game over), and is safe to call
    more than once per frame. Calibration starts the first time the stream is seen, i.e. while
    the player is looking at the game with their eyes open. The first `settle_s` seconds are ignored (the
    FFT window is still warming up), then `calibration_s` seconds are collected.
    """

    mode = "bci"
    hint = "KEEP THEM SHUT"

    def __init__(
        self,
        reader=None,
        config: EyesClosedConfig | None = None,
        calibration_s: float = 15.0,
        settle_s: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        log: Callable[[str], None] | None = None,
        log_interval_s: float = 0.5,
    ) -> None:
        if reader is None:
            from ..lsl.alpha_reader import (
                AlphaReader,
            )  # lazy: keyboard mode needs no pylsl

            reader = AlphaReader()
        self.reader = reader
        self.detector = EyesClosedDetector(config)
        self.calibration_s = calibration_s
        self.settle_s = settle_s
        self._clock = clock
        self._cal_start: float | None = None
        self._cal_values: list[float] = []
        self.log = log  # live monitor: also used by the ghost to log its outcomes
        self._log_interval_s = log_interval_s
        self._last_log = float("-inf")
        self._raw: float | None = None  # most recent relative-alpha sample

    def start(self) -> None:
        self.reader.start()

    def stop(self) -> None:
        self.reader.stop()

    def begin_challenge(self) -> None:
        self.detector.reset()

    @property
    def calibration_progress(self) -> float:
        if self.detector.calibrated:
            return 1.0
        if self._cal_start is None:
            return 0.0
        elapsed = self._clock() - self._cal_start - self.settle_s
        return max(0.0, min(1.0, elapsed / self.calibration_s))

    @property
    def ready(self) -> bool:
        return self.detector.calibrated and self.reader.connected

    @property
    def status_text(self) -> str:
        if not self.detector.calibrated:
            if self._cal_start is None:
                return "EEG: WAITING FOR STREAM"
            return f"EEG: CALIBRATING {int(self.calibration_progress * 100)}%  KEEP EYES OPEN"
        return "" if self.reader.connected else "EEG: SIGNAL LOST"

    def update(self) -> EyesClosedState:
        now = self._clock()
        samples = self.reader.drain()
        if self._cal_start is None and not self.detector.calibrated:
            if self.reader.connected:
                self._cal_start = now  # drop anything buffered before the drive began
            samples = []

        for s in samples:
            if not self.detector.calibrated and s.t - self._cal_start >= self.settle_s:
                self._cal_values.append(s.value)
            self.detector.update(s.t, s.value)
            self._raw = s.value

        if (
            not self.detector.calibrated
            and self._cal_start is not None
            and now - self._cal_start >= self.settle_s + self.calibration_s
            and len(self._cal_values) >= self.detector.cfg.min_calib_samples
        ):
            self.detector.calibrate(self._cal_values)
            d = self.detector
            self._emit(
                f"CALIBRATED from {len(self._cal_values)} samples: eyes-open baseline "
                f"{d.baseline:.3f} -> closed threshold {d.threshold:.3f} "
                f"(release {d.release:.3f})"
            )
        state = self.detector.update(now)
        self._log_state(now, state)
        return state

    def _emit(self, text: str) -> None:
        if self.log:
            self.log(f"[eyes] {text}")

    def _log_state(self, now: float, state: EyesClosedState) -> None:
        if not self.log or now - self._last_log < self._log_interval_s:
            return
        self._last_log = now
        raw = "  --  " if self._raw is None else f"{self._raw:6.3f}"
        if not self.detector.calibrated:
            if self._cal_start is None:
                self._emit("waiting for the NightDriveAlpha stream...")
            else:
                self._emit(
                    f"raw {raw}  calibrating {int(self.calibration_progress * 100):3d}% "
                    f"(keep eyes open, n={len(self._cal_values)})"
                )
            return
        label = "CLOSED" if state.closed else "open  "
        signal = "" if state.signal_ok else "  NO SIGNAL"
        self._emit(
            f"raw {raw}  avg {state.score:6.3f}  thr {state.threshold:6.3f}  "
            f"{label}  held {state.held_s:3.1f}s{signal}"
        )


def _print_flush(text: str) -> None:
    print(text, flush=True)


def make_eyes_source(
    mode: str = "keyboard", config: EyesClosedConfig | None = None, log: bool = True
):
    if mode == "bci":
        return BciEyes(config=config, log=_print_flush if log else None)
    import pygame

    return KeyboardEyes(lambda: bool(pygame.key.get_pressed()[pygame.K_SPACE]), config)
