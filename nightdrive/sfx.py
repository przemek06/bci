"""The sound-effects player. Sounds are recordings from assets/audio/sfx (see samples.py), except the cop's siren and scare.

Sounds are plain samples, or composites layered from several samples with start offsets and gains
(jump scares, cues). The player adds stereo panning, seamless loops and ambient one-shots.

Run `python -m nightdrive.sfx` to audition every sound. The jump-scare sounds are LOUD on purpose:
lower your system volume first, and use SFX_VOLUME in settings.py to scale them.
"""

import random

import numpy as np
import pygame

from . import samples
from . import settings as S

# (kind, how many variants) of the one-shots the ghost scatters around you
GHOST_ONESHOTS = (("chain", 4), ("creak", 3), ("knock", 3), ("step", 4))

SAMPLE_SOUNDS = {
    "engine": ("engine", 1.0),
    "monster_growl": ("monster_growl", 0.8),
    "monster_rumble": (
        "ghost_rumble",
        1.0,
    ),  # the same drone as the ghost, a loop of its own
    "riser": ("riser", 0.4),
    "ghost_rumble": ("ghost_rumble", 1.0),
    **{
        f"ghost_{kind}_{i}": (f"ghost_{kind}_{i}", 0.8)
        for kind, n in GHOST_ONESHOTS
        for i in range(1, n + 1)
    },
    "gasp": ("gasp", 0.8),
    "ghost_moan": ("ghost_moan", 0.8),
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
    "scare_truck": 1.0,
    "scare_deer": 1.0,
    "scare_yeti": 1.0,
    "scare_deep_one": 1.0,
    "scare_ghost": 1.0,
    "scare_chicken": 0.9,
    "scare_scooter": 0.9,
    "scare_trump": 0.9,
    "scare_monster": 1.0,
    "scare_impostor": 1.0,
    "pickup": 0.8,
    "ghost_appear": 1.0,
    "ghost_relief": 0.8,
    "saved": 0.5,
    "zap": 0.5,
    "creature_deer": 0.8,
    "creature_yeti": 0.8,
    "creature_deep_one": 0.8,
    "amb_steps": 0.7,
}


# the cop's sounds are still synthesised: name -> (builder(sr, rng) -> mono in -1..1, volume)
def _unit(x):
    peak = np.max(np.abs(x))
    return x / peak if peak > 0 else x


def _siren(sr, rng):
    """Two-second police wail, a whole number of sweeps so it loops."""
    t = np.arange(int(2.0 * sr)) / sr
    freq = 950 + 300 * np.sin(2 * np.pi * t - np.pi / 2)
    return _unit(np.tanh(2 * np.sin(2 * np.pi * np.cumsum(freq) / sr))) * 0.6


def _scare_cop(sr, rng):
    """Whistle blast and a bang on the window."""
    t = np.arange(int(1.2 * sr)) / sr
    freq = 2900 + 150 * np.sin(2 * np.pi * 38 * t)
    whistle = np.sin(2 * np.pi * np.cumsum(freq) / sr) * np.exp(-t * 1.5)
    spec = np.fft.rfft(rng.standard_normal(len(t)))
    freqs = np.fft.rfftfreq(len(t), 1 / sr)
    spec[(freqs < 80) | (freqs > 3000)] = 0
    bang = _unit(np.fft.irfft(spec, len(t))) * np.exp(-t * 14)
    x = _unit(0.7 * whistle + bang)
    fade = np.minimum(1.0, (len(t) - np.arange(len(t))) / (0.2 * sr))
    return x * fade


SYNTH_SOUNDS = {"scare_cop": (_scare_cop, 1.0), "siren": (_siren, 0.35)}


def _layer(base, extra, start, sr, gain=1.0):
    """Mix `extra` into `base` (both stereo) at `start` seconds, growing `base` if needed."""
    i = int(start * sr)
    out = np.zeros((max(len(base), i + len(extra)), 2), dtype=np.float32)
    out[: len(base)] += base
    out[i : i + len(extra)] += extra * gain
    return out


class Sfx:
    def __init__(self, enabled=True, rng=None):
        init = pygame.mixer.get_init()
        self.ok = bool(enabled and init and init[1] == -16)
        self.sounds = {}
        self.rng = rng or random.Random()
        self._loops = {}  # name -> channel of a looping sound
        self._amb_timer = self.rng.uniform(*S.AMBIENT_ONESHOT_RANGE)
        if not self.ok:
            return
        sr, _, self._channels = init
        for name, (key, volume) in SAMPLE_SOUNDS.items():
            audio = samples.load(key)
            if audio is not None:
                self._add(name, audio, volume)
        for name, parts in samples.COMPOSITES.items():
            audio = np.zeros((0, 2), dtype=np.float32)
            for key, start, *gain in parts:
                layer = samples.load(key)
                if layer is not None:
                    audio = _layer(audio, layer, start, sr, gain[0] if gain else 1.0)
            if len(audio):
                self._add(name, audio, COMPOSITE_VOLUME.get(name, 0.7))
        for name, (builder, volume) in SYNTH_SOUNDS.items():
            mono = builder(sr, np.random.default_rng(1))
            self._add(name, np.stack([mono, np.roll(mono, 20)], axis=1), volume)

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

    def play(self, name, pan=None):
        """Play a sound once. `pan` is -1 (hard left) .. +1 (hard right); None keeps it centred."""
        if self.ok and name in self.sounds:
            channel = self.sounds[name].play()
            if channel is not None and pan is not None:
                channel.set_volume(1.0 - max(0.0, pan), 1.0 + min(0.0, pan))
            return channel

    def play_random(self, names, pan=None):
        """Play one of `names` (those that are loaded), chosen at random."""
        options = [n for n in names if n in self.sounds]
        return self.play(self.rng.choice(options), pan) if options else None

    def play_scare(self, event_name):
        return self.play(f"scare_{event_name}")

    def play_appear(self, event_name):
        """A creature shows up: you gasp, and the scary ones make a noise of their own."""
        self.play("gasp")
        name = samples.APPEAR.get(event_name)
        return self.play(name) if name else None

    def play_saved(self, event_name):
        self.play("saved")
        self.play("exhale")
        if event_name == "scooter":
            self.play("laugh_kid")

    def play_lights(self, on):
        """The headlight switch: a dashboard button, one of three variants."""
        name = f"switch_{'on' if on else 'off'}_{self.rng.randint(1, 3)}"
        self.play(name)

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

    # --- loops ---

    def loop(self, name, volume=1.0):
        """Keep `name` looping at `volume` (starts it if needed). Call every frame; it is cheap."""
        if not self.ok or name not in self.sounds:
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
            if name in samples.LOOPS:
                sfx.loop(name, 1.0)
            else:
                sfx.play(name)
    pygame.mixer.quit()


if __name__ == "__main__":
    audition()
