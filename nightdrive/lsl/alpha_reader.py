"""Background reader for the `NightDriveAlpha` LSL stream (see tools/gpype_alpha_stream.py).

Pulling runs in a daemon thread so the game loop never blocks on the network.
The main thread only calls `latest()` / `drain()` / `connected`.
"""

import threading
import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

from pylsl import StreamInlet, resolve_byprop

STREAM_NAME = "NightDriveAlpha"
CONNECTED_WITHIN_S = 2.0


@dataclass(frozen=True)
class AlphaSample:
    t: float  # game clock (time.monotonic) when the sample was received
    lsl_t: float  # LSL timestamp, for alignment with the EEG recording
    value: float  # relative alpha, ~0..1


def relative_alpha(sample: Sequence[float]) -> float:
    """Relative alpha from one stream sample laid out as (alpha, broad) per channel."""
    if len(sample) < 2 or len(sample) % 2:
        raise ValueError(f"expected (alpha, broad) pairs, got {len(sample)} values")
    alpha = sum(sample[0::2])
    broad = sum(sample[1::2])
    return alpha / broad if broad > 0 else 0.0


class AlphaReader:
    def __init__(self, stream_name: str = STREAM_NAME, maxlen: int = 1000) -> None:
        self.stream_name = stream_name
        self._buf: deque[AlphaSample] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_rx: float | None = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._run, name="alpha-reader", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    @property
    def connected(self) -> bool:
        """True while samples are arriving."""
        last = self._last_rx
        return last is not None and time.monotonic() - last <= CONNECTED_WITHIN_S

    def latest(self) -> AlphaSample | None:
        with self._lock:
            return self._buf[-1] if self._buf else None

    def drain(self) -> list[AlphaSample]:
        """Return and remove everything received since the last call."""
        with self._lock:
            out = list(self._buf)
            self._buf.clear()
        return out

    def _run(self) -> None:
        inlet: StreamInlet | None = None
        while not self._stop.is_set():
            if inlet is None:
                streams = resolve_byprop("name", self.stream_name, timeout=1.0)
                if not streams:
                    continue
                inlet = StreamInlet(streams[0], max_buflen=5)
                if inlet.info().channel_count() % 2:
                    inlet.close_stream()
                    inlet = None
                    self._stop.wait(1.0)
                    continue
            samples, stamps = inlet.pull_chunk(timeout=0.2)
            if not samples:
                continue
            now = time.monotonic()
            new = [
                AlphaSample(t=now, lsl_t=ts, value=relative_alpha(s))
                for s, ts in zip(samples, stamps, strict=True)
            ]
            with self._lock:
                self._buf.extend(new)
            self._last_rx = now
