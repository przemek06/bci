"""Publish filtered raw occipital EEG from the Unicorn over LSL, using g.Pype (for the SSVEP switch).

Runs as its own process, separate from the game, like tools/gpype_alpha_stream.py. The game reads the
`NightDriveEEG` stream with pylsl (nightdrive/lsl/eeg_reader.py).

Pipeline:
    HybridBlack (8 EEG @ 250 Hz) -> Router (occipital channels only)
    -> Bandpass 3-40 Hz -> Bandstop (mains) -> LSLSender "NightDriveEEG"

The stream carries one value per occipital channel per sample. A flicker at 15 Hz also shows at
its 2nd harmonic (30 Hz), so the band-pass keeps up to 40 Hz.

Usage:
    python tools/gpype_eeg_stream.py                  # real Unicorn (paired in Bluetooth)
    python tools/gpype_eeg_stream.py --serial UN-2024.01.01
    python tools/gpype_eeg_stream.py --simulate       # no headset: a constant tone at the flicker frequency
    python tools/ssvep_sim_stream.py                  # no headset, and you decide when you "look" at the button
"""

import argparse
import sys
import time
from pathlib import Path

import gpype as gp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run from anywhere

from nightdrive import settings as S

STREAM_NAME = "NightDriveEEG"
SAMPLING_RATE = 250

# Nominal Unicorn layout: Fz, C3, Cz, C4, Pz, PO7, Oz, PO8. Verify on the real device.
OCCIPITAL_CHANNELS = [5, 6, 7]  # PO7, Oz, PO8


def build_pipeline(args: argparse.Namespace) -> gp.Pipeline:
    p = gp.Pipeline()

    if args.simulate:
        source = gp.Generator(
            sampling_rate=SAMPLING_RATE,
            channel_count=8,
            signal_frequency=args.freq,
            signal_amplitude=10,
            noise_amplitude=10,
        )
    else:
        source = gp.HybridBlack(serial=args.serial, enable_oscar=args.oscar)

    router = gp.Router(
        input_channels=gp.Router.ALL,
        output_channels={"OCC": args.channels},
    )
    bandpass = gp.Bandpass(f_lo=3, f_hi=40)
    mains = gp.Bandstop(f_lo=args.mains - 2, f_hi=args.mains + 2)
    sender = gp.LSLSender(stream_name=args.name)

    p.connect(source, router)
    p.connect(router["OCC"], bandpass)
    p.connect(bandpass, mains)
    p.connect(mains, sender)
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--serial", help="Unicorn serial, e.g. UN-2024.01.01 (default: first found)"
    )
    ap.add_argument(
        "--simulate", action="store_true", help="use a synthetic source, no headset"
    )
    ap.add_argument(
        "--freq",
        type=float,
        default=S.HEADLIGHT_BUTTON_HZ,
        help="tone frequency for --simulate",
    )
    ap.add_argument(
        "--oscar",
        action="store_true",
        help="g.Pype OSCAR artifact removal on the headset stream (off by default: not checked against SSVEP)",
    )
    ap.add_argument("--name", default=STREAM_NAME, help="LSL stream name")
    ap.add_argument(
        "--channels",
        type=lambda s: [int(x) for x in s.split(",")],
        default=OCCIPITAL_CHANNELS,
        help="EEG channel indices to stream (default: 5,6,7 = PO7,Oz,PO8)",
    )
    ap.add_argument(
        "--mains", type=float, default=50.0, help="mains frequency in Hz (50 EU, 60 US)"
    )
    ap.add_argument(
        "--seconds",
        type=float,
        help="stop after N seconds instead of waiting for Enter",
    )
    args = ap.parse_args()

    p = build_pipeline(args)
    p.start()
    try:
        if args.seconds:
            print(f"Streaming LSL '{args.name}' for {args.seconds:g} s.", flush=True)
            time.sleep(args.seconds)
        else:
            print(
                f"Streaming LSL '{args.name}' (channels {args.channels}). Press Enter to stop.",
                flush=True,
            )
            input()
    finally:
        p.stop()
        p.close()


if __name__ == "__main__":
    main()
