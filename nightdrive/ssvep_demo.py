"""SSVEP demo: several buttons flickering at different frequencies, and which one you are looking at.

    python -m nightdrive.ssvep_demo                   # the headset: reads the LSL stream "NightDriveEEG"
    python -m nightdrive.ssvep_demo --source sim      # no headset: hover the mouse over a button to "look" at it
    python -m nightdrive.ssvep_demo --freqs 6 7.5 13 17 --wave sine --calibration 10

Each button flickers at its own frequency. The visual cortex of someone looking at one of them oscillates
at that frequency, which shows in the occipital EEG (tools/gpype_eeg_stream.py publishes it). The demo
measures every button's frequency in the last 2 seconds, compares each to the level it shows when you
look at none of them, and reports the button you are looking at, on screen and on the console.

It starts by calibrating for a few seconds: look at the cross below the buttons, not at the buttons.
Keys: R = calibrate again, ESC = quit. In --source sim: 1..N = "look" at a button, 0 = look away.

Frequencies are chosen so that no button's 2nd harmonic lands on another's frequency, and none is in the
8-12 Hz alpha band. (Sampled sine luminance is used by default so any frequency is accurate on a 60 Hz screen.)
"""

import argparse
import sys
import time
from dataclasses import dataclass

import pygame

from .attention.ssvep import SsvepConfig, SsvepSelector, ssvep_score_db
from .light_switch import stimulus_level

DEFAULT_FREQS = (6.0, 7.5, 13.0, 17.0)
STREAM_NAME = "NightDriveEEG"

BG = (12, 14, 22)
TEXT = (225, 228, 255)
DIM = (120, 128, 170)
GOOD = (120, 255, 160)
BAD = (255, 120, 90)
DARK, BRIGHT = (
    (14, 16, 24),
    (246, 248, 255),
)  # the two extremes of the flicker: maximum contrast


# --- the logic (no pygame) --------------------------------------------------------------------------------


class DemoModel:
    """Measures every button's frequency, calibrates, and decides which button is being looked at.

    `source` is an EegReader or a SimulatedSource: `start()`, `stop()`, `connected`, `sampling_rate`,
    `window(seconds)`. `clock` returns seconds. `log` receives one line per event (None = silent).
    """

    def __init__(
        self,
        freqs,
        source,
        config=None,
        calibration_s=10.0,
        clock=time.monotonic,
        log=None,
    ):
        self.freqs = tuple(freqs)
        self.source = source
        self.cfg = config or SsvepConfig()
        self.calibration_s = calibration_s
        self.selector = SsvepSelector(len(self.freqs), self.cfg)
        self.log = log
        self._clock = clock
        self._next_eval = 0.0
        self._baseline = [[] for _ in self.freqs]
        self._cal_start = None
        self.raw = [0.0] * len(self.freqs)  # latest score per button, dB
        self.state = None
        self._last_selected = None

    def start(self):
        self.source.start()

    def stop(self):
        self.source.stop()

    def recalibrate(self):
        self.selector.calibrated = False
        self.selector.reset()
        self._baseline = [[] for _ in self.freqs]
        self._cal_start = None
        self._last_selected = None
        self.state = None
        self._emit("calibrating again: look at the cross, not at the buttons")

    # --- what the screen shows -------------------------------------------------------------------------

    @property
    def calibrated(self):
        return self.selector.calibrated

    @property
    def calibration_progress(self):
        if self.calibrated:
            return 1.0
        if self._cal_start is None:
            return 0.0
        return max(
            0.0, min(1.0, (self._clock() - self._cal_start) / self.calibration_s)
        )

    @property
    def selected(self):
        return self.state.selected if self.state else None

    @property
    def scores(self):
        return list(self.state.scores) if self.state else list(self.raw)

    @property
    def thresholds(self):
        return list(self.selector.thresholds) if self.calibrated else None

    @property
    def status_text(self):
        if not self.source.connected:
            return (
                "SIGNAL LOST"
                if self._cal_start is not None or self.calibrated
                else "WAITING FOR THE EEG STREAM"
            )
        if not self.calibrated:
            if self._cal_start is None:
                return "WAITING FOR ENOUGH EEG..."
            return f"CALIBRATING {int(self.calibration_progress * 100)}%  LOOK AT THE CROSS, NOT THE BUTTONS"
        return ""

    def label(self, index):
        return f"BUTTON {index + 1} ({self.freqs[index]:g} Hz)"

    @property
    def verdict(self):
        """The one line answer: what is the player looking at?"""
        if self.status_text:
            return self.status_text
        return (
            f"LOOKING AT: {self.label(self.selected)}"
            if self.selected is not None
            else "LOOKING AT: NOTHING"
        )

    # --- every frame -------------------------------------------------------------------------------------

    def update(self):
        now = self._clock()
        if not self.source.connected:
            if self.calibrated:
                self.state = self.selector.update(
                    now
                )  # time passes: the signal goes stale
            self._note_selection()
            return
        if now < self._next_eval:
            return
        window = self.source.window(self.cfg.window_s)
        if window is None:
            return
        self._next_eval = now + self.cfg.step_s
        fs = self.source.sampling_rate
        self.raw = [ssvep_score_db(window, fs, f, self.cfg) for f in self.freqs]

        if not self.calibrated:
            if self._cal_start is None:
                self._cal_start = now
                self._emit(
                    f"calibrating for {self.calibration_s:g} s: look at the cross, not at the buttons"
                )
            for scores, v in zip(self._baseline, self.raw, strict=True):
                scores.append(v)
            if (
                now - self._cal_start >= self.calibration_s
                and len(self._baseline[0]) >= self.cfg.min_calib_scores
            ):
                self.selector.calibrate(self._baseline)
                th = ", ".join(
                    f"{f:g} Hz: {t:.1f} dB"
                    for f, t in zip(self.freqs, self.selector.thresholds, strict=True)
                )
                self._emit(f"CALIBRATED. Thresholds: {th}")
            return
        self.state = self.selector.update(now, self.raw)
        self._note_selection()

    def _note_selection(self):
        if self.state is None or self.state.selected == self._last_selected:
            return
        self._last_selected = self.state.selected
        what = (
            "nothing"
            if self.state.selected is None
            else self.label(self.state.selected)
        )
        self._emit(f"looking at {what}")

    def _emit(self, text):
        if self.log:
            self.log(f"[ssvep-demo] {text}")


