"""Print the relative alpha from the `NightDriveAlpha` LSL stream.

Use it to check the headset: relative alpha should be low with eyes open and
jump when you close your eyes. Start tools/gpype_alpha_stream.py first.
"""

import numpy as np
from pylsl import StreamInlet, resolve_byprop

STREAM_NAME = "NightDriveAlpha"


def main() -> None:
    print(f"Looking for LSL stream '{STREAM_NAME}'...")
    streams = resolve_byprop("name", STREAM_NAME, timeout=10)
    if not streams:
        raise SystemExit("Stream not found. Is tools/gpype_alpha_stream.py running?")
    inlet = StreamInlet(streams[0])
    n = inlet.info().channel_count()
    print(f"Connected: {n} channels. Ctrl+C to stop.")

    while True:
        sample, _ts = inlet.pull_sample(timeout=2.0)
        if sample is None:
            print("no data for 2 s")
            continue
        # Layout: (alpha, broad) per analysed channel.
        values = np.asarray(sample, dtype=float).reshape(-1, 2)
        alpha, broad = values[:, 0].sum(), values[:, 1].sum()
        rel = alpha / broad if broad > 0 else 0.0
        print(f"relative alpha {rel:5.2f}  {'#' * int(rel * 60)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
