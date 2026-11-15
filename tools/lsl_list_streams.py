"""List the LSL streams visible on the network, and optionally read a few samples from each.

Run it on the RECEIVING computer to check that the data from another computer arrives (for example
from tools/mock_eeg_streams.py, or the real tools/gpype_alpha_stream.py). It needs only
`pip install pylsl`, not the game.

    python tools/lsl_list_streams.py                  # list everything LSL can see
    python tools/lsl_list_streams.py --samples 3      # ...and read 3 samples from each stream
    python tools/lsl_list_streams.py --name NightDrive --wait 6
"""

import argparse
import socket
import time

from pylsl import StreamInlet, resolve_streams


def describe(info, this_host: str) -> str:
    where = (
        "this computer"
        if info.hostname() == this_host
        else f"another computer ({info.hostname()})"
    )
    return (
        f"{info.name():<20} type={info.type():<6} channels={info.channel_count():<3} "
        f"rate={info.nominal_srate():g} Hz   from: {where}"
    )


def read_samples(info, count: int) -> None:
    inlet = StreamInlet(info, max_buflen=5)
    start = time.monotonic()
    values = []
    while len(values) < count and time.monotonic() - start < 8:
        sample, _ts = inlet.pull_sample(timeout=1.0)
        if sample is not None:
            values.append(sample)
    inlet.close_stream()
    if not values:
        print(
            "    no samples arrived (the stream is listed but the data connection failed: firewall?)"
        )
        return
    rate = (
        (len(values) - 1) / max(time.monotonic() - start, 1e-6)
        if len(values) > 1
        else 0.0
    )
    first = [round(v, 1) for v in values[0][:6]]
    print(
        f"    got {len(values)} samples, about {rate:.1f}/s; first values: {first} ..."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--wait",
        type=float,
        default=3.0,
        help="seconds to look for streams (default 3)",
    )
    ap.add_argument(
        "--name", default="", help="only show streams whose name contains this text"
    )
    ap.add_argument(
        "--samples",
        type=int,
        default=0,
        help="also read this many samples from each stream",
    )
    args = ap.parse_args()

    this_host = socket.gethostname()
    print(
        f"Looking for LSL streams for {args.wait:g} s (this computer: {this_host})..."
    )
    streams = [s for s in resolve_streams(wait_time=args.wait) if args.name in s.name()]
    if not streams:
        print("No LSL streams found. Check that:")
        print(
            "  - the sender is running (tools/mock_eeg_streams.py or tools/gpype_alpha_stream.py)"
        )
        print("  - both computers are on the same network / subnet")
        print("  - the firewall allows Python (LSL uses UDP multicast, then TCP)")
        print("  - it is not a guest Wi-Fi that isolates devices or blocks multicast")
        raise SystemExit(1)
    for info in streams:
        print(f"  {describe(info, this_host)}")
        if args.samples:
            read_samples(info, args.samples)


if __name__ == "__main__":
    main()
