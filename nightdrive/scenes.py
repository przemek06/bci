import random

import pygame

from . import settings as S
from .cop import CopChallenge
from .events import AFTERMATH, CATALOGUE, DEAD, IMPACT, QTE, EventDirector
from .focus_pass import FocusPass
from .gaze.tracker import GazeMonitor
from .ghost import GhostChallenge
from .ghost_audio import GhostAudio
from .roadside import LUNGE, MONSTER, RoadsideDirector

TEXT = (225, 228, 255)
DIM = (120, 128, 170)
ACCENT = (255, 120, 90)
GOOD = (120, 255, 160)
BAD = (255, 90, 80)
CONFETTI = (
    (255, 120, 90),
    (120, 255, 160),
    (255, 220, 90),
    (120, 200, 255),
    (255, 120, 200),
)
WARN = (255, 190, 60)


def draw_text(surf, text, font, color, center=None, topleft=None, shadow=(5, 6, 16)):
    img = font.render(text, False, color)
    rect = img.get_rect(center=center) if center else img.get_rect(topleft=topleft)
    if shadow:
        surf.blit(font.render(text, False, shadow), rect.move(1, 1))
    surf.blit(img, rect)


def start_drive(app, world):
    """The scene that begins a game: the attention calibration first, if the headset still needs a
    baseline (see attention_calibration.py), otherwise straight into the drive."""
    source = app.attention
    if getattr(source, "needs_calibration", False) and not source.calibrated:
        from .attention_calibration import AttentionCalibrationScene

        return AttentionCalibrationScene(app, world)
    return DriveScene(app, world)


