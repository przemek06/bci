"""Procedural sound effects, synthesised with numpy (no audio files).

Run `python -m nightdrive.sfx` to audition every sound. The jump-scare sounds are LOUD on purpose:
lower your system volume first, and use SFX_VOLUME in settings.py to scale them.
"""

import random

import numpy as np
import pygame

from . import samples
from . import settings as S

TAU = 2 * np.pi


# --- small DSP toolbox -------------------------------------------------------------------


def _time(dur, sr):
    return np.arange(int(dur * sr)) / sr


def _phase(freq, sr):
    """Phase of an oscillator whose frequency (Hz) may change per sample."""
    return TAU * np.cumsum(freq) / sr


def _saw(ph):
    return 2 * ((ph / TAU) % 1.0) - 1


def _square(ph):
    return np.sign(np.sin(ph))


def _unit(x):
    peak = np.max(np.abs(x))
    return x / peak if peak > 0 else x


def _band(x, lo, hi, sr):
    """Brick-wall band-pass via FFT. Circular, so looping sounds stay seamless."""
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    spec[(freqs < lo) | (freqs > hi)] = 0
    return np.fft.irfft(spec, len(x))


def _fade(x, sr, attack=0.004, release=0.05):
    env = np.ones(len(x))
    a, r = int(attack * sr), int(release * sr)
    if a:
        env[:a] = np.linspace(0, 1, a, endpoint=False)
    if r:
        env[-r:] = np.linspace(1, 0, r)
    return x * env


def _mix(parts, sr):
    """parts: (start_seconds, samples, gain). Returns the summed, peak-normalised result."""
    n = max(int(start * sr) + len(x) for start, x, _ in parts)
    out = np.zeros(n)
    for start, x, gain in parts:
        i = int(start * sr)
        out[i : i + len(x)] += x * gain
    return _unit(out)


# --- building blocks ---------------------------------------------------------------------


def _screech(
    sr, rng, dur=1.7, f0=1800, f1=3000, vib_rate=13, vib_depth=0.07, grit=0.4, drive=4.0
):
    """Harsh, fatiguing scream: a rising, wobbling, distorted stack of dissonant oscillators."""
    t = _time(dur, sr)
    jitter = _unit(_band(rng.standard_normal(len(t)), 0, 25, sr))
    freq = (f0 + (f1 - f0) * (t / dur) ** 0.7) * (
        1 + vib_depth * np.sin(TAU * vib_rate * t) + 0.03 * jitter
    )
    ph = _phase(freq, sr)
    voice = (
        _unit(_saw(ph))
        + 0.6
        * _unit(
            _square(_phase(freq * 1.414, sr))
        )  # a tritone above: deliberately unpleasant
        + 0.4 * np.sin(ph * 2.01)
        + 0.3 * np.sin(ph + 3 * np.sin(TAU * 60 * t))  # FM growl
    )
    noise = _unit(_band(rng.standard_normal(len(t)), 2500, 9000, sr))
    x = np.tanh(drive * _unit(voice + grit * noise) * (1 + 0.25 * np.sin(TAU * 28 * t)))
    return _fade(x, sr, 0.003, 0.25)


def _hit(sr, rng):
    """Low boom plus a crack: the moment of impact."""
    t = _time(0.6, sr)
    boom = np.sin(_phase(150 * np.exp(-t * 7) + 35, sr)) * np.exp(-t * 6)
    crack = _unit(_band(rng.standard_normal(len(t)), 200, 4000, sr)) * np.exp(-t * 45)
    return _unit(np.tanh(2.5 * (boom + 0.8 * crack)))


def _ringing(sr, dur=2.0):
    """Quiet tinnitus-like whine that lingers after a scare."""
    t = _time(dur, sr)
    return 0.12 * np.sin(TAU * 6800 * t) * (1 - t / dur) ** 2


def _squawk(sr, rng, f0, dur):
    t = _time(dur, sr)
    freq = f0 * (1 - 0.5 * (t / dur) ** 0.8) * (1 + 0.10 * np.sin(TAU * 48 * t))
    ph = _phase(freq, sr)
    x = _unit(_saw(ph) + 0.5 * _square(ph * 2) + 0.1 * rng.standard_normal(len(t)))
    x = _band(x, 500, 3500, sr) * np.exp(-t * 2.5 / dur)
    return _fade(_unit(np.tanh(2 * x)), sr, 0.008, 0.03)


