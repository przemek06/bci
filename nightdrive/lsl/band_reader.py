"""Reader for the `NightDriveBands` LSL stream (see tools/gpype_alpha_stream.py).

The stream carries (theta, alpha, beta_low, beta_mid, beta_high, gamma) band power per analysed
channel. This reader sums each band over channels, so a sample's value is a 6-tuple in that order.
"""

from collections.abc import Sequence

from .reader import StreamReader, StreamSample

STREAM_NAME = "NightDriveBands"
BANDS = ("theta", "alpha", "beta_low", "beta_mid", "beta_high", "gamma")

BandSample = (
    StreamSample  # .value is a tuple of channel-summed band powers, in BANDS order
)


def band_sums(sample: Sequence[float]) -> tuple[float, ...]:
    n = len(BANDS)
    if len(sample) < n or len(sample) % n:
        raise ValueError(
            f"expected groups of {n} band powers, got {len(sample)} values"
        )
    return tuple(sum(sample[i::n]) for i in range(n))


class BandReader(StreamReader):
    def __init__(self, stream_name: str = STREAM_NAME, maxlen: int = 1000) -> None:
        super().__init__(stream_name, band_sums, group=len(BANDS), maxlen=maxlen)
