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
QTE_WINDOW = 4.5  # seconds to press the prompted letter
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

# Sound effects (recordings, played by sfx.py). The jump-scare sounds are loud by design.
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
GHOST_RUMBLE_VOLUME = (
    0.6  # the low drone while the ghost is here (swells as the deadline nears)
)
PANIC_VOLUME = 0.6  # breathing during a QTE
BUZZ_VOLUME = 0.5  # fluorescent buzz while the headlights flicker
AMBIENT_ONESHOTS = True  # distant yells, bells, creaks now and then (extra sounds can distract: switch off for strict experiments)
AMBIENT_ONESHOT_RANGE = (40.0, 90.0)  # seconds between them

# Eye tracking (optional; off by default)
GAZE_CALIBRATION_FILE = "data/gaze_calibration.json"
GAZE_MODEL_FILE = "data/models/face_landmarker.task"
GAZE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
GAZE_SMOOTHING = 0.25  # EMA factor per update (higher = snappier, jitterier)
GAZE_STALE = 0.5  # seconds after which a gaze sample is considered lost
GAZE_MIN_QUALITY = 0.5
CALIB_SETTLE = 0.6  # seconds to let the eyes reach each target before sampling
CALIB_SAMPLE = 1.2  # seconds of samples collected per target
CALIB_MIN_SAMPLES = 8  # per target, otherwise the target is repeated
CALIB_MAX_TRIES = (
    3  # tries per target before it is skipped (a lost face must not stall calibration)
)
GAZE_ROAD_BOX = (
    0.15,
    0.15,
    0.85,
    0.85,
)  # looking outside this box counts as looking away
GAZE_AWAY_TIME = 3.0  # seconds looking away before it counts as distraction
GAZE_COOLDOWN = 15.0  # seconds after a gaze-triggered event before the next one

# Cop: keep looking away from the road and it escalates (seconds of continuous inattention)
COP_WARN_TIME = 2.0  # "EYES ON THE ROAD" text
COP_APPEAR_TIME = 5.0  # a cop shows up and yells
COP_BUST_TIME = 8.0  # the cop pulls you over: game over
COP_REGAIN_TIME = 0.5  # looking at the road this long calms everything down
COP_HIDDEN_GAP = -2500  # world units: the cop car is far behind you, out of sight
COP_VISIBLE_GAP = 700  # it is drawn once it is this far ahead of the camera
COP_ALONGSIDE_GAP = 900  # where it first shows up, beside you
COP_OVERTAKE_GAP = 1500  # how much further ahead it gets by the time it busts you
COP_STOP_GAP = 2200  # distance ahead where it cuts in front and stops you
COP_LEFT_OFFSET = -0.05  # the oncoming-traffic lane it overtakes in (LANE_X is yours)
COP_STOP_HOLD = 1.2  # seconds standing still behind the cop before the game-over screen
COP_CHANCE = 0.5  # share of gaze distractions that become a cop instead of a monster
GAZE_SCRCPY_SIZE = "1280x720"  # phone camera resolution when streamed through scrcpy
GAZE_SCRCPY_FPS = 30
GAZE_L2CS_FILE = "data/models/L2CSNet_gaze360.pkl"
GAZE_L2CS_URL = "https://huggingface.co/tianfxc/l2cs/resolve/main/L2CSNet_gaze360.pkl"  # community mirror of the official weights
GAZE_L2CS_SHA256 = "8a7f3480d868dd48261e1d59f915b0ef0bb33ea12ea00938fb2168f212080665"
GAZE_L2CS_FACE_SCALE = 1.1  # face crop size relative to the landmark bounding box
GAZE_SCREEN_CM = (
    34.5,
    22.3,
)  # physical size of the display (MacBook Pro 16"); 14": (30.2, 19.6)
GAZE_CAM0_ABOVE_SCREEN_CM = (
    0.6  # first camera is assumed to sit at the top centre of the screen
)
GAZE_MAX_SKEW = 0.1  # seconds between the cameras' newest frames for a sample to be used in calibration

# Score (shown on the dashboard)
SCORE_PER_SECOND = (
    10  # points earned per second of driving; other sources can call Score.add()
)

# Roadside encounters: the monster that must not see your headlights, and the hitchhikers (some are impostors)
ROADSIDE_SPAWN_DISTANCE = 21000  # world units ahead of the car where an encounter appears (about 3.5 s at cruise)
ROADSIDE_FIRST_DELAY = (25.0, 45.0)  # seconds before the first monster / hitchhiker
MONSTER_INTERVAL = (40.0, 75.0)  # seconds between monsters
HITCH_INTERVAL = (30.0, 55.0)  # seconds between hitchhikers
ROADSIDE_HINTS_ONLY_FIRST = (
    True  # on-screen warnings only for the first monster / hitchhiker of the game
)
ROADSIDE_RESULT_TIME = 2.2  # how long the result message stays up

MONSTER_SIGHT_AHEAD = 15000  # it can see you from this far ahead...
MONSTER_SIGHT_BEHIND = 3000  # ...until you are this far past it
MONSTER_NOTICE_TIME = 1.3  # seconds with the lights fully on to fill its suspicion
MONSTER_CALM_TIME = 1.0  # seconds for suspicion to drain with the lights off
MONSTER_LUNGE_TIME = 0.35  # how long it lunges at the car before the jump scare
MONSTER_BONUS = 150  # points for driving past unseen

HITCH_PICKUP_RANGE = (
    9000  # you can pick them up from this far ahead (about 1.5 s at cruise)...
)
HITCH_PASS_DISTANCE = 1500  # ...until you are this far past them
HITCH_IMPOSTOR_CHANCE = 0.35
HITCH_BOARDING_TIME = 1.3  # door opens, shuts, then you find out who got in
HITCH_BONUS = 100  # points for a real passenger

# Headlight button on the dashboard: a flickering stimulus (the future SSVEP target) that you click for now
HEADLIGHT_BUTTON_HZ = 15.0  # flicker frequency; 0 = steady. Keep clear of 8-12 Hz (alpha, used by the ghost)

# Roadside hitchhikers are switched off for now (the code stays); monsters are unaffected
HITCHHIKERS_ENABLED = False
