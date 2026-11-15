"""The development mock (tools/mock_eeg_streams.py) must look exactly like the real publisher to the game."""

import random
import statistics
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mock_eeg_streams as mock

from nightdrive.attention.focus_index import engagement_index
from nightdrive.lsl.alpha_reader import relative_alpha
from nightdrive.lsl.band_reader import band_sums


def mean_attention(state, eyes_closed=False, n=300):
    rng = random.Random(1)
    return statistics.mean(
        engagement_index(band_sums(mock.bands_sample(rng, state, eyes_closed, 0.12)))
        for _ in range(n)
    )


def mean_relative_alpha(eyes_closed, n=300):
    rng = random.Random(1)
    return statistics.mean(
        relative_alpha(mock.alpha_sample(rng, eyes_closed, 0.12)) for _ in range(n)
    )


def test_the_samples_have_the_real_stream_shapes():
    rng = random.Random(0)
    assert len(mock.alpha_sample(rng, False, 0.1)) == 6  # (alpha, broad) x 3
    assert len(mock.bands_sample(rng, "calm", False, 0.1)) == 24  # 6 bands x 4 channels


def test_calm_is_the_baseline_focused_is_higher_and_drowsy_is_lower():
    calm = mean_attention("calm")
    assert calm == pytest.approx(1.0, abs=0.12)
    assert mean_attention("focused") > calm * 1.8  # clearly passes a focus check
    assert mean_attention("drowsy") < calm * 0.6  # clearly does not


def test_closed_eyes_raise_relative_alpha_a_lot():
    assert mean_relative_alpha(False) == pytest.approx(0.15, abs=0.04)
    assert mean_relative_alpha(True) > 0.45


def test_the_mock_refuses_to_start_next_to_real_streams(monkeypatch):
    monkeypatch.setattr(mock, "resolve_byprop", lambda *a, **k: ["a stream"])
    monkeypatch.setattr(sys, "argv", ["mock_eeg_streams.py"])
    with pytest.raises(SystemExit) as exc:
        mock.main()
    assert "never mix" in str(exc.value)


def test_the_game_never_refers_to_the_mock():
    for path in (ROOT / "nightdrive").rglob("*.py"):
        assert "mock_eeg" not in path.read_text(encoding="utf-8"), path
