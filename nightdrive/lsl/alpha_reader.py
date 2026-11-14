"""Reader for the `NightDriveAlpha` LSL stream (see tools/gpype_alpha_stream.py)."""

from collections.abc import Sequence

from .reader import StreamReader, StreamSample

STREAM_NAME = "NightDriveAlpha"

AlphaSample = StreamSample  # .value is relative alpha, ~0..1


def relative_alpha(sample: Sequence[float]) -> float:
    """Relative alpha from one stream sample laid out as (alpha, broad) per channel."""
    if len(sample) < 2 or len(sample) % 2:
        raise ValueError(f"expected (alpha, broad) pairs, got {len(sample)} values")
    alpha = sum(sample[0::2])
    broad = sum(sample[1::2])
    return alpha / broad if broad > 0 else 0.0


class AlphaReader(StreamReader):
    def __init__(self, stream_name: str = STREAM_NAME, maxlen: int = 1000) -> None:
        super().__init__(stream_name, relative_alpha, group=2, maxlen=maxlen)
