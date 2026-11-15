"""DEVELOPMENT MOCK: publish fake headset streams so the game can be tried without the Unicorn.

It publishes the same two LSL streams as tools/gpype_alpha_stream.py, in the same format:
    NightDriveAlpha   6 channels:  (alpha, broad) x 3 occipital channels       -> the eyes-closed ghost
    NightDriveBands  24 channels:  (theta, alpha, beta_low, beta_mid, beta_high, gamma) x 4 channels
                                                                                -> attention / focus
The game does not know the difference: run it as usual (`python -m nightdrive --eyes bci --attention bci`).
Nothing in the game refers to this file, so the real game is simply: start the real publisher
(tools/gpype_alpha_stream.py) instead of this script. If real streams are already up, this script
refuses to start so the two can never be mixed.

Sending to ANOTHER computer (instead of real data, for testing the receiving side):
    This script needs only `pip install pylsl` and never touches the game, so run it on any computer.
    LSL streams are visible to every computer on the same network, so the receiver just reads them
    as usual (the game, or `python tools/lsl_list_streams.py --samples 3` to check). Run
    `python tools/mock_eeg_streams.py --auto --no-keys` for a hands-free demo that cycles through
    calm / focused / drowsy / eyes closed. If the other computer sees nothing: same subnet? firewall
    (allow python)? and note that guest Wi-Fi often blocks device-to-device traffic and multicast.

Control the "player" with keys in THIS window (Windows: single keys; elsewhere: letter + Enter):
    c   toggle eyes closed        (alpha jumps: the ghost can be passed)
    f   focused                   (beta + gamma up: focus passes a quick-time event)
    d   drowsy / distracted       (beta + gamma down: focus does not pass)
    n   normal / calm             (the level the calibration recorded)
    q   quit
"""

import argparse
import random
import socket
import sys
import threading
import time

from pylsl import StreamInfo, StreamOutlet, resolve_byprop

ALPHA_STREAM = "NightDriveAlpha"
BANDS_STREAM = "NightDriveBands"
RATE_HZ = 4.0

OCC_CHANNELS = 3  # PO7, Oz, PO8
ATT_CHANNELS = 4  # C3, Cz, C4, Pz
BANDS = ["4-8Hz", "8-12Hz", "13-16Hz", "16-20Hz", "20-30Hz", "30-45Hz"]

# calm values per attention channel: (theta, alpha, beta_low, beta_mid, beta_high, gamma);
# beta + gamma add up to the alpha value, so the calm attention value is 1.0
CALM = (400.0, 100.0, 30.0, 30.0, 30.0, 10.0)
STATE_GAIN = {"calm": 1.0, "focused": 2.2, "drowsy": 0.45}  # multiplies beta and gamma
BROAD = 3000.0  # broadband power per occipital channel
ALPHA_SHARE = {
    "open": 0.15,
    "closed": 0.60,
}  # relative alpha with the eyes open / closed


def alpha_sample(rng: random.Random, eyes_closed: bool, noise: float) -> list[float]:
    """(alpha, broad) for each occipital channel."""
    share = ALPHA_SHARE["closed" if eyes_closed else "open"]
    out = []
    for _ in range(OCC_CHANNELS):
        broad = BROAD * rng.lognormvariate(0, noise)
        out += [share * broad * rng.lognormvariate(0, noise), broad]
    return out


def bands_sample(
    rng: random.Random, state: str, eyes_closed: bool, noise: float
) -> list[float]:
    """(theta, alpha, beta_low, beta_mid, beta_high, gamma) for each attention channel."""
    gain = STATE_GAIN[state]
    out = []
    for _ in range(ATT_CHANNELS):
        theta, alpha, bl, bm, bh, gamma = CALM
        if eyes_closed:  # closed eyes: much more alpha
            alpha, theta = alpha * 4.0, theta * 1.2
        values = (theta, alpha, bl * gain, bm * gain, bh * gain, gamma * gain)
        out += [v * rng.lognormvariate(0, noise) for v in values]
    return out


def make_outlet(name: str, labels: list[str], source_id: str) -> StreamOutlet:
    info = StreamInfo(name, "EEG", len(labels), RATE_HZ, "float32", source_id)
    channels = info.desc().append_child("channels")
    for label in labels:
        channels.append_child("channel").append_child_value("label", label)
    return StreamOutlet(info)


class Controls:
    """The mock player: state (calm / focused / drowsy) and whether the eyes are closed."""

    def __init__(self):
        self.state = "calm"
        self.eyes_closed = False
        self.quit = False

    def press(self, key: str) -> None:
        key = key.lower()
        if key == "c":
            self.eyes_closed = not self.eyes_closed
        elif key == "f":
            self.state = "focused"
        elif key == "d":
            self.state = "drowsy"
        elif key == "n":
            self.state = "calm"
        elif key == "q":
            self.quit = True
        else:
            return
        print(f"  -> {self.describe()}", flush=True)

    def apply(self, state: str, eyes_closed: bool) -> None:
        """Set the state from the --auto schedule (prints only when something changes)."""
        if (state, eyes_closed) != (self.state, self.eyes_closed):
            self.state, self.eyes_closed = state, eyes_closed
            print(f"  -> {self.describe()}  (auto)", flush=True)

    def describe(self) -> str:
        return f"attention: {self.state.upper()}   eyes: {'CLOSED' if self.eyes_closed else 'open'}"