def _bell(sr, f, dur=0.6):
    t = _time(dur, sr)
    x = sum(
        a * np.sin(TAU * f * r * t) for r, a in ((1, 1.0), (2.756, 0.5), (5.404, 0.25))
    )
    return _unit(x) * np.exp(-t * 7)


def _squeal(sr, rng, dur=0.9, f0=3300):
    t = _time(dur, sr)
    freq = f0 * (1 + 0.02 * np.sin(TAU * 9 * t))
    ph = _phase(freq, sr)
    x = (
        np.sin(ph)
        + 0.5 * np.sin(2 * ph)
        + 0.3 * _unit(_band(rng.standard_normal(len(t)), 2000, 5000, sr))
    )
    return _fade(np.tanh(2 * x * (1 + 0.3 * np.sin(TAU * 17 * t))), sr, 0.01, 0.2)


def _note(sr, f, dur, vib=0.0):
    t = _time(dur, sr)
    freq = f * (1 + vib * np.sin(TAU * 6 * t))
    return _fade(_unit(_band(_saw(_phase(freq, sr)), 0, 2200, sr)), sr, 0.02, 0.05)


# --- jump scares, one per event ----------------------------------------------------------


def scare_truck(sr, rng):
    t = _time(1.7, sr)
    horn = sum(
        _saw(_phase(f * (1 + 0.003 * np.sin(TAU * 5 * t)), sr)) for f in (370, 440, 554)
    )
    horn = _fade(np.tanh(2.5 * _unit(horn)), sr, 0.015, 0.3)
    skid = _fade(
        _unit(_band(rng.standard_normal(len(t)), 3000, 6500, sr)) * (1 - t / 1.7),
        sr,
        0.01,
        0.2,
    )
    return _mix(
        [
            (0, _hit(sr, rng), 1.0),
            (0, horn, 1.0),
            (0, skid, 0.35),
            (1.7, _ringing(sr), 1.0),
        ],
        sr,
    )


def scare_chicken(sr, rng):
    parts = [
        (start, _squawk(sr, rng, f0, dur), 1.0)
        for start, f0, dur in (
            (0, 900, 0.2),
            (0.25, 1000, 0.18),
            (0.46, 850, 0.2),
            (0.75, 1100, 0.35),
        )
    ]
    parts.append((1.05, _squawk(sr, rng, 1300, 0.6), 1.0))
    return _mix(parts, sr)


def scare_scooter(sr, rng):
    parts = [(i * 0.12, _bell(sr, 2093), 0.8) for i in range(5)]
    parts += [
        (0.2, _squeal(sr, rng), 0.8),
        (0.3, _screech(sr, rng, dur=0.7, f0=1600, f1=2600, drive=2.0, grit=0.3), 0.6),
    ]
    parts.append((0, _hit(sr, rng), 0.7))
    return _mix(parts, sr)


def scare_trump(sr, rng):
    t = _time(0.7, sr)
    buzzer = _fade(
        np.tanh(2 * (_square(TAU * 110 * t) + _square(TAU * 113 * t))), sr, 0.005, 0.05
    )
    parts = [(0, buzzer, 1.0)]
    start = 0.75
    for f, dur, vib in (
        (233.1, 0.3, 0),
        (220.0, 0.3, 0),
        (207.7, 0.3, 0),
        (196.0, 1.0, 0.03),
    ):
        parts.append((start, _note(sr, f, dur, vib), 0.9))
        start += dur
    return _mix(parts, sr)


# --- cues and ambience -------------------------------------------------------------------


def alert(sr, rng):
    parts = []
    for i, f in enumerate((880, 1320)):
        t = _time(0.09, sr)
        parts.append((i * 0.11, _fade(_square(TAU * f * t), sr, 0.003, 0.02), 1.0))
    return _mix(parts, sr)


def riser(sr, rng, dur=1.5):
    """Tension swelling over the QTE window."""
    t = _time(dur, sr)
    whoosh = _unit(_band(rng.standard_normal(len(t)), 800, 6000, sr)) * (t / dur) ** 2
    sweep = np.sin(_phase(200 * (9 ** (t / dur)), sr)) * (t / dur) ** 1.5
    return _fade(_unit(whoosh + 0.6 * sweep), sr, 0.02, 0.05)


def saved(sr, rng):
    """Relief: a short tyre squeal, then a soft major chord."""
    t = _time(0.45, sr)
    skid = _unit(_band(rng.standard_normal(len(t)), 2000, 5000, sr)) * np.exp(-t * 5)
    parts = [(0, skid, 0.5)]
    for f in (523.25, 659.25, 783.99):
        ct = _time(1.2, sr)
        parts.append((0.25, np.sin(TAU * f * ct) * np.exp(-ct * 3), 0.5))
    return _mix(parts, sr)


