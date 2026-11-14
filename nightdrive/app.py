import argparse
from pathlib import Path

import pygame

from . import settings as S
from .art import Art
from .attention.eyes_source import make_eyes_source
from .audio import Music
from .gaze import l2cs
from .gaze.base import GazePoint
from .gaze.calibration import GazeCalibration
from .gaze.mouse_source import MouseGazeSource
from .gaze.tracker import GazeTracker
from .gaze.webcam_source import WebcamGazeSource, detect_cameras, parse_camera
from .light_switch import make_light_switch
from .scenes import MenuScene
from .sfx import Sfx
from .world import World


class App:
    def __init__(
        self,
        seed=None,
        eyes="keyboard",
        eyes_log=True,
        audio=True,
        gaze="off",
        camera=0,
        gaze_model="auto",
        lights="click",
        ssvep_log=True,
        ssvep_method=None,
    ):
        pygame.init()
        pygame.display.set_caption("Night Drive")
        self.fullscreen = False
        self.window = pygame.display.set_mode(
            (S.W * S.WINDOW_SCALE, S.H * S.WINDOW_SCALE), pygame.RESIZABLE
        )
        self.canvas = pygame.Surface((S.W, S.H))
        self.clock = pygame.time.Clock()
        self.running = True
        self.seed = seed
        self.roadside_hints = (
            set()
        )  # which roadside tutorials were already shown this session
        self.font_title = pygame.font.Font(None, 40)
        self.font = pygame.font.Font(None, 20)
        self.font_big = pygame.font.Font(None, 28)
        self.font_small = pygame.font.Font(None, 14)
        self.assets = Art()
        self.music = Music(enabled=audio)
        self.sfx = Sfx(enabled=audio)
        self.eyes = make_eyes_source(
            eyes, log=eyes_log
        )  # "are the eyes closed?" for the ghost scare
        self.eyes.start()
        self.light_switch = make_light_switch(
            lights, self, log=ssvep_log, method=ssvep_method
        )  # how the headlight button is operated
        self.light_switch.start()
        self.gaze_mode = (
            gaze if gaze != "off" else "webcam"
        )  # source used when toggled on
        cams = camera if isinstance(camera, (list, tuple)) else [camera]
        if list(map(str, cams)) == ["auto"]:
            cams = detect_cameras()
        self.camera = [parse_camera(c) for c in cams]
        self.use_l2cs = gaze_model == "l2cs" or (
            gaze_model == "auto" and l2cs.available()
        )
        self.gaze_tag = f"{'l2cs' if self.use_l2cs else 'mediapipe'}:{len(self.camera)}"
        self.gaze = None  # GazeTracker while eye tracking is on
        self.show_gaze = True
        if gaze != "off":
            self.enable_gaze()
        self.scene = MenuScene(self, World(self.assets, seed))

    def set_scene(self, scene):
        self.scene = scene

    def quit(self):
        self.disable_gaze()
        self.running = False

    def enable_gaze(self):
        if self.gaze_mode == "mouse":
            source = MouseGazeSource(self.mouse_norm)
        else:
            source = WebcamGazeSource(self.camera, self.use_l2cs)
        cal = GazeCalibration.load(Path(S.GAZE_CALIBRATION_FILE))
        if cal is not None and source.needs_calibration and cal.tag != self.gaze_tag:
            cal = None  # calibrated for another model / camera set
        self.gaze = GazeTracker(source, cal)
        self.gaze.start()

    def disable_gaze(self):
        if self.gaze:
            self.gaze.stop()
            self.gaze = None

    def _view(self):
        ww, wh = pygame.display.get_surface().get_size()
        scale = max(1, min(ww // S.W, wh // S.H))
        return scale, (ww - S.W * scale) // 2, (wh - S.H * scale) // 2

    def _canvas_on_screen(self):
        """(x, y, w, h) of the letterboxed canvas in desktop coordinates."""
        scale, ox, oy = self._view()
        wx, wy = pygame.display.get_window_position()
        return wx + ox, wy + oy, S.W * scale, S.H * scale

    def mouse_norm(self):
        """Mouse position as 0..1 desktop coordinates (the same space as the gaze)."""
        dw, dh = pygame.display.get_desktop_sizes()[0]
        wx, wy = pygame.display.get_window_position()
        mx, my = pygame.mouse.get_pos()
        return (wx + mx) / dw, (wy + my) / dh

    def gaze_canvas_point(self):
        """The gaze point mapped from the desktop onto the game canvas (0..1 inside it), or None."""
        p = self.gaze.point if self.gaze else None
        if p is None:
            return None
        dw, dh = pygame.display.get_desktop_sizes()[0]
        x, y, w, h = self._canvas_on_screen()
        return GazePoint((p.x * dw - x) / w, (p.y * dh - y) / h, p.quality, p.t)

    def window_to_canvas(self, pos):
        """A window pixel as game-canvas coordinates, or None outside the letterboxed canvas."""
        scale, ox, oy = self._view()
        x, y = (pos[0] - ox) / scale, (pos[1] - oy) / scale
        return (x, y) if 0 <= x < S.W and 0 <= y < S.H else None

    def set_fullscreen(self, flag):
        if flag != self.fullscreen:
            self.toggle_fullscreen()

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.window = pygame.display.set_mode(
                (S.W * S.WINDOW_SCALE, S.H * S.WINDOW_SCALE), pygame.RESIZABLE
            )

    def present(self):
        """Integer-scale the canvas with nearest-neighbour, letterboxed."""
        win = pygame.display.get_surface()
        ww, wh = win.get_size()
        scale = max(1, min(ww // S.W, wh // S.H))
        scaled = pygame.transform.scale(self.canvas, (S.W * scale, S.H * scale))
        win.fill((0, 0, 0))
        win.blit(
            scaled, ((ww - scaled.get_width()) // 2, (wh - scaled.get_height()) // 2)
        )
        pygame.display.flip()

    def run(self):
        while self.running:
            dt = min(self.clock.tick(S.FPS) / 1000, 0.05)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit()
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    self.toggle_fullscreen()
                else:
                    self.scene.handle_event(event)
            self.eyes.update()  # keeps calibration + live alpha log running in every scene
            if self.gaze:
                self.gaze.update()
            self.scene.update(dt)
            self.music.update(dt)
            if getattr(
                self.scene, "draws_window", False
            ):  # e.g. the full-screen gaze calibration
                self.scene.draw_window(pygame.display.get_surface())
                pygame.display.flip()
            else:
                self.scene.draw(self.canvas)
                self.present()
        self.eyes.stop()
        self.light_switch.stop()
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(prog="nightdrive")
    parser.add_argument(
        "--seed", type=int, default=None, help="seed for the generated road"
    )
    parser.add_argument(
        "--gaze",
        choices=("off", "webcam", "mouse"),
        default="off",
        help="enable eye tracking at start (it can also be toggled in the menu)",
    )
    parser.add_argument(
        "--gaze-camera",
        nargs="+",
        default=["auto"],
        help="'auto' (default: built-in camera + every USB phone seen by adb) or camera indexes / scrcpy:front:SERIAL / stream URLs",
    )
    parser.add_argument(
        "--gaze-model",
        choices=("auto", "l2cs", "mediapipe"),
        default="auto",
        help="gaze estimator: l2cs (neural net, needs torch; best with head movement) or mediapipe (iris landmarks only); auto uses l2cs when torch is installed",
    )
    parser.add_argument(
        "--eyes",
        choices=("keyboard", "bci"),
        default="keyboard",
        help="ghost scare input: hold SPACE (keyboard) or alpha waves from the headset (bci)",
    )
    parser.add_argument(
        "--no-eyes-log",
        action="store_true",
        help="don't print live alpha values to the console",
    )
    parser.add_argument(
        "--lights",
        choices=("click", "ssvep"),
        default="click",
        help="how the headlight button is operated: click it, or look at it (SSVEP from the headset; the mouse still works)",
    )
    parser.add_argument(
        "--ssvep-method",
        choices=("fbcca", "cca", "psd"),
        default=None,
        help="SSVEP detection method (default: fbcca, filter-bank CCA)",
    )
    parser.add_argument(
        "--no-ssvep-log",
        action="store_true",
        help="don't print the live SSVEP scores to the console",
    )
    args = parser.parse_args()
    App(
        args.seed,
        eyes=args.eyes,
        eyes_log=not args.no_eyes_log,
        gaze=args.gaze,
        camera=args.gaze_camera,
        gaze_model=args.gaze_model,
        lights=args.lights,
        ssvep_log=not args.no_ssvep_log,
        ssvep_method=args.ssvep_method,
    ).run()
