import math

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
IMPACT_DISTANCE = 900  # world units: when a missed creature gets hit
AFTERMATH_TIME = 2.2  # seconds the result message stays up
BRAKE_SPEED = 0.2  # fraction of cruise speed while braking after a success
AUTO_EVENT_RANGE = (
    10.0,
    20.0,
)  # temporary: random delay between events until attention input exists
JUMPSCARE_TIME = 1.7  # seconds of full-screen jump scare before the game-over screen
GAME_OVER_FADE = 0.7  # seconds to fade from the scare to the game-over screen

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
GAZE_ROAD_BOX = (
    0.15,
    0.15,
    0.85,
    0.85,
)  # looking outside this box counts as looking away
GAZE_AWAY_TIME = 3.0  # seconds looking away before it counts as distraction
GAZE_COOLDOWN = 15.0  # seconds after a gaze-triggered event before the next one
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
