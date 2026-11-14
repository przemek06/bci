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
QTE_WINDOW = 2.0  # seconds to press the prompted letter
IMPACT_DISTANCE = 900  # world units: when a missed creature gets hit
AFTERMATH_TIME = 2.2  # seconds the result message stays up
BRAKE_SPEED = 0.2  # fraction of cruise speed while braking after a success
AUTO_EVENT_RANGE = (
    10.0,
    20.0,
)  # temporary: random delay between events until attention input exists
JUMPSCARE_TIME = 1.7  # seconds of full-screen jump scare before the game-over screen
GAME_OVER_FADE = 0.7  # seconds to fade from the scare to the game-over screen
