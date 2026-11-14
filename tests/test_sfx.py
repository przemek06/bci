import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pygame
from helpers import requires_audio

from nightdrive import samples as samples_mod
from nightdrive import settings as S
from nightdrive import sfx
from nightdrive.events import CATALOGUE

SR = 44100


def test_every_event_has_a_scare_sound():
    for ev in CATALOGUE:
        assert f"scare_{ev.name}" in samples_mod.COMPOSITES, ev.name


def test_nothing_is_synthesised_any_more():
    """Every sound is a recording; the numpy synthesiser (and its fallbacks) were removed."""
    assert not hasattr(sfx, "build") and not hasattr(sfx, "SOUNDS")
    for name in ("alert", "click"):  # the old synthesised fallbacks
        assert name not in sfx.SAMPLE_SOUNDS and name not in samples_mod.COMPOSITES
    for name in ("riser", "saved", "zap"):  # now recorded
        assert name in sfx.SAMPLE_SOUNDS or name in samples_mod.COMPOSITES


@requires_audio
def test_recorded_deer_scare_is_piercing_and_long():
    pygame.mixer.init(SR, -16, 2)
    fx = sfx.Sfx(enabled=True)
    snd = fx.sounds["scare_deer"]
    assert snd.get_length() >= S.JUMPSCARE_TIME
    a = (
        pygame.sndarray.array(snd).astype(float).mean(axis=1)[: 3 * SR]
    )  # the scare itself, without the drone tail
    spec = np.abs(np.fft.rfft(a)) ** 2
    freqs = np.fft.rfftfreq(len(a), 1 / SR)
    assert spec[freqs > 800].sum() / spec.sum() > 0.2  # real screech energy up high
    pygame.mixer.quit()


def test_volumes_are_sane():
    assert 0 < S.SFX_VOLUME <= 1 and 0 <= S.ENGINE_VOLUME <= 1


@requires_audio
def test_sfx_plays_and_loops_follow_speed():
    pygame.mixer.init(SR, -16, 2)
    fx = sfx.Sfx(enabled=True)
    assert fx.ok
    assert set(sfx.SAMPLE_SOUNDS) | set(samples_mod.COMPOSITES) <= set(fx.sounds)
    assert fx.play_scare("deer") is not None
    assert not hasattr(fx, "toggle_mute")  # there is no player-facing mute any more
    fx.engine(1.0)
    assert "engine" in fx._loops
    fx.engine(0)
    assert "engine" not in fx._loops
    pygame.mixer.quit()


def test_disabled_sfx_is_a_noop():
    fx = sfx.Sfx(enabled=False)
    assert fx.play("gasp") is None
    fx.engine(1.0)
    fx.stop_all()


@requires_audio
def test_all_sample_files_exist_and_are_levelled():
    pygame.mixer.init(SR, -16, 2)
    for key, target_db in samples_mod.SAMPLES.items():
        assert any((S.SFX_DIR / f"{key}{ext}").exists() for ext in (".wav", ".mp3")), (
            key
        )
        a = samples_mod.load(key)
        assert a is not None and a.ndim == 2 and a.shape[1] == 2, key
        assert np.abs(a).max() <= 0.951, key  # never clips
        rms_db = 20 * np.log10(np.sqrt((a**2).mean()))
        assert rms_db <= target_db + (0.5 if key in samples_mod.LOOPS else 0.1), (
            key
        )  # at or below the target (peak-limited when quieter)
    pygame.mixer.quit()


def test_sample_tables_are_consistent():
    for name in samples_mod.APPEAR.values():
        assert name in samples_mod.COMPOSITES
    for name, parts in samples_mod.COMPOSITES.items():
        for key, start, *gain in parts:
            assert key in samples_mod.SAMPLES, (name, key)
            assert start >= 0 and (not gain or 0 < gain[0] <= 1), (name, key)
    for key in samples_mod.TRIMS:
        assert key in samples_mod.SAMPLES
    assert set(sfx.COMPOSITE_VOLUME) >= {
        n for n in samples_mod.COMPOSITES if n.startswith("scare_")
    }


def test_layer_gain_is_applied():
    base = np.zeros((0, 2), dtype=np.float32)
    ones = np.ones((100, 2), dtype=np.float32)
    quiet = sfx._layer(base, ones, 0.0, SR, 0.5)
    assert quiet.max() == 0.5 and len(quiet) == 100
    mixed = sfx._layer(quiet, ones, 0.5, SR)  # starts later: the sound grows
    assert len(mixed) == SR // 2 + 100


@requires_audio
def test_riser_is_the_cropped_swell_and_scares_have_length():
    pygame.mixer.init(SR, -16, 2)
    riser = samples_mod.load("riser")
    assert abs(len(riser) / SR - 1.5) < 0.01  # just the 1.5 s before the peak
    assert (
        abs(riser[0]).max() < 0.05 and np.abs(riser[-1]).max() < 0.05
    )  # faded in and out
    fx = sfx.Sfx(enabled=True)
    for ev in CATALOGUE:
        assert fx.sounds[f"scare_{ev.name}"].get_length() >= 1.5, ev.name
    for name in ("scare_deer", "scare_yeti", "scare_deep_one", "scare_truck"):
        assert fx.sounds[name].get_length() > S.JUMPSCARE_TIME + 2.0, name  # drone tail
    pygame.mixer.quit()


@requires_audio
def test_loops_start_and_stop():
    pygame.mixer.init(SR, -16, 2)
    fx = sfx.Sfx(enabled=True)
    fx.loop("panic", 0.5)
    fx.loop("buzz", 0.5)
    fx.ambience()
    assert {"panic", "buzz", "frogs"} <= set(fx._loops)
    fx.stop_loop("panic")
    assert "panic" not in fx._loops
    fx.stop_loops()
    assert not fx._loops
    pygame.mixer.quit()


def test_appear_saved_and_lights_sounds_do_not_crash():
    pygame.mixer.init(SR, -16, 2)
    fx = sfx.Sfx(enabled=True)
    for ev in CATALOGUE:
        fx.play_appear(ev.name)
        fx.play_saved(ev.name)
    fx.play_lights(True)
    fx.play_lights(False)
    pygame.mixer.quit()


@requires_audio
def test_ambient_oneshots_fire_on_schedule(monkeypatch):
    pygame.mixer.init(SR, -16, 2)
    fx = sfx.Sfx(enabled=True)
    played = []
    monkeypatch.setattr(fx, "play", lambda name, pan=None: played.append(name))
    fx.ambient_tick(S.AMBIENT_ONESHOT_RANGE[0] - 1)
    assert not played or S.AMBIENT_ONESHOT_RANGE[0] > 0 and fx._amb_timer < 1
    fx.ambient_tick(S.AMBIENT_ONESHOT_RANGE[1] + 1)
    assert played and played[-1].startswith("amb_")
    monkeypatch.setattr(S, "AMBIENT_ONESHOTS", False)
    played.clear()
    fx.ambient_tick(1000)
    assert not played
    pygame.mixer.quit()


@requires_audio
def test_headlight_switch_has_three_variants_each_way():
    pygame.mixer.init(SR, -16, 2)
    fx = sfx.Sfx(enabled=True)
    for state in ("on", "off"):
        assert {f"switch_{state}_{i}" for i in (1, 2, 3)} <= set(fx.sounds)
    fx.play_lights(True)
    fx.play_lights(False)
    pygame.mixer.quit()
