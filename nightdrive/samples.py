"""Recorded effects (Horror SFX Free by YourPalRob, Darkworld Audio Survival Effects), levelled and mapped to game moments.

The files live in assets/audio/sfx/<key>.wav or .mp3; tools/import_audio.py documents where each one came from.
"""

import numpy as np
import pygame

from . import settings as S

# key -> target RMS in dBFS. The raw files range from -10 dB to -60 dB, so every sample is levelled
# to its target (never past a 0.95 peak).
SAMPLES = {
    # layered under the synthesised jump scares
    "shriek_a": -12,  # deer: a bright, piercing screech
    "shriek_b": -14,
    "yeti_roar": -11,
    "deep_froth": -13,  # deep one: frothy, gurgling growls
    "deep_growl": -14,
    "metal_screech": -14,
    "laugh": -20,
    "drone": -28,  # lingers after the scary scares
    "thud": -12,  # the hit
    "car_crash": -12,
    "glass_smash": -14,
    "injured": -16,  # the driver's cry
    # a creature announces itself as it appears
    "appear_deer": -26,
    "appear_yeti": -24,  # sniffing the air
    "appear_yeti_growl": -24,
    "appear_deep_one": -26,
    "twig": -22,
    "snow_step": -22,
    "wet_step": -22,
    # the player
    "gasp": -24,  # a startled gasp when a creature appears
    "exhale": -24,  # relief when you brake in time
    "panic": -30,  # loops during a QTE
    "laugh_kid": -22,  # the scooter kid rides off laughing
    # headlights
    "buzz": -34,  # loops while flickering
    **{f"switch_{state}_{i}": -24 for state in ("on", "off") for i in (1, 2, 3)},
    # night ambience
    "frogs": -38,  # loops under the drive
    "amb_yell": -30,
    "amb_bell": -30,
    "amb_creak": -32,
    "amb_crying": -34,
    "amb_tapping": -34,
    "amb_crows": -32,
    "amb_door": -34,
    "amb_hoot": -32,
    "amb_distant_roar": -38,
    **{f"step_twig_{i}": -34 for i in (1, 2, 3, 4)},
}

# synthesised scare -> [(sample key, start second)] mixed on top of it
SCARE_LAYERS = {
    "scare_truck": [
        ("car_crash", 0.0),
        ("glass_smash", 0.05),
        ("metal_screech", 0.0),
        ("injured", 0.5),
        ("drone", 1.7),
    ],
    "scare_scooter": [("laugh", 0.6)],
}

# sounds built purely from samples: name -> [(sample key, start second)]
COMPOSITES = {
    # fully recorded jump scares
    "scare_deer": [
        ("thud", 0.0),
        ("shriek_a", 0.0),
        ("shriek_b", 0.15),
        ("injured", 0.4),
        ("drone", 1.7),
    ],
    "scare_yeti": [("thud", 0.0), ("yeti_roar", 0.0), ("injured", 0.4), ("drone", 1.7)],
    "scare_deep_one": [
        ("thud", 0.0),
        ("deep_froth", 0.0),
        ("deep_growl", 0.1),
        ("injured", 0.4),
        ("drone", 1.7),
    ],
    # creatures announcing themselves
    "creature_deer": [("twig", 0.0), ("appear_deer", 0.15)],
    "creature_yeti": [
        ("appear_yeti", 0.0),
        ("snow_step", 0.35),
        ("snow_step", 0.85),
        ("snow_step", 1.3),
    ],
    "creature_deep_one": [
        ("appear_deep_one", 0.0),
        ("wet_step", 0.3),
        ("wet_step", 0.8),
    ],
    "amb_steps": [
        (f"step_twig_{i + 1}", i * 0.6) for i in range(4)
    ],  # someone walking by the road
}

# event name -> sound played when the creature appears
APPEAR = {
    "deer": "creature_deer",
    "yeti": "creature_yeti",
    "deep_one": "creature_deep_one",
}

# one-shots sprinkled over a quiet drive
AMBIENT_ONESHOTS = (
    "amb_yell",
    "amb_bell",
    "amb_creak",
    "amb_crying",
    "amb_tapping",
    "amb_crows",
    "amb_door",
    "amb_hoot",
    "amb_distant_roar",
    "amb_steps",
)


def load(key):
    """Decode a sample to stereo float32 at the mixer's rate, levelled to its target. None if unavailable."""
    file = next(
        (f for f in (S.SFX_DIR / f"{key}.wav", S.SFX_DIR / f"{key}.mp3") if f.exists()),
        None,
    )
    if file is None:
        return None
    try:
        data = pygame.sndarray.array(pygame.mixer.Sound(str(file)))
    except pygame.error:
        return None
    a = data.astype(np.float32) / 32768
    if a.ndim == 1:
        a = np.stack([a, a], axis=1)
    a = a[:, :2]
    rms = float(np.sqrt((a**2).mean())) + 1e-9
    gain = 10 ** (SAMPLES[key] / 20) / rms
    peak = float(np.abs(a).max())
    if peak * gain > 0.95:
        gain = 0.95 / peak
    return a * gain
