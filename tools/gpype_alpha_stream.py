"""Publish EEG band powers from the Unicorn over LSL, using g.Pype.

Runs as its own process, separate from the game, so g.Pype's threads never touch the pygame
loop. The game reads the streams below with pylsl.

The headset source runs g.Pype's OSCAR artifact removal (HybridBlack(enable_oscar=True), the
documented switch, ENABLE_OSCAR). It applies to the whole stream, so BOTH branches below get
OSCAR-cleaned data.

Two SEPARATE branches from the same source, each with its own filters / FFT / band power:

1. Alpha branch (eyes-closed ghost), same filters as the original ghost integration:
    HybridBlack (OSCAR) -> Router (occipital channels PO7, Oz, PO8)
    -> Bandpass 1-40 Hz -> Bandstop (mains) -> FFT (1 s window, updates every 0.25 s)
    -> BandPower alpha 8-12 Hz + broadband 2-30 Hz -> LSLSender "NightDriveAlpha"
   Per update: (alpha, broad) for each channel. Relative alpha = alpha / broad rises
   strongly when the eyes are closed.

2. Attention branch (focus-to-pass quick-time events):
    Router (C3, Cz, C4, Pz) -> Bandpass 0.5-50 Hz -> Bandstop (mains)
    -> FFT (1 s window, updates every 0.25 s)
    -> BandPower theta 4-8, alpha 8-12, beta low 13-16, beta mid 16-20, beta high 20-30,
       gamma 30-45 Hz -> LSLSender "NightDriveBands"
   Per update: (theta, alpha, beta_low, beta_mid, beta_high, gamma) for each channel.

Usage:
    python tools/gpype_alpha_stream.py                 # real Unicorn (paired in Windows Bluetooth)
    python tools/gpype_alpha_stream.py --serial UN-2024.01.01
"""

import argparse
import time

import gpype as gp

STREAM_NAME = "NightDriveAlpha"
BANDS_STREAM_NAME = "NightDriveBands"
SAMPLING_RATE = 250

# Nominal Unicorn layout: Fz, C3, Cz, C4, Pz, PO7, Oz, PO8. Verify on the real device.
OCCIPITAL_CHANNELS = [5, 6, 7]  # PO7, Oz, PO8
ATTENTION_CHANNELS = [1, 2, 3, 4,]  # C3, Cz, C4, Pz: away from the eyes and forehead muscles

ALPHA_BAND = [8.0, 12.0]
BROAD_BAND = [2.0, 30.0]  # reference power for the relative-alpha ratio
ATTENTION_BANDS = [
    [4.0, 8.0],  # theta
    [8.0, 12.0],  # alpha
    [13.0, 16.0],  # beta low
    [16.0, 20.0],  # beta mid
    [20.0, 30.0],  # beta high
    [30.0, 45.0],  # gamma
]


def build_pipeline(args: argparse.Namespace) -> gp.Pipeline:
    p = gp.Pipeline()

    # OSCAR artifact removal on the whole stream (documented switch; both branches get it)
    source = gp.HybridBlack(serial=args.serial, enable_oscar=True)

    router = gp.Router(
        input_channels=gp.Router.ALL,
        output_channels={"OCC": args.channels, "ATT": args.att_channels},
    )
    p.connect(source, router)

    # 1. Alpha branch (same filters as the original)
    bandpass = gp.Bandpass(f_lo=1, f_hi=40)
    mains = gp.Bandstop(f_lo=args.mains - 2, f_hi=args.mains + 2)
    fft = gp.FFT(window_size=args.window, overlap=args.overlap)
    power = gp.BandPower(bands=[ALPHA_BAND, BROAD_BAND])
    sender = gp.LSLSender(stream_name=STREAM_NAME)

    p.connect(router["OCC"], bandpass)
    p.connect(bandpass, mains)
    p.connect(mains, fft)
    p.connect(fft, power)
    p.connect(power, sender)

    # 2. Attention branch (its own filters, FFT and band power)
    att_bandpass = gp.Bandpass(f_lo=0.5, f_hi=50)
    att_mains = gp.Bandstop(f_lo=args.mains - 2, f_hi=args.mains + 2)
    att_fft = gp.FFT(window_size=args.window, overlap=args.overlap)
    att_power = gp.BandPower(bands=ATTENTION_BANDS)
    att_sender = gp.LSLSender(stream_name=BANDS_STREAM_NAME)

    p.connect(router["ATT"], att_bandpass)
    p.connect(att_bandpass, att_mains)
    p.connect(att_mains, att_fft)
    p.connect(att_fft, att_power)
    p.connect(att_power, att_sender)
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--serial", help="Unicorn serial, e.g. UN-2024.01.01 (default: first found)"
    )
    ap.add_argument(
        "--channels",
        type=lambda s: [int(x) for x in s.split(",")],
        default=OCCIPITAL_CHANNELS,
        help="EEG channels for the alpha / eyes-closed stream (default: 5,6,7 = PO7,Oz,PO8)",
    )
    ap.add_argument(
        "--att-channels",
        type=lambda s: [int(x) for x in s.split(",")],
        default=ATTENTION_CHANNELS,
        help="EEG channels for the attention index (default: 1,2,3,4 = C3,Cz,C4,Pz)",
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
            print(f"Streaming for {args.seconds:g} s.", flush=True)
            time.sleep(args.seconds)
        else:
            print(
                f"Streaming '{STREAM_NAME}' and '{BANDS_STREAM_NAME}'. Press Enter to stop.",
                flush=True,
            )
            input()
    finally:
        p.stop()
        p.close()


if __name__ == "__main__":
    main()