# --auto: a hands-free scenario, repeated forever: (attention state, eyes closed, seconds).
# It starts calm for long enough to record a baseline (the game's calibration takes about 25 s).
AUTO_SCHEDULE = (
    ("calm", False, 30.0),
    ("focused", False, 8.0),
    ("calm", False, 12.0),
    ("drowsy", False, 8.0),
    ("calm", True, 8.0),  # eyes closed (the ghost)
    ("calm", False, 10.0),
)


def auto_state(t: float) -> tuple[str, bool]:
    """The scripted (state, eyes_closed) `t` seconds after the start of the --auto scenario."""
    total = sum(seconds for _, _, seconds in AUTO_SCHEDULE)
    t %= total
    for state, closed, seconds in AUTO_SCHEDULE:
        if t < seconds:
            return state, closed
        t -= seconds
    return AUTO_SCHEDULE[-1][0], AUTO_SCHEDULE[-1][1]


def local_address() -> str:
    """This computer's address on the network the default route uses (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "unknown"


def start_key_reader(controls: Controls) -> None:
    try:
        import msvcrt  # Windows: react to single key presses

        def loop():
            while not controls.quit:
                if msvcrt.kbhit():
                    controls.press(msvcrt.getwch())
                time.sleep(0.03)

    except ImportError:  # elsewhere: type a letter and press Enter

        def loop():
            for line in sys.stdin:
                for ch in line.strip():
                    controls.press(ch)

    threading.Thread(target=loop, daemon=True).start()


def real_streams_present() -> list[str]:
    return [
        n
        for n in (ALPHA_STREAM, BANDS_STREAM)
        if resolve_byprop("name", n, timeout=1.5)
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--noise",
        type=float,
        default=0.12,
        help="relative noise on every value (default 0.12)",
    )
    ap.add_argument(
        "--seconds",
        type=float,
        help="stop after N seconds (default: until you press q)",
    )
    ap.add_argument("--seed", type=int, help="seed for repeatable data")
    ap.add_argument(
        "--auto",
        action="store_true",
        help="hands-free: cycle calm / focused / drowsy / eyes closed on a schedule",
    )
    ap.add_argument(
        "--no-keys",
        action="store_true",
        help="do not read the keyboard (unattended or background running)",
    )
    args = ap.parse_args()

    found = real_streams_present()
    if found:
        raise SystemExit(
            f"Streams already exist ({', '.join(found)}): a real publisher (or another mock) "
            "is running. Not starting the mock, so real and fake data never mix."
        )

    rng = random.Random(args.seed)
    alpha_labels = [
        f"Ch{c + 1:02d}:{b}" for c in range(OCC_CHANNELS) for b in ("8-12Hz", "2-30Hz")
    ]
    band_labels = [f"Ch{c + 1:02d}:{b}" for c in range(ATT_CHANNELS) for b in BANDS]
    alpha_out = make_outlet(ALPHA_STREAM, alpha_labels, "night-drive-mock-alpha")
    bands_out = make_outlet(BANDS_STREAM, band_labels, "night-drive-mock-bands")

    controls = Controls()
    print(__doc__.split("Control the")[0].strip().split("\n", 1)[0])
    print(
        "MOCK headset streams are running (fake data). Keys here: c eyes closed | f focused | d drowsy | n calm | q quit"
    )
    print(f"  -> {controls.describe()}", flush=True)
    print(
        f"Visible on the network from {socket.gethostname()} ({local_address()}): on another computer "
        "run `python tools/lsl_list_streams.py --samples 3` to check.",
        flush=True,
    )
    if args.auto:
        print(
            "AUTO scenario: calm 30 s, focused 8 s, calm 12 s, drowsy 8 s, eyes closed 8 s, calm 10 s, repeat.",
            flush=True,
        )
    if not args.no_keys:
        start_key_reader(controls)

    start = time.monotonic()
    nxt = start
    while not controls.quit and (
        args.seconds is None or time.monotonic() - start < args.seconds
    ):
        if args.auto:
            controls.apply(*auto_state(time.monotonic() - start))
        alpha_out.push_sample(alpha_sample(rng, controls.eyes_closed, args.noise))
        bands_out.push_sample(
            bands_sample(rng, controls.state, controls.eyes_closed, args.noise)
        )
        nxt += 1.0 / RATE_HZ
        time.sleep(max(0.0, nxt - time.monotonic()))
    print("mock stopped.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
