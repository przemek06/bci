"""Print the calculated attention index from the `NightDriveBands` LSL stream.

Like tools/lsl_alpha_print.py, but for the attention index the game uses (same code, so the
numbers match the game's [attention] log):

    attention = (beta + gamma) / alpha      beta = low + mid + high beta

It first records your own baseline (about 23 s: keep your eyes open and sit still), then prints
`level` = attention relative to that baseline: 1.0 = your normal, 1.4 = 40% above it. The bar
shows the level; the `|` marks the level that passes a quick-time event by focus (1.4).
Start tools/gpype_alpha_stream.py first (and give it about a minute to settle).

Usage:
    python tools/lsl_attention_print.py
    python tools/lsl_attention_print.py --pass-level 1.5
"""

import argparse
import sys
import time
from pathlib import Path

from pylsl import StreamInlet, resolve_byprop

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nightdrive.attention.focus_index import FocusEstimator
from nightdrive.lsl.band_reader import STREAM_NAME, band_sums

BAR_SCALE = 30  # bar length = level * this (so 1.0 = 30 characters)
BAR_MAX = 90


def bar(level: float, pass_level: float) -> str:
    n = max(0, min(BAR_MAX, int(level * BAR_SCALE)))
    marker = int(pass_level * BAR_SCALE)
    cells = ["#" if i < n else " " for i in range(max(n, marker + 1))]
    cells[marker] = "|"
    return "".join(cells).rstrip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--pass-level",
        type=float,
        default=1.4,
        help="level marked with | (default 1.4)",
    )
    args = ap.parse_args()

    print(f"Looking for LSL stream '{STREAM_NAME}'...")
    streams = resolve_byprop("name", STREAM_NAME, timeout=10)
    if not streams:
        raise SystemExit("Stream not found. Is tools/gpype_alpha_stream.py running?")
    inlet = StreamInlet(streams[0])
    print(f"Connected: {inlet.info().channel_count()} channels. Ctrl+C to stop.")
    print("Calibrating your baseline (~23 s): keep your eyes open and sit still.\n")

    est = FocusEstimator()
    while True:
        sample, _ts = inlet.pull_sample(timeout=2.0)
        if sample is None:
            print("no data for 2 s")
            continue
        now = time.monotonic()
        state = est.update(now, band_sums(sample))
        ratio = est.index if est.index is not None else 0.0
        if not state.calibrated:
            pct = int(est.calibration_progress(now) * 100)
            print(f"calibrating {pct:3d}%   ratio {ratio:5.2f}")
            continue
        print(
            f"attention level {state.level:5.2f} ({(state.level - 1) * 100:+4.0f}%)  "
            f"ratio {ratio:5.2f}  {bar(state.level, args.pass_level)}"
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
