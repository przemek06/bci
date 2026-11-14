"""Publish synthetic occipital EEG over LSL, for trying SSVEP without a headset.

The signal is noise + alpha + mains hum, plus, while the simulated player "looks" at a flickering
light, the response of the visual cortex to it (the light's frequency and its 2nd harmonic).

One light (the headlight button):
    python tools/ssvep_sim_stream.py                      # Enter toggles "looking at the button"
    python tools/ssvep_sim_stream.py --auto 6:10          # look 6 s, look away 10 s, repeat
    python -m nightdrive --lights ssvep                   # in another terminal: the game

Several lights (the demo): give the same frequencies as the demo, then type a number + Enter to look at
that button (0 = look away), or let --auto look at each button in turn.
    python tools/ssvep_sim_stream.py --freqs 6 7.5 13 17
    python tools/ssvep_sim_stream.py --freqs 6 7.5 13 17 --auto 8:6
    python -m nightdrive.ssvep_demo                       # in another terminal (or another computer)

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
from nightdrive.attention.ssvep_sim import (
    SimulatedEeg,  # also imported by the tests from here
)

STREAM_NAME = "NightDriveEEG"
SAMPLING_RATE = 250
CHANNELS = ["PO7", "Oz", "PO8"]


def main() -> None:
    from pylsl import StreamInfo, StreamOutlet

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--freq",
        type=float,
        default=S.HEADLIGHT_BUTTON_HZ,
        help="flicker frequency in Hz (one light)",
    )
    ap.add_argument(
        "--freqs",
        type=float,
        nargs="+",
        help="several lights (the demo): their frequencies. Type 1..N + Enter to look at one, 0 to look away",
    )
    ap.add_argument("--name", default=STREAM_NAME, help="LSL stream name")
    ap.add_argument(
        "--strength", type=float, default=3.0, help="SSVEP amplitude in microvolts"
    )
    ap.add_argument(
        "--auto",
        metavar="ON:OFF",
        help="look ON seconds, look away OFF seconds, repeat (each light in turn)",
    )
    args = ap.parse_args()
    targets = args.freqs or [args.freq]

    info = StreamInfo(
        args.name, "EEG", len(CHANNELS), SAMPLING_RATE, "float32", "nightdrive-sim"
    )
    chans = info.desc().append_child("channels")
    for label in CHANNELS:
        ch = chans.append_child("channel")
        ch.append_child_value("label", label)
        ch.append_child_value("unit", "microvolts")
    outlet = StreamOutlet(info)
    sim = SimulatedEeg(freq=targets[0], ssvep_uv=args.strength)

    looking = {
        "hz": None
    }  # the frequency the simulated player is looking at right now (None = nothing)

    def look(index):
        looking["hz"] = None if index is None else targets[index]
        if index is None:
            print("looking away", flush=True)
        else:
            what = "the button" if len(targets) == 1 else f"button {index + 1}"
            print(f"looking at {what} ({targets[index]:g} Hz)", flush=True)

    if args.auto:
        on_s, off_s = (float(x) for x in args.auto.split(":"))

        def cycle():
            while True:
                for index in range(len(targets)):
                    time.sleep(off_s)
                    look(index)
                    time.sleep(on_s)
                    look(None)

        threading.Thread(target=cycle, daemon=True).start()
    else:

        def keys():
            while True:
                line = input().strip()
                if len(targets) == 1:  # Enter toggles
                    look(None if looking["hz"] is not None else 0)
                elif line.isdigit() and 0 <= int(line) <= len(targets):
                    look(None if int(line) == 0 else int(line) - 1)
                else:
                    print(f"type a number from 0 to {len(targets)}", flush=True)

        threading.Thread(target=keys, daemon=True).start()

    shown = ", ".join(f"{f:g}" for f in targets)
    print(
        f"Streaming LSL '{args.name}', lights at {shown} Hz. Ctrl+C to stop.",
        flush=True,
    )
    step = 5  # samples per push (20 ms)
    start = time.perf_counter()
    sent = 0
    try:
        while True:
            due = int((time.perf_counter() - start) * SAMPLING_RATE) - sent
            if due >= step:
                hz = looking["hz"]
                outlet.push_chunk(
                    sim.chunk(step, hz is not None, hz).astype(np.float32)
                )
                sent += step
            else:
                time.sleep(0.004)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
