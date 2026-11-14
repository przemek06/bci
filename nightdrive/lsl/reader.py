"""Generic background reader for an LSL stream of float vectors.

Pulling runs in a daemon thread so the game loop never blocks on the network.
The main thread only calls `latest()` / `drain()` / `connected`.

`parse` turns one raw stream sample (a list of floats) into whatever value the
consumer wants (e.g. relative alpha, band-power sums). `group` is the number of
values that belong together, e.g. 2 for (alpha, broad) per channel: streams whose
channel count is not a multiple of it are ignored.
"""

import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from pylsl import StreamInlet, resolve_byprop

CONNECTED_WITHIN_S = 2.0


@dataclass(frozen=True)
class StreamSample:
    t: float  # game clock (time.monotonic) when the sample was received
    lsl_t: float  # LSL timestamp, for alignment with the EEG recording
    value: Any  # result of `parse`


class StreamReader:
    def __init__(
        self,
        stream_name: str,
        parse: Callable[[Sequence[float]], Any],
        group: int = 1,
        maxlen: int = 1000,
    ) -> None:
        self.stream_name = stream_name
        self._parse = parse
        self._group = group
        self._buf: deque[StreamSample] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_rx: float | None = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._run, name=f"lsl-{self.stream_name}", daemon=True
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

    def latest(self) -> StreamSample | None:
        with self._lock:
            return self._buf[-1] if self._buf else None

    def drain(self) -> list[StreamSample]:
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
                if inlet.info().channel_count() % self._group:
                    inlet.close_stream()
                    inlet = None
                    self._stop.wait(1.0)
                    continue
            samples, stamps = inlet.pull_chunk(timeout=0.2)
            if not samples:
                continue
            now = time.monotonic()
            new = [
                StreamSample(t=now, lsl_t=ts, value=self._parse(s))
                for s, ts in zip(samples, stamps, strict=True)
            ]
            with self._lock:
                self._buf.extend(new)
            self._last_rx = now
