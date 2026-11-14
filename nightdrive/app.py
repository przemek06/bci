import argparse

import pygame

from . import settings as S
from .art import Art
from .attention.eyes_source import make_eyes_source
from .scenes import MenuScene
from .world import World


class App:
    def __init__(self, seed=None, eyes="keyboard", eyes_log=True):
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
        self.font_title = pygame.font.Font(None, 40)
        self.font = pygame.font.Font(None, 20)
        self.font_big = pygame.font.Font(None, 28)
        self.font_small = pygame.font.Font(None, 14)
        self.assets = Art()
        self.eyes = make_eyes_source(
            eyes, log=eyes_log
        )  # "are the eyes closed?" for the ghost scare
        self.eyes.start()
        self.scene = MenuScene(self, World(self.assets, seed))

    def set_scene(self, scene):
        self.scene = scene

    def quit(self):
        self.running = False

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
            self.scene.update(dt)
            self.scene.draw(self.canvas)
            self.present()
        self.eyes.stop()
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(prog="nightdrive")
    parser.add_argument(
        "--seed", type=int, default=None, help="seed for the generated road"
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
    args = parser.parse_args()
    App(args.seed, args.eyes, eyes_log=not args.no_eyes_log).run()
