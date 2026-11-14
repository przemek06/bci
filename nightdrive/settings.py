import math
from pathlib import Path

# Internal pixel-art resolution (scaled up by an integer factor to the window)
W, H = 320, 180
HORIZON = H // 2
FPS = 60
WINDOW_SCALE = 3

# Road geometry (OutRun-style segment projection)
SEGMENT_LENGTH = 200
ROAD_WIDTH = 2000  # half-width in world units
RUMBLE_LENGTH = 4  # segments per colour band
CAMERA_HEIGHT = 1000
CAMERA_DEPTH = 1 / math.tan(math.radians(90) / 2)
DRAW_DISTANCE = 130  # segments drawn ahead
FOG_DENSITY = 4.0
TRACK_SEGMENTS = 3000  # length of the looping track

# Driving
CRUISE_SPEED = 6000  # world units per second
MENU_SPEED = 2500
LANE_X = 0.5  # driving in the right lane (road edges are +-1)

# Night palette
FOG_COLOR = (7, 10, 22)
GRASS = ((10, 26, 20), (8, 22, 17))
RUMBLE = ((120, 34, 40), (150, 150, 160))
ROAD = ((48, 50, 62), (43, 45, 57))
LANE = (170, 170, 140)

# Background layers: pixels scrolled per (curve * segment travelled)
PARALLAX_SKY = 0.02
PARALLAX_FAR = 0.05
PARALLAX_NEAR = 0.10
BG_WIDTH = 640  # width of the looping background tiles

# Events and quick-time events
QTE_WINDOW = 1.5  # seconds to press the prompted letter
QTE_WINDOW_DARK = 1.0  # ...when the headlights are off or flickering
IMPACT_DISTANCE = 900  # world units: when a missed creature gets hit
AFTERMATH_TIME = 2.2  # seconds the result message stays up
BRAKE_SPEED = 0.2  # fraction of cruise speed while braking after a success
AUTO_EVENT_RANGE = (
    10.0,
    20.0,
)  # temporary: random delay between events until attention input exists
JUMPSCARE_TIME = 1.7  # seconds of full-screen jump scare before the game-over screen
GAME_OVER_FADE = 0.7  # seconds to fade from the scare to the game-over screen

# Music (Lonely Nightmare by Crow Shade, CC BY 4.0). Gains level the tracks to about -34 dB RMS.
# The game reads only the small copy in assets/audio/. The full downloaded packs live in
# asset_packs/ (git-ignored); tools/import_audio.py copies what is used.
AUDIO_DIR = Path(__file__).resolve().parent.parent / "assets" / "audio"
MUSIC_DIR = AUDIO_DIR / "music"
SFX_DIR = AUDIO_DIR / "sfx"
MUSIC_PLAYLIST = (
    ("comfort", 0.71),
    ("a_place_ive_seen_before", 0.63),
    ("subtle_changes", 0.55),
    ("lying_down", 0.71),
    ("my_room", 0.50),
    ("sealed", 1.0),
    ("ceiling_stars", 0.32),
)
MUSIC_VOLUME = 0.8  # master music volume, 0..1
MUSIC_DUCK = 0.35  # fraction of the volume left during a QTE

# Sound effects (synthesised in sfx.py). The jump-scare sounds are loud by design.
SFX_VOLUME = 0.7  # master effects volume, 0..1
ENGINE_VOLUME = 0.12  # engine hum at cruise speed

# Headlights (Space toggles). They flicker now and then; switch off and on again to fix them.
FLICKER_RANGE = (25.0, 50.0)  # seconds of good light between flicker episodes
LIGHT_STEPS = 16  # light levels the renderer caches fog tables for
LIGHT_OFF_VISIBILITY = (
    0.30  # how bright the nearest road is with the lights off (moonlight)
)
LIGHT_OFF_DENSITY = 25.0  # how fast it fades with distance with the lights off

# Recorded effects (Horror SFX Free by YourPalRob, Darkworld Audio Survival Effects) and ambience
AMBIENCE_VOLUME = 0.5  # the frog loop under the drive
PANIC_VOLUME = 0.6  # breathing during a QTE
BUZZ_VOLUME = 0.5  # fluorescent buzz while the headlights flicker
AMBIENT_ONESHOTS = True  # distant yells, bells, creaks now and then (extra sounds can distract: switch off for strict experiments)
AMBIENT_ONESHOT_RANGE = (40.0, 90.0)  # seconds between them
