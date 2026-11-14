"""Print the relative high beta from the `NightDriveBands` LSL stream.

Like tools/lsl_alpha_print.py, for high beta (20-30 Hz, one of the two bands in the
attention index). Relative high beta = high beta / (all six bands: theta, alpha, low / mid /
high beta, gamma), summed over the analysed channels, so it is a share between 0 and 1 and does not
depend on the overall signal size. The bar shows how much; the number in brackets is the
average over the last 5 s. Start tools/gpype_alpha_stream.py first.
"""

import time
from collections import deque

import numpy as np
from pylsl import StreamInlet, resolve_byprop

STREAM_NAME = "NightDriveBands"
BAND = 4  # position in (theta, alpha, beta_low, beta_mid, beta_high, gamma)
AVG_SECONDS = 5.0
BAR_SCALE = 60  # bar length = relative value * this


def main() -> None:
    print(f"Looking for LSL stream '{STREAM_NAME}'...")
    streams = resolve_byprop("name", STREAM_NAME, timeout=10)
    if not streams:
        raise SystemExit("Stream not found. Is tools/gpype_alpha_stream.py running?")
    inlet = StreamInlet(streams[0])
    n = inlet.info().channel_count()
    print(f"Connected: {n} channels. Ctrl+C to stop.")

    recent: deque[tuple[float, float]] = deque()
    while True:
        sample, _ts = inlet.pull_sample(timeout=2.0)
        if sample is None:
            print("no data for 2 s")
            continue
        # Layout: (theta, alpha, beta_low, beta_mid, beta_high, gamma) per analysed channel.
        sums = np.asarray(sample, dtype=float).reshape(-1, 6).sum(axis=0)
        total = sums.sum()
        rel = sums[BAND] / total if total > 0 else 0.0
        now = time.monotonic()
        recent.append((now, rel))
        while recent and recent[0][0] < now - AVG_SECONDS:
            recent.popleft()
        avg = sum(v for _, v in recent) / len(recent)
        print(
            f"relative beta-high {rel:5.2f} (avg {avg:4.2f})  {'#' * int(rel * BAR_SCALE)}"
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
