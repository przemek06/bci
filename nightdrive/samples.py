"""Recorded effects (Horror SFX Free by YourPalRob, Darkworld Audio Survival Effects), levelled and mapped to game moments.

The files live in assets/audio/sfx/<key>.wav or .mp3; tools/import_audio.py documents where each one came from.
"""

import numpy as np
import pygame

from . import settings as S

# key -> target RMS in dBFS. The raw files range from -10 dB to -60 dB, so every sample is levelled
# to its target (never past a 0.95 peak).
SAMPLES = {
    # layered into the jump scares
    "shriek_a": -12,  # deer: a bright, piercing screech
    "shriek_b": -14,
    "yeti_roar": -11,
    "deep_froth": -13,  # deep one: frothy, gurgling growls
    "deep_growl": -14,
    "metal_screech": -14,
    "laugh": -20,
    "drone": -28,  # lingers after the scary scares
    "ghost_scream": -11,  # the eyes-closed ghost kills you
    "ghost_moan": -24,  # ...and announces itself
    "scream_driver": -12,  # you scream when it gets you
    "ghost_stinger": -16,  # a resonant hit as it appears
    "ghost_tone": -30,  # eerie underwater bell under the stinger
    "ghost_rumble": -26,  # low drone loop while it is here
    **{f"ghost_chain_{i}": -22 for i in (1, 2, 3, 4)},  # rattling chains around you
    **{f"ghost_creak_{i}": -24 for i in (1, 2, 3)},
    **{f"ghost_knock_{i}": -20 for i in (1, 2, 3)},
    **{
        f"ghost_step_{i}": -24 for i in (1, 2, 3, 4)
    },  # footsteps you hear with your eyes shut
    "ghost_swoosh": -22,  # it passes
    "engine": -16,  # the car interior, loops under the drive
    "monster_growl": -20,
    "monster_attack": -12,
    "monster_roar": -12,
    "door_open": -22,
    "door_shut": -20,
    "laugh_spooky": -18,
    # the remaining scares and cues (all recorded now)
    "truck_horn": -14,
    "air_brake": -20,
    "riser": -22,  # a slow swell, cropped to its last 1.5 s before the peak (see TRIMS)
    "shriek_c": -13,
    "shriek_d": -16,
    "phone_slam": -12,
    **{f"whistle_{i}": -16 for i in (1, 2, 3, 4, 5)},
    "bell_ding": -16,
    "bonk": -14,
    "squeak_a": -18,
    "squeak_b": -20,
    "switch_click": -20,
    "tv_zap": -18,
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

# samples cropped on load: key -> (start second, length in seconds)
TRIMS = {"riser": (3.0, 1.5)}

# samples that play as seamless loops (their tail is crossfaded into their head on load)
LOOPS = ("engine", "frogs", "panic", "buzz", "ghost_rumble")
LOOP_CROSSFADE_S = 0.75

# every sound built from several samples: name -> [(sample key, start second[, gain])]
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
    "scare_ghost": [
        ("ghost_scream", 0.0),
        ("scream_driver", 0.3),
        ("injured", 0.6),
        ("drone", 1.7),
    ],
    "ghost_appear": [("ghost_stinger", 0.0), ("ghost_tone", 0.1), ("ghost_moan", 0.25)],
    "ghost_relief": [("ghost_swoosh", 0.0), ("exhale", 0.5)],
    "scare_truck": [
        ("truck_horn", 0.0),
        ("truck_horn", 0.5, 0.9),
        ("air_brake", 0.0, 0.8),
        ("car_crash", 0.0),
        ("glass_smash", 0.05),
        ("metal_screech", 0.0),
        ("injured", 0.5),
        ("drone", 1.7),
    ],
    "scare_chicken": [
        ("shriek_c", 0.0),
        ("shriek_d", 0.4, 0.8),
        ("whistle_5", 1.0, 0.8),
    ],
    "scare_scooter": [
        ("bonk", 0.0),
        ("bell_ding", 0.05),
        ("bell_ding", 0.2, 0.8),
        ("bell_ding", 0.35, 0.7),
        ("squeak_a", 0.1),
        ("squeak_b", 0.25, 0.8),
        ("laugh", 0.8),
    ],
    # "you're fired": an angry phone slam, then a sad-trombone of falling slide whistles
    "scare_trump": [
        ("phone_slam", 0.0),
        ("whistle_1", 0.9),
        ("whistle_2", 1.55),
        ("whistle_3", 2.2),
        ("whistle_4", 2.85),
    ],
    # the roadside monster saw you / the hitchhiker was not human
    "scare_monster": [
        ("monster_attack", 0.0),
        ("monster_roar", 0.1),
        ("thud", 0.0),
        ("injured", 0.4),
        ("drone", 1.7),
    ],
    "scare_impostor": [
        ("laugh_spooky", 0.0),
        ("shriek_b", 0.5),
        ("injured", 0.9),
        ("drone", 1.7),
    ],
    "pickup": [("door_open", 0.0), ("door_shut", 0.8)],
    # cues
    "saved": [("bell_ding", 0.0, 0.8)],  # a soft ding (the exhale is played separately)
    "zap": [("switch_click", 0.0), ("tv_zap", 0.05)],
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
    if key in TRIMS:
        start, length = TRIMS[key]
        sr = pygame.mixer.get_init()[0]
        a = a[int(start * sr) : int((start + length) * sr)]
        fade = int(0.05 * sr)
        a = a.copy()
        a[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)[:, None]
        a[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)[:, None]
    rms = float(np.sqrt((a**2).mean())) + 1e-9
    gain = 10 ** (SAMPLES[key] / 20) / rms
    peak = float(np.abs(a).max())
    if peak * gain > 0.95:
        gain = 0.95 / peak
    a = a * gain
    if key in LOOPS:
        a = make_loopable(a, pygame.mixer.get_init()[0])
    return a


def make_loopable(a, sr, fade_s=LOOP_CROSSFADE_S):
    """Blend the last `fade_s` seconds into the first ones (equal power) so the loop has no seam."""
    n = int(fade_s * sr)
    if len(a) < 4 * n:
        return a
    out = a[n:].copy()
    t = np.linspace(0, np.pi / 2, n, dtype=np.float32)[:, None]
    out[-n:] = a[-n:] * np.cos(t) + a[:n] * np.sin(t)
    return out
