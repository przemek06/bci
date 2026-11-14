"""Background reader for the raw `NightDriveEEG` LSL stream (see tools/gpype_eeg_stream.py).

The stream carries filtered occipital EEG, one sample per time step, one value per channel (the
tool sends PO7, Oz, PO8). Pulling runs in a daemon thread so the game loop never blocks on the
network. The main thread only calls `window()` and reads `connected`.
"""

import threading
import time

import numpy as np
from pylsl import StreamInlet, resolve_byprop

STREAM_NAME = "NightDriveEEG"
CONNECTED_WITHIN_S = 2.0
DEFAULT_RATE = 250.0  # the Unicorn's sampling rate, used if the stream does not say


class EegReader:
    def __init__(self, stream_name: str = STREAM_NAME, keep_s: float = 10.0) -> None:
        self.stream_name = stream_name
        self.keep_s = keep_s
        self.sampling_rate = DEFAULT_RATE
        self.channel_count = 0
        self._buf = np.zeros(
            (0, 0)
        )  # ring buffer, (samples, channels); sized once the stream is known
        self._write = 0  # next write position
        self._filled = 0  # how many valid samples the buffer holds
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_rx: float | None = None

    def start(self) -> None:
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, name="eeg-reader", daemon=True
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

    def window(self, seconds: float) -> np.ndarray | None:
        """The latest `seconds` of EEG as (channels, samples), oldest first. None until enough has arrived."""
        n = round(seconds * self.sampling_rate)
        with self._lock:
            if self._filled < n or n <= 0:
                return None
            size = len(self._buf)
            idx = (np.arange(self._write - n, self._write)) % size
            return self._buf[idx].T.copy()

    # --- the thread -------------------------------------------------------------------

    def _open(self) -> StreamInlet | None:
        streams = resolve_byprop("name", self.stream_name, timeout=1.0)
        if not streams:
            return None
        inlet = StreamInlet(streams[0], max_buflen=int(self.keep_s))
        info = inlet.info()
        rate = info.nominal_srate()
        with self._lock:
            self.sampling_rate = rate if rate and rate > 0 else DEFAULT_RATE
            self.channel_count = info.channel_count()
            size = int(self.keep_s * self.sampling_rate) + 1
            self._buf = np.zeros((size, self.channel_count))
            self._write = self._filled = 0
        return inlet

    def _run(self) -> None:
        inlet: StreamInlet | None = None
        while not self._stop.is_set():
            if inlet is None:
                inlet = self._open()
                if inlet is None:
                    continue
            samples, _stamps = inlet.pull_chunk(timeout=0.2)
            if not samples:
                continue
            chunk = np.asarray(samples, dtype=float)
            with self._lock:
                size = len(self._buf)
                if len(chunk) >= size:  # more than the buffer holds: keep the newest
                    chunk = chunk[-size:]
                idx = (self._write + np.arange(len(chunk))) % size
                self._buf[idx] = chunk
                self._write = (self._write + len(chunk)) % size
                self._filled = min(size, self._filled + len(chunk))
            self._last_rx = time.monotonic()
