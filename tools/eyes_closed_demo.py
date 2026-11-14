"""Try the eyes-closed detector on the live alpha stream, no game needed.

Start tools/gpype_alpha_stream.py first, then run this from the repo root:
    python tools/eyes_closed_demo.py

Flow: calibrate with eyes open, then a few rounds of rest (eyes open) followed by
a "CLOSE YOUR EYES" challenge. Close them for 3 s before the deadline or you die.
"""

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nightdrive.attention.eyes_closed import EyesClosedConfig, EyesClosedDetector
from nightdrive.lsl.alpha_reader import AlphaReader

TICK_S = 0.05
SETTLE_S = 2.0  # ignore the first seconds of calibration (FFT window warm-up)


def pump(reader: AlphaReader, det: EyesClosedDetector):
    """Feed all new samples to the detector; return (state, values_fed)."""
    values = []
    state = None
    for s in reader.drain():
        state = det.update(s.t, s.value)
        values.append(s.value)
    return state or det.update(time.monotonic()), values


def status(line: str) -> None:
    print("\r" + line.ljust(78), end="", flush=True)


def calibrate(reader: AlphaReader, det: EyesClosedDetector, seconds: float) -> None:
    print(
        f"\nCALIBRATION: keep your eyes OPEN and look at the screen for {seconds:g} s."
    )
    start = time.monotonic()
    values: list[float] = []
    reader.drain()
    while (elapsed := time.monotonic() - start) < seconds:
        for s in reader.drain():
            if elapsed > SETTLE_S:
                values.append(s.value)
        status(f"calibrating... {seconds - elapsed:4.1f}s   samples: {len(values)}")
        time.sleep(TICK_S)
    det.calibrate(values)
    print(
        f"\nbaseline {det.baseline:.2f}  ->  closed threshold {det.threshold:.2f}"
        f"  (release {det.release:.2f})"
    )


def rest(reader, det, seconds: float) -> int:
    """Eyes-open rest period. Returns how many ticks were wrongly seen as 'closed'."""
    print("\nEyes open, relax...")
    end = time.monotonic() + seconds
    false_ticks = 0
    while time.monotonic() < end:
        state, _ = pump(reader, det)
        false_ticks += state.closed
        status(
            f"score {state.score:.2f} / thr {state.threshold:.2f}   {'(false trigger)' if state.closed else ''}"
        )
        time.sleep(TICK_S)
    return false_ticks


def challenge(reader, det, hold_s: float, deadline_s: float) -> bool:
    print(f"\n*** A GHOST! CLOSE YOUR EYES for {hold_s:g} s! ***")
    det.reset()
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        state, _ = pump(reader, det)
        if state.passed:
            print("\nYou kept your eyes closed. The ghost passes. You live.")
            return True
        bar = "#" * int(min(state.held_s / hold_s, 1) * 20)
        status(
            f"score {state.score:.2f} / thr {state.threshold:.2f}   held {state.held_s:3.1f}s [{bar:<20}]"
        )
        time.sleep(TICK_S)
    print("\nYou kept your eyes open. The ghost got you. DEAD.")
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument(
        "--calibration", type=float, default=12.0, help="eyes-open calibration seconds"
    )
    ap.add_argument(
        "--hold", type=float, default=3.0, help="seconds eyes must stay closed"
    )
    ap.add_argument(
        "--deadline",
        type=float,
        default=8.0,
        help="seconds allowed to pass a challenge",
    )
    args = ap.parse_args()

    reader = AlphaReader()
    reader.start()
    print(
        "Waiting for the NightDriveAlpha stream (is tools/gpype_alpha_stream.py running?)..."
    )
    t0 = time.monotonic()
    while not reader.connected:
        if time.monotonic() - t0 > 20:
            reader.stop()
            raise SystemExit("No stream received.")
        time.sleep(0.1)

    det = EyesClosedDetector(EyesClosedConfig(hold_s=args.hold))
    try:
        calibrate(reader, det, args.calibration)
        results, false_ticks = [], 0
        for _ in range(args.rounds):
            false_ticks += rest(reader, det, random.uniform(5, 9))
            results.append(challenge(reader, det, args.hold, args.deadline))
        print(
            f"\nPassed {sum(results)}/{len(results)} challenges; false 'closed' ticks while resting: {false_ticks}"
        )
    except KeyboardInterrupt:
        pass
    finally:
        reader.stop()


if __name__ == "__main__":
    main()
