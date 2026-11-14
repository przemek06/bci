"""Publish occipital alpha / broadband power from the Unicorn over LSL, using g.Pype.

Runs as its own process, separate from the game, so g.Pype's threads never
touch the pygame loop. The game (or tools/lsl_alpha_print.py) reads the
`NightDriveAlpha` stream with pylsl.

Pipeline:
    HybridBlack (8 EEG @ 250 Hz) -> Router (occipital channels only)
    -> Bandpass 1-40 Hz -> Bandstop (mains) -> FFT -> BandPower
    -> LSLSender "NightDriveAlpha"

Per update, the stream carries 2 values per occipital channel, in order
(alpha, broad) for each channel. Relative alpha = alpha / broad rises
strongly when the eyes are closed.

Usage:
    python tools/gpype_alpha_stream.py                 # real Unicorn (paired in Windows Bluetooth)
    python tools/gpype_alpha_stream.py --serial UN-2024.01.01
    python tools/gpype_alpha_stream.py --simulate      # no headset: 10 Hz test signal
"""

import argparse
import time

import gpype as gp

STREAM_NAME = "NightDriveAlpha"
SAMPLING_RATE = 250

# Nominal Unicorn layout: Fz, C3, Cz, C4, Pz, PO7, Oz, PO8. Verify on the real device.
OCCIPITAL_CHANNELS = [5, 6, 7]  # PO7, Oz, PO8

ALPHA_BAND = [8.0, 12.0]
BROAD_BAND = [2.0, 30.0]  # reference power for the relative-alpha ratio


def build_pipeline(args: argparse.Namespace) -> gp.Pipeline:
    p = gp.Pipeline()

    if args.simulate:
        source = gp.Generator(
            sampling_rate=SAMPLING_RATE,
            channel_count=8,
            signal_frequency=10,
            signal_amplitude=10,
            noise_amplitude=10,
        )
    else:
        source = gp.HybridBlack(serial=args.serial)

    router = gp.Router(
        input_channels=gp.Router.ALL,
        output_channels={"OCC": args.channels},
    )
    bandpass = gp.Bandpass(f_lo=1, f_hi=40)
    mains = gp.Bandstop(f_lo=args.mains - 2, f_hi=args.mains + 2)
    fft = gp.FFT(window_size=args.window, overlap=args.overlap)
    power = gp.BandPower(bands=[ALPHA_BAND, BROAD_BAND])
    sender = gp.LSLSender(stream_name=STREAM_NAME)

    p.connect(source, router)
    p.connect(router["OCC"], bandpass)
    p.connect(bandpass, mains)
    p.connect(mains, fft)
    p.connect(fft, power)
    p.connect(power, sender)
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--serial", help="Unicorn serial, e.g. UN-2024.01.01 (default: first found)"
    )
    ap.add_argument(
        "--simulate",
        action="store_true",
        help="use a synthetic 10 Hz source, no headset",
    )
    ap.add_argument(
        "--channels",
        type=lambda s: [int(x) for x in s.split(",")],
        default=OCCIPITAL_CHANNELS,
        help="EEG channel indices to analyse (default: 5,6,7 = PO7,Oz,PO8)",
    )
    ap.add_argument(
        "--mains", type=float, default=50.0, help="mains frequency in Hz (50 EU, 60 US)"
    )
    ap.add_argument(
        "--window",
        type=int,
        default=SAMPLING_RATE,
        help="FFT window in samples (250 = 1 s)",
    )
    ap.add_argument(
        "--overlap",
        type=float,
        default=0.75,
        help="FFT overlap (0.75 -> update every 0.25 s)",
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
            print(f"Streaming LSL '{STREAM_NAME}' for {args.seconds:g} s.", flush=True)
            time.sleep(args.seconds)
        else:
            print(
                f"Streaming LSL '{STREAM_NAME}' (channels {args.channels}). Press Enter to stop.",
                flush=True,
            )
            input()
    finally:
        p.stop()
        p.close()


if __name__ == "__main__":
    main()
