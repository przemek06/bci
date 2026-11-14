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
        assert f"scare_{ev.name}" in set(sfx.SOUNDS) | set(samples_mod.COMPOSITES), (
            ev.name
        )


def test_sounds_are_valid_audio():
    for name, x in sfx.build(SR).items():
        assert np.isfinite(x).all(), name
        assert 0.1 < np.abs(x).max() <= 1.0, (
            name
        )  # audible, never clipping the float range
        assert np.sqrt((x**2).mean()) > 0.03, name  # not near-silent


def test_synthesis_is_deterministic():
    a, b = sfx.build(SR, seed=3), sfx.build(SR, seed=3)
    assert all(np.array_equal(a[k], b[k]) for k in a)


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


def test_engine_loop_is_seamless():
    e = sfx.build(SR)["engine"]
    assert abs(e[0] - e[-1]) <= np.abs(np.diff(e)).max()


def test_volumes_are_sane():
    assert 0 < S.SFX_VOLUME <= 1 and 0 <= S.ENGINE_VOLUME <= 1


@requires_audio
def test_sfx_plays_and_mutes():
    pygame.mixer.init(SR, -16, 2)
    fx = sfx.Sfx(enabled=True)
    assert fx.ok
    assert set(sfx.SOUNDS) | set(sfx.SAMPLE_SOUNDS) | set(
        samples_mod.COMPOSITES
    ) <= set(fx.sounds)
    assert fx.play_scare("deer") is not None
    fx.toggle_mute()
    assert fx.play("alert") is None  # muted
    fx.engine(1.0)
    assert "engine" not in fx._loops  # engine stays off while muted
    fx.toggle_mute()
    fx.engine(1.0)
    assert "engine" in fx._loops
    fx.engine(0)
    assert "engine" not in fx._loops
    pygame.mixer.quit()


def test_disabled_sfx_is_a_noop():
    fx = sfx.Sfx(enabled=False)
    assert fx.play("alert") is None
    fx.engine(1.0)
    fx.stop_all()


@requires_audio
def test_all_sample_files_exist_and_are_levelled():
    from nightdrive import samples

    pygame.mixer.init(SR, -16, 2)
    for key, target_db in samples.SAMPLES.items():
        assert any((S.SFX_DIR / f"{key}{ext}").exists() for ext in (".wav", ".mp3")), (
            key
        )
        a = samples.load(key)
        assert a is not None and a.ndim == 2 and a.shape[1] == 2, key
        assert np.abs(a).max() <= 0.951, key  # never clips
        rms_db = 20 * np.log10(np.sqrt((a**2).mean()))
        assert rms_db <= target_db + 0.1, (
            key
        )  # at or below the target (peak-limited when quieter)
    pygame.mixer.quit()


def test_sample_tables_are_consistent():
    from nightdrive import samples

    for layers in samples.SCARE_LAYERS.values():
        for key, start in layers:
            assert key in samples.SAMPLES and start >= 0
    for name in samples.APPEAR.values():
        assert name in samples.COMPOSITES
    for parts in samples.COMPOSITES.values():
        for key, start in parts:
            assert key in samples.SAMPLES and start >= 0
    assert set(samples.SCARE_LAYERS) <= set(sfx.SOUNDS)


@requires_audio
def test_recorded_layers_make_the_scares_longer():
    pygame.mixer.init(SR, -16, 2)
    fx = sfx.Sfx(enabled=True)
    plain = sfx.build(SR)
    assert (
        fx.sounds["scare_truck"].get_length() > len(plain["scare_truck"]) / SR + 1.0
    )  # drone tail added
    for name in ("scare_deer", "scare_yeti", "scare_deep_one"):
        assert fx.sounds[name].get_length() > S.JUMPSCARE_TIME + 2.0, (
            name
        )  # recorded, with a drone tail
    pygame.mixer.quit()


def test_synthesised_sounds_left():
    """Tracks what is still synthetic, so removing one is a conscious step (see the list in the docs)."""
    assert set(sfx.SOUNDS) == {
        "scare_truck",
        "scare_chicken",
        "scare_scooter",
        "scare_trump",
        "alert",
        "riser",
        "saved",
        "click",
        "zap",
        "engine",
    }


@requires_audio
def test_loops_start_stop_and_respect_mute():
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
    fx.toggle_mute()
    fx.loop("panic", 0.5)
    assert not fx._loops  # muted: nothing starts
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
    monkeypatch.setattr(fx, "play", lambda name: played.append(name))
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