# --- the window ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Layout:
    buttons: list  # pygame.Rect per button (the flickering areas)
    cross: tuple  # centre of the fixation cross
    verdict_y: int
    footer_y: int


def layout(size, n):
    w, h = size
    gap = max(16, w // 40)
    bw = min(280, (w - 2 * gap - (n - 1) * gap) // n)
    bh = int(bw * 0.72)
    total = n * bw + (n - 1) * gap
    x0 = (w - total) // 2
    top = int(h * 0.17)
    buttons = [pygame.Rect(x0 + i * (bw + gap), top, bw, bh) for i in range(n)]
    cross = (w // 2, int(h * 0.80))
    return Layout(buttons, cross, int(h * 0.68), h - 22)


def mix(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b, strict=True))


def bar_fraction(db, lo=-8.0, hi=14.0):
    return max(0.0, min(1.0, (db - lo) / (hi - lo)))


class DemoView:
    """Draws the demo and turns keys / the mouse into actions. Knows nothing about EEG."""

    def __init__(self, model, wave="sine", sim=None, clock=time.perf_counter):
        self.model = model
        self.wave = wave
        self.sim = sim  # a SimulatedSource when there is no headset, else None
        self._clock = (
            clock  # wall clock for the flicker: its frequency must be true to life
        )
        self._fonts = {}
        self.drawn_text = []  # every string drawn in the last frame (handy for tests)
        self._sticky = None  # sim: the button chosen with the number keys
        self.hover = None
        self.frames = self.dropped = 0
        self._last_frame = None

    def font(self, size):
        if size not in self._fonts:
            self._fonts[size] = pygame.font.Font(None, size)
        return self._fonts[size]

    def text(self, surf, string, size, color, center=None, topleft=None):
        self.drawn_text.append(string)
        img = self.font(size).render(string, True, color)
        surf.blit(
            img,
            img.get_rect(center=center) if center else img.get_rect(topleft=topleft),
        )

    # --- input ----------------------------------------------------------------------------------------

    def handle_event(self, event):
        """Returns "quit" to stop the demo."""
        if event.type == pygame.QUIT:
            return "quit"
        if event.type != pygame.KEYDOWN:
            return None
        if event.key == pygame.K_ESCAPE:
            return "quit"
        if event.key == pygame.K_r:
            self.model.recalibrate()
        elif self.sim is not None and pygame.K_0 <= event.key <= pygame.K_9:
            n = event.key - pygame.K_0
            self._sticky = n - 1 if 1 <= n <= len(self.model.freqs) else None
        return None

    def update_simulated_gaze(self, size):
        """With no headset the 'player' looks at the button under the mouse (or the one chosen by key)."""
        rects = layout(size, len(self.model.freqs)).buttons
        pos = pygame.mouse.get_pos()
        self.hover = next((i for i, r in enumerate(rects) if r.collidepoint(pos)), None)
        target = self.hover if self.hover is not None else self._sticky
        want = None if target is None else self.model.freqs[target]
        if self.sim is not None and want != self.sim.looking_at:
            self.sim.look_at(want)

    # --- drawing ---------------------------------------------------------------------------------------

    def draw(self, surf, fps=0.0):
        self.drawn_text = []
        m = self.model
        w, h = surf.get_size()
        lay = layout((w, h), len(m.freqs))
        now = self._clock()
        surf.fill(BG)
        self.text(surf, "SSVEP DEMO", 40, TEXT, center=(w // 2, 26))
        self.text(
            surf,
            "each button flickers at its own frequency: look at one",
            22,
            DIM,
            center=(w // 2, 56),
        )

        for i, rect in enumerate(lay.buttons):
            level = stimulus_level(now, m.freqs[i], self.wave)
            pygame.draw.rect(surf, mix(DARK, BRIGHT, level), rect)
            selected = m.selected == i
            pygame.draw.rect(
                surf,
                GOOD if selected else (40, 44, 64),
                rect.inflate(16, 16),
                4,
                border_radius=4,
            )
            self.text(
                surf,
                f"BUTTON {i + 1}",
                28,
                GOOD if selected else TEXT,
                center=(rect.centerx, rect.bottom + 26),
            )
            self.text(
                surf,
                f"{m.freqs[i]:g} Hz",
                24,
                GOOD if selected else DIM,
                center=(rect.centerx, rect.bottom + 48),
            )
            self._draw_bar(surf, rect, i)

        cx, cy = lay.cross
        pygame.draw.line(surf, DIM, (cx - 14, cy), (cx + 14, cy), 3)
        pygame.draw.line(surf, DIM, (cx, cy - 14), (cx, cy + 14), 3)
        self.text(surf, "look here while calibrating", 20, DIM, center=(cx, cy + 30))

        verdict = m.verdict
        color = (
            GOOD
            if m.selected is not None and not m.status_text
            else (DIM if not m.status_text else BAD)
        )
        self.text(surf, verdict, 46, color, center=(w // 2, lay.verdict_y))
        if not m.calibrated:  # a progress bar under the message
            bar = pygame.Rect(0, 0, 360, 10)
            bar.center = (w // 2, lay.verdict_y + 34)
            pygame.draw.rect(surf, (28, 32, 48), bar)
            pygame.draw.rect(
                surf, GOOD, (bar.x, bar.y, int(bar.w * m.calibration_progress), bar.h)
            )

        self._draw_footer(surf, lay, fps)

    def _draw_bar(self, surf, rect, i):
        m = self.model
        bar = pygame.Rect(rect.x, rect.bottom + 70, rect.w, 14)
        pygame.draw.rect(surf, (28, 32, 48), bar)
        score = m.scores[i]
        th = m.thresholds[i] if m.thresholds else None
        over = th is not None and score >= th
        pygame.draw.rect(
            surf,
            GOOD if over else (90, 120, 200),
            (bar.x, bar.y, int(bar.w * bar_fraction(score)), bar.h),
        )
        if th is not None:
            tx = bar.x + int(bar.w * bar_fraction(th))
            pygame.draw.line(surf, TEXT, (tx, bar.y - 3), (tx, bar.bottom + 3), 2)
        self.text(
            surf,
            f"{score:+.1f} dB",
            20,
            TEXT if over else DIM,
            center=(rect.centerx, bar.bottom + 16),
        )

    def _draw_footer(self, surf, lay, fps):
        w = surf.get_width()
        source = (
            "simulated EEG" if self.sim is not None else "LSL stream " + STREAM_NAME
        )
        keys = "R recalibrate   ESC quit"
        if self.sim is not None:
            keys += f"   |   mouse over a button (or 1-{len(self.model.freqs)}, 0 = away) = look"
        self.text(
            surf, f"{source}   |   {keys}", 20, DIM, center=(w // 2, lay.footer_y - 22)
        )
        self.text(
            surf,
            f"{fps:4.1f} FPS   {self.dropped} dropped frames (the flicker needs a steady 60)",
            18,
            BAD if self.dropped else DIM,
            center=(w // 2, lay.footer_y),
        )

    def count_frame(self):
        """Call once per displayed frame: counts frames that took far longer than 1/60 s."""
        now = self._clock()
        if self._last_frame is not None and now - self._last_frame > 1.5 / 60:
            self.dropped += 1
        self._last_frame = now
        self.frames += 1


# --- running it ----------------------------------------------------------------------------------------------


def _print_flush(text):
    print(text, flush=True)


def build(args):
    """The model and view for parsed command-line `args`."""
    if args.source == "sim":
        from .attention.ssvep_sim import SimulatedSource

        source = sim = SimulatedSource(strength=args.strength)
    else:
        from .lsl.eeg_reader import EegReader

        source, sim = EegReader(stream_name=args.stream), None
    model = DemoModel(
        args.freqs,
        source,
        config=SsvepConfig(method=args.method),
        calibration_s=args.calibration,
        log=_print_flush,
    )
    return model, DemoView(model, wave=args.wave, sim=sim)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        prog="nightdrive.ssvep_demo", description=__doc__.split("\n")[0]
    )
    ap.add_argument(
        "--freqs",
        type=float,
        nargs="+",
        default=list(DEFAULT_FREQS),
        help="flicker frequencies in Hz",
    )
    ap.add_argument(
        "--source",
        choices=("lsl", "sim"),
        default="lsl",
        help="the headset stream, or simulated EEG",
    )
    ap.add_argument(
        "--stream", default=STREAM_NAME, help="LSL stream name (--source lsl)"
    )
    ap.add_argument(
        "--wave", choices=("sine", "square"), default="sine", help="flicker waveform"
    )
    ap.add_argument(
        "--method",
        choices=("fbcca", "cca", "psd"),
        default=SsvepConfig().method,
        help="detection method: filter-bank CCA, CCA, or the power-spectrum SNR",
    )
    ap.add_argument(
        "--calibration", type=float, default=10.0, help="calibration length in seconds"
    )
    ap.add_argument(
        "--strength",
        type=float,
        default=6.0,
        help="simulated SSVEP amplitude in microvolts (--source sim)",
    )
    ap.add_argument(
        "--size",
        type=int,
        nargs=2,
        default=(1280, 720),
        metavar=("W", "H"),
        help="window size",
    )
    args = ap.parse_args(argv)
    if len(args.freqs) < 2:
        ap.error("need at least two frequencies")
    return args


def main(argv=None):
    args = parse_args(argv)
    pygame.init()
    pygame.display.set_caption("SSVEP demo")
    try:  # vsync keeps the flicker steady
        screen = pygame.display.set_mode(tuple(args.size), pygame.RESIZABLE, vsync=1)
    except pygame.error:
        screen = pygame.display.set_mode(tuple(args.size), pygame.RESIZABLE)
    model, view = build(args)
    clock = pygame.time.Clock()
    model.start()
    print(
        f"[ssvep-demo] {', '.join(f'{f:g}' for f in args.freqs)} Hz, source: {args.source}. ESC to quit.",
        flush=True,
    )
    running = True
    try:
        while running:
            for event in pygame.event.get():
                if view.handle_event(event) == "quit":
                    running = False
            screen = pygame.display.get_surface()
            if view.sim is not None:
                view.update_simulated_gaze(screen.get_size())
            model.update()
            view.draw(screen, clock.get_fps())
            view.count_frame()
            pygame.display.flip()
            clock.tick(60)
    finally:
        model.stop()
        pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