class MenuScene:
    def __init__(self, app, world):
        self.app = app
        self.world = world
        self.world.cruise = S.MENU_SPEED
        app.music.duck = False
        app.music.start()
        world.headlights.reset()
        world.headlights.flicker_enabled = False
        world.score.reset()
        world.button_flicker = False  # the dashboard button only flickers while driving
        world.button_hover = False
        app.sfx.stop_loop("panic")
        app.sfx.stop_loop("buzz")
        app.sfx.stop_loop("ghost_rumble")
        app.sfx.stop_loop("monster_rumble")
        self.selected = 0
        self.veil = pygame.Surface((S.W, S.H), pygame.SRCALPHA)
        self.veil.fill((2, 3, 12, 110))

    @property
    def options(self):
        gaze = self.app.gaze
        opts = ["START", "EYE TRACKING: ON" if gaze else "EYE TRACKING: OFF"]
        if gaze and gaze.source.needs_calibration:
            opts.append("CALIBRATE EYES" if gaze.ready else "CALIBRATE EYES (REQUIRED)")
        opts.append("QUIT")
        return opts

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        n = len(self.options)
        if event.key in (pygame.K_UP, pygame.K_w):
            self.selected = (self.selected - 1) % n
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.selected = (self.selected + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._choose()
        elif event.key == pygame.K_ESCAPE:
            self.app.quit()

    def _choose(self):
        choice = self.options[self.selected]
        if choice == "START":
            self.app.set_scene(start_drive(self.app, self.world))
        elif choice.startswith("EYE TRACKING"):
            if self.app.gaze:
                self.app.disable_gaze()
            else:
                self.app.enable_gaze()
            self.selected = min(self.selected, len(self.options) - 1)
        elif choice.startswith("CALIBRATE"):
            from .calibration_scene import CalibrationScene

            self.app.set_scene(CalibrationScene(self.app, self.world))
        else:
            self.app.quit()

    def update(self, dt):
        self.world.update(dt)
        self.app.sfx.engine(self.world.speed / S.CRUISE_SPEED)
        self.app.sfx.ambience()

    def draw(self, surf):
        self.world.draw(surf)
        surf.blit(self.veil, (0, 0))
        draw_text(
            surf,
            "NIGHT DRIVE",
            self.app.font_title,
            TEXT,
            center=(S.W // 2, 42),
            shadow=(120, 30, 40),
        )
        draw_text(
            surf,
            "a calm drive through the dark",
            self.app.font_small,
            DIM,
            center=(S.W // 2, 66),
        )
        if self.app.highscore.best:
            draw_text(
                surf,
                f"HIGH SCORE  {self.app.highscore.best}",
                self.app.font_small,
                ACCENT,
                center=(S.W // 2, 76),
            )
        for i, label in enumerate(self.options):
            selected = i == self.selected
            text = f"> {label} <" if selected else label
            draw_text(
                surf,
                text,
                self.app.font,
                ACCENT if selected else TEXT,
                center=(S.W // 2, 88 + i * 14),
            )
        draw_text(
            surf,
            "UP/DOWN + ENTER",
            self.app.font_small,
            DIM,
            center=(S.W // 2, 149),
        )
        draw_text(
            surf, "MUSIC: CROW SHADE", self.app.font_small, DIM, center=(S.W // 2, 160)
        )
        draw_text(
            surf,
            "SFX: YOURPALROB, FILMCOW, DARKWORLD, RIRISAURUS",
            self.app.font_small,
            DIM,
            center=(S.W // 2, 170),
        )


class DriveScene:
    def __init__(self, app, world):
        self.app = app
        self.world = world
        self.world.cruise = S.CRUISE_SPEED
        app.music.start()
        world.headlights.reset()
        world.headlights.flicker_enabled = S.HEADLIGHTS_ENABLED
        world.score.reset()
        world.actors.clear()  # nobody left standing by the road from a previous run
        world.button_flicker = (
            S.HEADLIGHTS_ENABLED  # the headlight button flickers: the future SSVEP stimulus
        )
        world.button_hz = app.light_switch.stimulus_hz
        self.rng = random.Random(app.seed)
        self.director = EventDirector(world, self.rng)
        self.ghost = GhostChallenge(app)  # close-your-eyes scare, see nightdrive/ghost/
        self.focus = FocusPass(
            app
        )  # focus hard to pass a quick-time event, see focus_pass.py
        self.ghost_audio = GhostAudio(app.sfx, self.ghost, random.Random(app.seed))
        self.roadside = RoadsideDirector(
            world,
            world.score,
            app.sfx,
            random.Random(None if app.seed is None else app.seed + 2),
            app.roadside_hints,
        )
        self.auto_timer = self.rng.uniform(*S.AUTO_EVENT_RANGE)
        self.elapsed = 0.0
        self.best_at_start = app.highscore.best  # the record to beat in this run
        self.record_left = 0.0  # seconds left of the "new high score" banner
        self._record_announced = False
        self.gaze_monitor = GazeMonitor()
        self.cop = CopChallenge(app, world)
        self.cop_rng = random.Random(None if app.seed is None else app.seed + 2)
        self.cop_episode = (
            False  # this lapse of attention escalates to a cop, not a monster
        )
        self._was_away = False
        self.sim_away = False  # C key: pretend to look away (no eye tracker needed)
        self._prev_state = self.director.state
        self._was_flickering = False

    def on_distracted(self, event=None):
        """Called when the player's attention drops. For now fired by a timer or the E key."""
        if self.ghost.active or self.roadside.active:  # one scare at a time
            return
        if not self.app.qte_keys and not self.focus.ready:
            return  # focus-only mode: wait until focus can pass the event (never an unwinnable one)
        # longer window if focus can pass the event (see focus_pass.py)
        self.director.qte_window = self.focus.qte_window(S.QTE_WINDOW)
        if self.director.trigger(event):
            self.app.sfx.play("riser")
            self.app.sfx.play_appear(self.director.event.name)

    def end_run(self):
        """The run is over (death, ESC, or the window closed): keep the score if it is a new best."""
        return self.app.highscore.submit(self.world.score.display)

    def _check_record(self, dt):
        """Congratulate the moment the score passes the best of earlier runs (once per run)."""
        self.record_left = max(0.0, self.record_left - dt)
        if (
            not self._record_announced
            and self.best_at_start > 0
            and self.world.score.display > self.best_at_start
        ):
            self._record_announced = True
            self.record_left = S.RECORD_BANNER_S
            self.app.sfx.play("saved")

    def _draw_record_banner(self, surf):
        """The best score itself is only shown on the menu and the end screen, never while driving."""
        if self.record_left > 0:
            flash = int(self.elapsed * 4) % 2 == 0
            draw_text(
                surf,
                "NEW HIGH SCORE!",
                self.app.font_big,
                GOOD if flash else ACCENT,
                center=(S.W // 2, 104),
            )
            draw_text(
                surf, "CONGRATULATIONS!", self.app.font, TEXT, center=(S.W // 2, 122)
            )

    @property
    def keys_active(self):
        """Do letter keys pass quick-time events? Yes in the no-BCI mode, and as a fallback when
        focus cannot be measured (signal lost mid-event), so a quick-time event is never unwinnable."""
        return self.app.qte_keys or not self.focus.ready

    def _scare_running(self):
        """A QTE event, the ghost or a roadside encounter is going on: no second one starts."""
        return self.director.active or self.ghost.active or self.roadside.active

    def toggle_lights(self):
        if not S.HEADLIGHTS_ENABLED:  # headlight features are switched off for now
            return
        self.world.headlights.toggle()
        self.app.sfx.play_lights(self.world.headlights.on)

    def handle_event(self, event):
        if S.HEADLIGHTS_ENABLED and self.app.light_switch.handle_event(
            event
        ):  # a click on the dashboard button, or later a BCI
            self.toggle_lights()
            return
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_ESCAPE:
            self.director.reset()
            self.app.sfx.stop("riser")
            self.ghost.reset()
            self.cop.reset()
            self.ghost_audio.stop()
            self.roadside.reset()
            self.end_run()
            self.app.set_scene(MenuScene(self.app, self.world))
        elif event.key == pygame.K_RETURN:  # open the door for a hitchhiker
            self.roadside.pick_up()
        elif event.key == pygame.K_TAB:  # show/hide the gaze marker
            self.app.show_gaze = not self.app.show_gaze
        elif pygame.K_1 <= event.key <= pygame.K_9:  # debug: trigger a specific event
            index = event.key - pygame.K_1
            if index < len(CATALOGUE) and not self.director.active:
                self.on_distracted(CATALOGUE[index])
        elif pygame.K_a <= event.key <= pygame.K_z:
            letter = chr(event.key).upper()
            if self.director.state == QTE:
                if (
                    self.keys_active
                ):  # in the BCI mode the keys do nothing (not even a wrong one)
                    self.director.press(letter)
            elif letter == "E" and not self._scare_running():
                self.on_distracted()  # debug: trigger an event now
            elif letter == "C":
                self.sim_away = not self.sim_away  # debug: toggle looking away
            elif letter in "MHI" and not self._scare_running():
                if letter == "M":  # debug: a monster by the road (needs the headlights)
                    if S.HEADLIGHTS_ENABLED:
                        self.roadside.start_monster()
                elif (
                    S.HITCHHIKERS_ENABLED
                ):  # debug: H = a hitchhiker (maybe), I = an impostor
                    self.roadside.start_hitchhiker(True if letter == "I" else None)
            elif letter == "G":
                self.ghost.trigger(
                    busy=self.director.active or self.roadside.active
                )  # debug: ghost now

    def update(self, dt):
        self.elapsed += dt
        if self.focus.update(
            dt, qte_active=self.director.state == QTE, paused=self.ghost.active
        ):
            self.director.pass_by_focus()
        self.world.update(dt)
        self.world.score.update(dt)
        self._check_record(dt)
        if S.HEADLIGHTS_ENABLED and self.app.light_switch.update(dt):
            self.toggle_lights()
        self.world.button_hover = S.HEADLIGHTS_ENABLED and self.app.light_switch.hover
        self.director.update(dt)
        flickering = self.world.headlights.flickering
        if flickering and not self._was_flickering:
            self.app.sfx.play("zap")
        self._was_flickering = flickering
        self.app.music.duck = (
            self.director.state in (QTE, IMPACT)
            or self.ghost.active
            or self.roadside.mode in (MONSTER, LUNGE)
        )
        sfx = self.app.sfx
        sfx.engine(self.world.speed / S.CRUISE_SPEED)
        sfx.ambience()
        if self.director.state in (
            QTE,
            IMPACT,
        ):  # panicked breathing while the clock ticks
            sfx.loop("panic", S.PANIC_VOLUME)
        else:
            sfx.stop_loop("panic")
            if not self.director.active:
                sfx.ambient_tick(dt)
        if flickering and self.world.headlights.on:
            sfx.loop("buzz", S.BUZZ_VOLUME)
        else:
            sfx.stop_loop("buzz")
        if self.director.state != self._prev_state:
            if self.director.state == AFTERMATH:  # we braked in time
                self.app.sfx.stop("riser")
                self.app.sfx.play_saved(self.director.event.name)
            self._prev_state = self.director.state
        if self.director.state == DEAD:
            self.app.set_scene(
                GameOverScene(
                    self.app,
                    self.world,
                    self.director.event,
                    self.elapsed,
                )
            )
            self.director.reset()
            self.roadside.reset()
            return
        self.ghost.update(dt, busy=self.director.active or self.roadside.active)
        self.ghost_audio.update(dt)
        if self.ghost.dead:
            self.app.set_scene(
                GameOverScene(
                    self.app,
                    self.world,
                    self.ghost.death_event,
                    self.elapsed,
                )
            )
            self.ghost.reset()
            self.roadside.reset()
            return
        self.roadside.update(dt, busy=self.director.active or self.ghost.active)
        if self.roadside.dead:
            self.app.set_scene(
                GameOverScene(
                    self.app,
                    self.world,
                    self.roadside.death_event,
                    self.elapsed,
                )
            )
            self.roadside.reset()
            return
        if self.cop.dead:
            self.app.set_scene(
                GameOverScene(
                    self.app,
                    self.world,
                    self.cop.death_event,
                    self.elapsed,
                )
            )
            self.cop.reset()
            return
        gaze = self.app.gaze
        point = self.app.gaze_canvas_point() if gaze and gaze.ready else None
        tracked = point is not None and point.quality >= S.GAZE_MIN_QUALITY
        # untrackable eyes or a gaze far off screen both count as looking away
        gaze_away = bool(gaze and gaze.ready) and (
            not tracked or GazeMonitor.is_away(point)
        )
        busy = self._scare_running()
        away = gaze_away or self.sim_away
        if (
            away and not self._was_away and self.cop.away == 0.0
        ):  # a new lapse: cop or monster?
            self.cop_episode = self.sim_away or self.cop_rng.random() < S.COP_CHANCE
        elif not away and self.cop.away == 0.0:
            self.cop_episode = False
        self._was_away = away
        if busy:  # monsters have the player's full attention already
            self.cop.reset()
        else:
            self.cop.update(dt, away and self.cop_episode)
        if gaze and gaze.ready:
            # gaze replaces the placeholder timer: looking away from the road triggers events
            if (
                self.gaze_monitor.update(dt, point)
                and not busy
                and not self.cop_episode
            ):
                self.on_distracted()
        elif not self._scare_running():
            self.auto_timer -= dt
            if self.auto_timer <= 0:
                self.on_distracted()
                self.auto_timer = self.rng.uniform(*S.AUTO_EVENT_RANGE)

    def draw(self, surf):
        d = self.director
        self.world.draw(surf)
        if d.state == QTE:
            self._draw_prompt(surf, d.qte, self.keys_active)
            self.focus.draw(surf, keys_enabled=self.keys_active)
        elif d.message:
            draw_text(surf, d.message, self.app.font_big, GOOD, center=(S.W // 2, 40))
        self._draw_headlight_hint(surf)
        self._draw_light_switch_status(surf)
        self._draw_roadside_hud(surf)
        self.ghost.draw(surf)
        self.cop.draw(surf)
        self._draw_record_banner(surf)
        if self.elapsed < 5:
            alpha = 255 if self.elapsed < 3.5 else int(255 * (5 - self.elapsed) / 1.5)
            hint = self.app.font_small.render("ESC - MENU    C - LOOK AWAY", False, DIM)
            hint.set_alpha(alpha)
            surf.blit(hint, hint.get_rect(topright=(S.W - 6, 10)))

    def _draw_light_switch_status(self, surf):
        if not S.HEADLIGHTS_ENABLED:
            return
        text = (
            self.app.light_switch.status_text
        )  # e.g. "SSVEP: CALIBRATING 40%  LOOK AT THE ROAD"
        if text:
            draw_text(surf, text, self.app.font_small, DIM, topleft=(6, 24))

    def _draw_roadside_hud(self, surf):
        r = self.roadside
        hint = r.hint
        if not hint:
            return
        text, kind = hint
        color = {"warn": BAD, "calm": DIM, "info": TEXT, "dim": DIM, "good": GOOD}[kind]
        if kind == "warn" and int(self.elapsed * 4) % 2:
            color = WARN
        font = self.app.font_big if kind in ("warn", "good") else self.app.font
        draw_text(surf, text, font, color, center=(S.W // 2, 40))
        if r.shows_suspicion_bar:  # how close it is to noticing you
            bar = pygame.Rect(0, 0, 80, 5)
            bar.midtop = (S.W // 2, 54)
            pygame.draw.rect(surf, (6, 8, 20), bar)
            pygame.draw.rect(
                surf,
                BAD,
                (bar.x + 1, bar.y + 1, int((bar.w - 2) * r.suspicion), bar.h - 2),
            )

    def _draw_headlight_hint(self, surf):
        if not S.HEADLIGHTS_ENABLED:
            return
        lights = self.world.headlights
        if lights.flickering and lights.on:
            if int(self.elapsed * 3) % 2 == 0:
                draw_text(
                    surf,
                    "HEADLIGHTS FAILING - CLICK: OFF, THEN ON",
                    self.app.font_small,
                    WARN,
                    center=(S.W // 2, S.H - 46),
                )
        elif not lights.on:
            draw_text(
                surf,
                "HEADLIGHTS OFF - CLICK",
                self.app.font_small,
                DIM,
                center=(S.W // 2, S.H - 46),
            )

    def _draw_prompt(self, surf, qte, show_letter=True):
        cx, top = S.W // 2, 16
        # border goes from white to red as time runs out
        r = qte.remaining
        color = (255, int(80 + 175 * r), int(80 + 175 * r))
        if not show_letter:
            # BCI mode: nothing to press, so no letter box and no countdown bar: just the cue
            # (it goes from white to red as time runs out). The only bar is the focus meter.
            draw_text(surf, "FOCUS!", self.app.font_big, color, center=(cx, 24))
            draw_text(
                surf, "WATCH OUT ON THE ROAD!", self.app.font, TEXT, center=(cx, 44)
            )
            return
        box = pygame.Rect(0, 0, 44, 44)
        box.midtop = (cx, top)
        pygame.draw.rect(surf, (6, 8, 20), box)
        pygame.draw.rect(surf, color, box, 2)
        draw_text(surf, qte.letter, self.app.font_title, color, center=box.center)
        bar = pygame.Rect(0, 0, 64, 5)
        bar.midtop = (cx, box.bottom + 4)
        pygame.draw.rect(surf, (6, 8, 20), bar)
        pygame.draw.rect(
            surf, color, (bar.x + 1, bar.y + 1, int((bar.w - 2) * r), bar.h - 2)
        )


class GameOverScene:
    """Jump scare close-up, fade to black, then the game-over screen."""

    def __init__(self, app, world, event, survived):
        self.app = app
        self.world = world
        self.event = event
        self.survived = survived
        self.image = app.assets.jumpscares[event.name]
        app.music.stop()  # silence makes the scare land harder
        app.sfx.stop("riser")
        app.sfx.stop_loops()
        app.sfx.play_scare(event.name)
        self.t = 0.0
        self.rng = random.Random()
        self.previous_best = app.highscore.best
        self.new_record = app.highscore.submit(world.score.display)
        self._chimed = False
        crng = random.Random(
            7
        )  # confetti for a new record: x, fall speed, start offset, colour
        self.confetti = [
            (
                crng.randrange(S.W),
                crng.uniform(30, 80),
                crng.uniform(0, S.H),
                crng.choice(CONFETTI),
            )
            for _ in range(70)
        ]

    @property
    def can_continue(self):
        return self.t > S.JUMPSCARE_TIME + S.GAME_OVER_FADE + 0.3

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN or not self.can_continue:
            return
        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.app.sfx.stop_all()
            self.world.speed = 0.0
            self.app.set_scene(start_drive(self.app, self.world))
        elif event.key == pygame.K_ESCAPE:
            self.app.sfx.stop_all()
            self.app.set_scene(MenuScene(self.app, self.world))

    def update(self, dt):
        self.t += dt
        self.world.update(dt)
        if (
            self.new_record
            and not self._chimed
            and self.t > S.JUMPSCARE_TIME + S.GAME_OVER_FADE
        ):
            self._chimed = True  # a soft ding as the game-over screen appears
            self.app.sfx.play("saved")

    def draw(self, surf):
        surf.fill((0, 0, 0))
        if self.t < S.JUMPSCARE_TIME + S.GAME_OVER_FADE:
            self._draw_scare(surf)
        else:
            self._draw_game_over(surf)

    def _draw_scare(self, surf):
        t = self.t
        zoom = 1.1 + 0.25 * min(
            1.0, t / S.JUMPSCARE_TIME
        )  # slams in big, then creeps closer
        size = (int(S.W * zoom), int(S.H * zoom))
        img = pygame.transform.scale(self.image, size)
        amp = max(1, int(8 * (1 - t / S.JUMPSCARE_TIME)))
        ox = (S.W - size[0]) // 2 + self.rng.randint(-amp, amp)
        oy = (S.H - size[1]) // 2 + self.rng.randint(-amp, amp)
        surf.blit(img, (ox, oy))
        if int(t * 14) % 2 == 0 and t < S.JUMPSCARE_TIME:  # flicker
            veil = pygame.Surface((S.W, S.H), pygame.SRCALPHA)
            veil.fill((255, 0, 0, 50))
            surf.blit(veil, (0, 0))
        if t < 0.1:  # white flash on impact
            surf.fill((255, 255, 255), special_flags=pygame.BLEND_RGB_ADD)
        if self.event.scare_text and t < S.JUMPSCARE_TIME:
            draw_text(
                surf,
                self.event.scare_text,
                self.app.font_title,
                (255, 255, 255),
                center=(S.W // 2, 22),
                shadow=(120, 30, 40),
            )
        if t > S.JUMPSCARE_TIME:  # fade out
            fade = min(1.0, (t - S.JUMPSCARE_TIME) / S.GAME_OVER_FADE)
            veil = pygame.Surface((S.W, S.H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * fade)))
            surf.blit(veil, (0, 0))

    def _draw_confetti(self, surf):
        for x, speed, phase, color in self.confetti:
            y = (phase + self.t * speed) % S.H
            surf.fill(color, (x, int(y), 2, 2))

    def _draw_game_over(self, surf):
        cx = S.W // 2
        mins, secs = divmod(int(self.survived), 60)
        if self.new_record:
            self._draw_confetti(surf)
        draw_text(
            surf,
            "GAME OVER",
            self.app.font_title,
            BAD,
            center=(cx, 34),
            shadow=(40, 6, 10),
        )
        draw_text(surf, self.event.over_text, self.app.font, TEXT, center=(cx, 60))
        draw_text(
            surf,
            f"SCORE  {self.world.score.display}",
            self.app.font,
            ACCENT,
            center=(cx, 82),
        )
        if self.new_record:
            flash = int(self.t * 3) % 2 == 0
            draw_text(
                surf,
                "NEW HIGH SCORE!",
                self.app.font_big,
                GOOD if flash else ACCENT,
                center=(cx, 102),
            )
            draw_text(surf, "CONGRATULATIONS!", self.app.font, TEXT, center=(cx, 118))
            if self.previous_best:
                draw_text(
                    surf,
                    f"PREVIOUS BEST  {self.previous_best}",
                    self.app.font_small,
                    DIM,
                    center=(cx, 130),
                )
        else:
            draw_text(
                surf,
                f"HIGH SCORE  {self.app.highscore.best}",
                self.app.font,
                DIM,
                center=(cx, 102),
            )
        draw_text(
            surf, f"TIME  {mins}:{secs:02d}", self.app.font, DIM, center=(cx, 142)
        )
        if self.can_continue and int(self.t * 2) % 2 == 0:
            draw_text(
                surf,
                "ENTER - DRIVE AGAIN",
                self.app.font_small,
                ACCENT,
                center=(cx, 156),
            )
        if self.can_continue:
            draw_text(surf, "ESC - MENU", self.app.font_small, DIM, center=(cx, 168))