def click(sr, rng):
    """Chunky dashboard switch."""
    t = _time(0.09, sr)
    tick = _unit(_band(rng.standard_normal(len(t)), 1500, 6000, sr)) * np.exp(-t * 90)
    thud = np.sin(TAU * 140 * t) * np.exp(-t * 60)
    return _unit(tick + 0.8 * thud)


def zap(sr, rng):
    """Electrical crackle as the headlights start to fail."""
    t = _time(0.45, sr)
    gate = (rng.random(len(t) // 400 + 1) > 0.45).repeat(400)[: len(t)]
    hiss = _unit(_band(rng.standard_normal(len(t)), 1000, 9000, sr))
    return _fade(
        _unit(np.tanh(3 * hiss * gate) + 0.4 * np.sin(TAU * 100 * t)) * np.exp(-t * 4),
        sr,
        0.002,
        0.1,
    )


def engine(sr, rng):
    """Two-second seamless loop of low engine rumble."""
    t = _time(2.0, sr)
    tone = _saw(TAU * 48 * t) + 0.5 * _saw(
        TAU * 96 * t
    )  # whole number of cycles, so it loops
    x = _band(_unit(tone), 20, 400, sr) + 0.6 * _unit(
        _band(rng.standard_normal(len(t)), 40, 300, sr)
    )
    return _unit(x) * 0.5


# name -> (builder, relative volume)
SOUNDS = {
    "scare_truck": (scare_truck, 1.0),
    "scare_chicken": (scare_chicken, 0.9),
    "scare_scooter": (scare_scooter, 0.9),
    "scare_trump": (scare_trump, 0.9),
    "alert": (alert, 0.3),
    "riser": (riser, 0.4),
    "saved": (saved, 0.5),
    "click": (click, 0.6),
    "zap": (zap, 0.5),
    "engine": (engine, 1.0),
}


def build(sr, seed=1):
    """Synthesise every sound as a mono float array in -1..1."""
    return {
        name: builder(sr, np.random.default_rng(seed))
        for name, (builder, _) in SOUNDS.items()
    }


# recorded samples played as they are: name -> (sample key, relative volume)
SAMPLE_SOUNDS = {
    "gasp": ("gasp", 0.8),
    "exhale": ("exhale", 0.8),
    "panic": ("panic", 1.0),
    "laugh_kid": ("laugh_kid", 0.8),
    "buzz": ("buzz", 1.0),
    "frogs": ("frogs", 1.0),
    **{
        f"switch_{s}_{i}": (f"switch_{s}_{i}", 0.6)
        for s in ("on", "off")
        for i in (1, 2, 3)
    },
    **{key: (key, 0.7) for key in samples.AMBIENT_ONESHOTS if key in samples.SAMPLES},
}
# sounds assembled from several samples (see samples.COMPOSITES): relative volume
COMPOSITE_VOLUME = {
    "creature_deer": 0.8,
    "creature_yeti": 0.8,
    "creature_deep_one": 0.8,
    "amb_steps": 0.7,
}


def _stereo(mono):
    return np.stack(
        [mono, np.roll(mono, 20)], axis=1
    )  # a hair of delay between the ears gives width


def _layer(base, extra, start, sr):
    """Mix `extra` into `base` (both stereo) at `start` seconds, growing `base` if needed."""
    i = int(start * sr)
    out = np.zeros((max(len(base), i + len(extra)), 2), dtype=np.float32)
    out[: len(base)] += base
    out[i : i + len(extra)] += extra
    return out


class Sfx:
    def __init__(self, enabled=True, rng=None):
        init = pygame.mixer.get_init()
        self.ok = bool(enabled and init and init[1] == -16)
        self.muted = False
        self.sounds = {}
        self.rng = rng or random.Random()
        self._loops = {}  # name -> channel of a looping sound
        self._amb_timer = self.rng.uniform(*S.AMBIENT_ONESHOT_RANGE)
        if not self.ok:
            return
        sr, _, self._channels = init
        for name, mono in build(sr).items():
            audio = _stereo(mono)
            for key, start in samples.SCARE_LAYERS.get(name, ()):
                layer = samples.load(key)
                if layer is not None:
                    audio = _layer(audio, layer, start, sr)
            self._add(name, audio, SOUNDS[name][1])
        for name, (key, volume) in SAMPLE_SOUNDS.items():
            audio = samples.load(key)
            if audio is not None:
                self._add(name, audio, volume)
        for name, parts in samples.COMPOSITES.items():
            audio = np.zeros((0, 2), dtype=np.float32)
            for key, start in parts:
                layer = samples.load(key)
                if layer is not None:
                    audio = _layer(audio, layer, start, sr)
            if len(audio):
                self._add(name, audio, COMPOSITE_VOLUME.get(name, 0.7))

    def _add(self, name, audio, volume):
        audio = audio / max(1.0, float(np.abs(audio).max()))
        pcm = (audio * 32767 * 0.95).astype(np.int16)
        if self._channels == 1:
            pcm = pcm.mean(axis=1).astype(np.int16)
        elif self._channels > 2:
            pcm = np.concatenate(
                [pcm, np.repeat(pcm[:, :1], self._channels - 2, axis=1)], axis=1
            )
        snd = pygame.sndarray.make_sound(np.ascontiguousarray(pcm))
        snd.set_volume(volume * S.SFX_VOLUME)
        self.sounds[name] = snd

    # --- one-shots ---

    def play(self, name):
        if self.ok and not self.muted and name in self.sounds:
            return self.sounds[name].play()

    def play_scare(self, event_name):
        return self.play(f"scare_{event_name}")

    def play_appear(self, event_name):
        """A creature shows up: you gasp, and the scary ones make a noise of their own."""
        self.play("gasp" if "gasp" in self.sounds else "alert")
        name = samples.APPEAR.get(event_name)
        return self.play(name) if name else None

    def play_saved(self, event_name):
        self.play("saved")
        self.play("exhale")
        if event_name == "scooter":
            self.play("laugh_kid")

    def play_lights(self, on):
        """The headlight switch: a dashboard button (one of three variants), or a synthesised click."""
        name = f"switch_{'on' if on else 'off'}_{self.rng.randint(1, 3)}"
        self.play(name if name in self.sounds else "click")

    def ambient_tick(self, dt):
        """Every so often a distant yell, bell or creak. Call while the drive is quiet."""
        if not (self.ok and S.AMBIENT_ONESHOTS):
            return
        self._amb_timer -= dt
        if self._amb_timer <= 0:
            self._amb_timer = self.rng.uniform(*S.AMBIENT_ONESHOT_RANGE)
            options = [n for n in samples.AMBIENT_ONESHOTS if n in self.sounds]
            if options:
                self.play(self.rng.choice(options))

    def stop(self, name):
        if self.ok and name in self.sounds:
            self.sounds[name].stop()

    def stop_all(self):
        if self.ok:
            for snd in self.sounds.values():
                snd.stop()
        self._loops.clear()

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            self.stop_all()

    # --- loops ---

    def loop(self, name, volume=1.0):
        """Keep `name` looping at `volume` (starts it if needed). Call every frame; it is cheap."""
        if not self.ok or self.muted or name not in self.sounds:
            return
        channel = self._loops.get(name)
        if channel is None or not channel.get_busy():
            channel = self._loops[name] = self.sounds[name].play(loops=-1)
        if channel:
            channel.set_volume(volume)

    def stop_loop(self, name):
        if self._loops.pop(name, None) is not None:
            self.sounds[name].stop()

    def stop_loops(self):
        for name in list(self._loops):
            self.stop_loop(name)

    def engine(self, speed_fraction):
        """Engine hum that follows the car's speed (0 stops it)."""
        if speed_fraction <= 0.02:
            self.stop_loop("engine")
        else:
            self.loop("engine", S.ENGINE_VOLUME * min(1.0, speed_fraction))

    def ambience(self, on=True):
        if on:
            self.loop("frogs", S.AMBIENCE_VOLUME)
        else:
            self.stop_loop("frogs")


LOOPS = {"engine", "frogs", "panic", "buzz"}


def audition():
    pygame.mixer.init(44100, -16, 2)
    sfx = Sfx()
    names = list(sfx.sounds)
    print("Jump-scare sounds are LOUD. Lower your system volume before playing them.")
    while True:
        for i, name in enumerate(names, 1):
            print(f"  {i:2d}  {name}")
        choice = input("number to play, q to quit > ").strip().lower()
        if choice == "q":
            break
        if choice.isdigit() and 1 <= int(choice) <= len(names):
            sfx.stop_all()
            name = names[int(choice) - 1]
            if name in LOOPS:
                sfx.loop(name, 1.0)
            else:
                sfx.play(name)
    pygame.mixer.quit()


if __name__ == "__main__":
    audition()
