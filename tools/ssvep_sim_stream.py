"""Publish synthetic occipital EEG over LSL, for trying the SSVEP headlight switch without a headset.

The signal is noise + alpha + mains hum, plus, while you are "attending", the response of the visual
cortex to a light flickering at the button's frequency (the fundamental and its 2nd harmonic).
Press Enter to start / stop attending, or use --auto to cycle by itself.

Usage:
    python tools/ssvep_sim_stream.py                      # Enter toggles "attending"
    python tools/ssvep_sim_stream.py --auto 6:10          # attend 6 s, look away 10 s, repeat
    python -m nightdrive --lights ssvep                   # in another terminal: the game

The stream is called `NightDriveEEG` and has 3 channels (PO7, Oz, PO8) at 250 Hz, like
tools/gpype_eeg_stream.py. The frequency defaults to the button's (HEADLIGHT_BUTTON_HZ).
"""

import argparse
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run from anywhere

from nightdrive import settings as S

STREAM_NAME = "NightDriveEEG"
SAMPLING_RATE = 250
CHANNELS = ["PO7", "Oz", "PO8"]


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

    def chunk(self, n, attending=False):
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
                f = self.freq
                sig = sig + self.ssvep_uv * np.sin(2 * np.pi * f * t + self._phase[c])
                sig = sig + 0.5 * self.ssvep_uv * np.sin(
                    2 * np.pi * 2 * f * t + 2 * self._phase[c]
                )
            out[:, c] = sig * self._gain[c]
        self.n += n
        return out


def main() -> None:
    from pylsl import StreamInfo, StreamOutlet

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--freq",
        type=float,
        default=S.HEADLIGHT_BUTTON_HZ,
        help="flicker frequency in Hz",
    )
    ap.add_argument("--name", default=STREAM_NAME, help="LSL stream name")
    ap.add_argument(
        "--strength", type=float, default=3.0, help="SSVEP amplitude in microvolts"
    )
    ap.add_argument(
        "--auto",
        metavar="ON:OFF",
        help="attend ON seconds, look away OFF seconds, repeat",
    )
    args = ap.parse_args()

    info = StreamInfo(
        args.name, "EEG", len(CHANNELS), SAMPLING_RATE, "float32", "nightdrive-sim"
    )
    chans = info.desc().append_child("channels")
    for label in CHANNELS:
        ch = chans.append_child("channel")
        ch.append_child_value("label", label)
        ch.append_child_value("unit", "microvolts")
    outlet = StreamOutlet(info)
    sim = SimulatedEeg(freq=args.freq, ssvep_uv=args.strength)

    attending = threading.Event()
    if args.auto:
        on_s, off_s = (float(x) for x in args.auto.split(":"))

        def cycle():
            while True:
                time.sleep(off_s)
                attending.set()
                print("attending (looking at the button)", flush=True)
                time.sleep(on_s)
                attending.clear()
                print("looking away", flush=True)

        threading.Thread(target=cycle, daemon=True).start()
    else:

        def keys():
            while True:
                input()
                attending.clear() if attending.is_set() else attending.set()
                print(
                    "attending (looking at the button)"
                    if attending.is_set()
                    else "looking away",
                    flush=True,
                )

        threading.Thread(target=keys, daemon=True).start()

    print(
        f"Streaming LSL '{args.name}' at {args.freq:g} Hz flicker. Ctrl+C to stop.",
        flush=True,
    )
    step = 5  # samples per push (20 ms)
    start = time.perf_counter()
    sent = 0
    try:
        while True:
            due = int((time.perf_counter() - start) * SAMPLING_RATE) - sent
            if due >= step:
                outlet.push_chunk(
                    sim.chunk(step, attending.is_set()).astype(np.float32)
                )
                sent += step
            else:
                time.sleep(0.004)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
