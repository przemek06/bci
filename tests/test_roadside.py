"""The roadside monster and the hitchhikers: rules tested with a stand-in world and sound player."""

import random
from types import SimpleNamespace

import numpy as np

from nightdrive import settings as S
from nightdrive.roadside import (
    BOARDING,
    DEAD,
    HITCH,
    IDLE,
    IMPOSTOR_DEATH,
    LUNGE,
    MONSTER,
    MONSTER_DEATH,
    RESULT,
    RoadsideDirector,
)
from nightdrive.score import Score

SPEED = 6000
DT = 1 / 60


class FakeSfx:
    def __init__(self):
        self.played = []
        self.loops = {}

    def play(self, name, pan=None):
        self.played.append(name)

    def loop(self, name, volume=1.0):
        self.loops[name] = volume

    def stop_loop(self, name):
        self.loops.pop(name, None)


def make(seed=1):
    world = SimpleNamespace(
        position=0.0,
        speed=SPEED,
        actors=[],
        track=SimpleNamespace(length=600_000),
        headlights=SimpleNamespace(light=1.0),
    )
    score = Score(per_second=0)
    sfx = FakeSfx()
    return RoadsideDirector(world, score, sfx, random.Random(seed)), world, score, sfx


def drive(director, world, seconds, busy=False):
    """Move the car at cruise speed and update, `seconds` long. Stops early on a result."""
    for _ in range(int(seconds / DT)):
        world.position = (world.position + world.speed * DT) % world.track.length
        director.update(DT, busy)
        if director.dead:
            return


# --- the monster ---------------------------------------------------------------------------


def test_monster_appears_ahead_beside_the_road_with_a_growl():
    d, world, _, sfx = make()
    assert d.start_monster() and d.mode == MONSTER
    assert not d.start_monster() and not d.start_hitchhiker()  # one at a time
    assert len(world.actors) == 1 and world.actors[0].kind == "monster"
    assert abs(world.actors[0].offset) > 1.5  # on the roadside, not on the road
    assert sfx.played == ["monster_growl"]
    assert abs(d._ahead(world.actors[0].z) - S.ROADSIDE_SPAWN_DISTANCE) < 1


def test_monster_gets_you_if_the_lights_stay_on():
    d, world, score, sfx = make()
    d.start_monster()
    world.headlights.light = 1.0
    drive(d, world, 5)
    assert d.mode in (LUNGE, DEAD)
    drive(d, world, 1)
    assert d.dead and d.death_event is MONSTER_DEATH
    assert score.display == 0 and d.survived_count == 0
    assert "monster_rumble" not in sfx.loops


def test_monster_lunges_at_the_car_before_the_scare():
    d, world, _, _ = make()
    d.start_monster()
    for _ in range(int(5 / DT)):
        world.position += SPEED * DT
        d.update(DT)
        if d.mode == LUNGE:
            break
    assert d.mode == LUNGE
    assert d.actor.target_offset == S.LANE_X  # it is coming for you
    assert not d.dead  # a short beat first


def test_turning_the_lights_off_in_time_makes_you_invisible():
    d, world, score, sfx = make()
    d.start_monster()
    world.headlights.light = 0.0
    for _ in range(int(7 / DT)):
        world.position += SPEED * DT
        d.update(DT)
        if d.mode == RESULT:
            break
    assert not d.dead and d.mode == RESULT
    assert score.display == S.MONSTER_BONUS and d.survived_count == 1
    assert d.message == "IT DIDN'T SEE YOU" and "exhale" in sfx.played
    assert world.actors == []
    assert d.suspicion == 0.0 and "monster_rumble" not in sfx.loops


def test_late_but_in_time_still_counts():
    """Lights on at first, off before the suspicion fills."""
    d, world, score, _ = make()
    d.start_monster()
    world.headlights.light = 1.0
    for _ in range(int(7 / DT)):
        world.position += SPEED * DT
        # it enters sight at 15000 ahead: ~1 s after spawning. Switch off 0.8 s after that.
        world.headlights.light = (
            1.0 if d._ahead(d.actor.z) > 15000 - 0.8 * SPEED else 0.0
        )
        d.update(DT)
        assert not d.dead
        if d.mode == RESULT:
            break
    assert d.mode == RESULT and score.display == S.MONSTER_BONUS


def test_suspicion_tracks_the_brightness_of_the_lights():
    def suspicion_after(light, seconds=0.8):
        d, world, _, _ = make()
        d.start_monster()
        world.position = S.ROADSIDE_SPAWN_DISTANCE - 10000  # well inside its sight
        world.headlights.light = light
        for _ in range(int(seconds / DT)):
            d.update(DT)
        return d.suspicion

    bright, dim = suspicion_after(1.0), suspicion_after(0.8)
    assert bright > dim > 0.0  # the brighter, the faster it notices
    assert (
        suspicion_after(0.4) == suspicion_after(0.0) == 0.0
    )  # a dim glow is not enough


def test_suspicion_drains_when_the_lights_go_off_and_creeps_the_monster():
    d, world, _, sfx = make()
    d.start_monster()
    world.position = S.ROADSIDE_SPAWN_DISTANCE - 10000
    world.headlights.light = 1.0
    for _ in range(int(0.7 / DT)):
        d.update(DT)
    up = d.suspicion
    assert 0 < up < 1 and sfx.loops["monster_rumble"] > 0
    assert abs(d.actor.target_offset) < abs(d._base_offset)  # it steps towards the road
    world.headlights.light = 0.0
    for _ in range(int(0.7 / DT)):
        d.update(DT)
    assert d.suspicion < up


def test_hint_tells_you_what_to_do():
    d, world, _, _ = make()
    assert d.hint is None
    d.start_monster()
    world.headlights.light = 1.0
    assert d.hint == ("MONSTER! LIGHTS OFF!", "warn")
    world.headlights.light = 0.0
    assert d.hint == ("STAY DARK...", "calm")


# --- the hitchhikers -----------------------------------------------------------------------


def to_pickup_window(d, world):
    while not d.can_pick_up:
        world.position += SPEED * DT
        d.update(DT)


def test_hitchhiker_waits_on_the_right_shoulder():
    d, world, _, _ = make()
    assert d.start_hitchhiker(impostor=False) and d.mode == HITCH
    assert world.actors[0].kind == "hitchhiker" and world.actors[0].offset > 1.0
    assert d.hint == ("HITCHHIKER AHEAD", "dim") and not d.can_pick_up


def test_picking_up_a_real_hitchhiker_scores_points():
    d, world, score, sfx = make()
    d.start_hitchhiker(impostor=False)
    to_pickup_window(d, world)
    assert d.hint == ("ENTER - PICK UP", "info")
    assert d.pick_up() and d.mode == BOARDING and world.actors == []
    assert sfx.played[-1] == "pickup" and world.speed < SPEED  # you stop for them
    drive(d, world, S.HITCH_BOARDING_TIME + 0.2)
    assert d.mode == RESULT and score.display == S.HITCH_BONUS
    assert d.survived_count == 1 and not d.dead and "saved" in sfx.played
    assert "THANKS FOR THE RIDE" in d.message


def test_picking_up_an_impostor_ends_the_run():
    d, world, score, _ = make()
    d.start_hitchhiker(impostor=True)
    assert world.actors[0].kind == "impostor"
    to_pickup_window(d, world)
    assert d.pick_up()
    for _ in range(int((S.HITCH_BOARDING_TIME + 0.2) / DT)):
        d.update(DT)
    assert d.dead and d.death_event is IMPOSTOR_DEATH and score.display == 0


def test_pick_up_only_works_when_they_are_close():
    d, world, _, sfx = make()
    d.start_hitchhiker(impostor=False)
    assert not d.pick_up() and d.mode == HITCH  # far away
    to_pickup_window(d, world)
    world.position += S.HITCH_PICKUP_RANGE + 2 * S.HITCH_PASS_DISTANCE  # well past them
    d.update(DT)
    assert d.mode == IDLE and not d.pick_up() and "pickup" not in sfx.played


def test_skipping_anyone_costs_nothing_even_an_impostor():
    for impostor in (False, True):
        d, world, score, _ = make()
        d.start_hitchhiker(impostor=impostor)
        drive(d, world, 8)
        assert d.mode == IDLE and not d.dead and score.display == 0
        assert world.actors == []


def test_random_hitchhikers_include_impostors_at_about_the_configured_rate():
    impostors = 0
    for seed in range(400):
        d, *_ = make(seed)
        d.start_hitchhiker()
        impostors += d.impostor
    assert 0.25 < impostors / 400 < 0.45  # HITCH_IMPOSTOR_CHANCE is 0.35


# --- scheduling ----------------------------------------------------------------------------


def test_encounters_start_on_their_own_but_never_while_something_else_is_going_on():
    d, _world, _, _ = make()
    for _ in range(int(S.ROADSIDE_FIRST_DELAY[1] * 2 / DT)):
        d.update(DT, busy=True)
    assert d.mode == IDLE  # busy: nothing starts, and the timers wait
    for _ in range(
        int((S.ROADSIDE_FIRST_DELAY[1] + 1) / DT)
    ):  # free again: one comes soon
        d.update(DT)
        if d.active:
            break
    assert d.mode in (MONSTER, HITCH)


def test_both_kinds_show_up_over_time_and_never_overlap(monkeypatch):
    monkeypatch.setattr(S, "HITCHHIKERS_ENABLED", True)
    d, world, _, _ = make(seed=2)
    seen = set()
    for _ in range(int(900 / DT)):
        world.position = (world.position + SPEED * DT) % world.track.length
        world.headlights.light = 0.0  # keep the monster happy so the run goes on
        d.update(DT)
        if d.mode in (MONSTER, HITCH):
            seen.add(d.mode)
        assert len(world.actors) <= 1
        if d.mode == BOARDING or d.dead:
            d.reset()
    assert seen == {MONSTER, HITCH}


def test_hitchhikers_are_switched_off_by_default_but_monsters_still_come():
    assert S.HITCHHIKERS_ENABLED is False
    d, world, _, _ = make(seed=2)
    seen = set()
    for _ in range(int(900 / DT)):
        world.position = (world.position + SPEED * DT) % world.track.length
        world.headlights.light = 0.0
        d.update(DT)
        seen.add(d.mode)
    assert MONSTER in seen and HITCH not in seen
    d.reset()
    assert d.start_hitchhiker(
        impostor=False
    )  # the code is still there for when they come back


def test_reset_clears_everything():
    d, world, _, sfx = make()
    d.start_monster()
    world.position = S.ROADSIDE_SPAWN_DISTANCE - 10000
    for _ in range(30):
        d.update(DT)
    d.reset()
    assert (
        d.mode == IDLE and world.actors == [] and sfx.loops == {} and d.suspicion == 0
    )


# --- the art: the impostor tell ------------------------------------------------------------


def test_impostor_looks_like_the_real_thing_apart_from_the_eyes():
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from nightdrive.art import Art

    art = Art()
    real, fake = art.sprites["hitchhiker"], art.sprites["impostor"]
    assert real.surf.get_size() == fake.surf.get_size() and real.world_h == fake.world_h
    import pygame

    a = pygame.surfarray.array3d(real.surf).astype(int)
    b = pygame.surfarray.array3d(fake.surf).astype(int)
    differing = int((np.abs(a - b).sum(axis=2) > 0).sum())
    assert 0 < differing <= 4  # a small detail: just the eye pixels
    assert (
        real.glow is None and fake.glow is not None
    )  # ...and a faint glow you can see in the dark
    assert fake.glow_color == "acid"  # a colour no other creature's eyes use
    assert (
        fake.glow_scale > 0.16 and fake.glow_floor > 0.3
    )  # readable from afar, not only up close
    assert art.sprites["monster"].glow_color == "red"
    for name in ("monster", "impostor"):
        assert name in art.jumpscares


# --- the warnings are a one-time tutorial ---------------------------------------------------------


def second_time(kind):
    """A director that has already shown the tutorial for `kind`."""
    d, world, score, sfx = make()
    getattr(d, f"start_{kind}")()
    d.reset()
    return d, world, score, sfx


def test_first_monster_has_the_warning_and_the_bar_later_ones_do_not():
    d, _world, _, _ = make()
    d.start_monster()
    assert d.hint is not None and d.shows_suspicion_bar
    d.reset()
    d.start_monster()  # the second one: just a monster by the road
    assert d.hint is None and not d.shows_suspicion_bar


def test_first_hitchhiker_has_the_prompt_later_ones_do_not():
    d, world, _, _ = make()
    d.start_hitchhiker(impostor=False)
    assert d.hint == ("HITCHHIKER AHEAD", "dim")
    d.reset()
    d.start_hitchhiker(impostor=False)
    assert d.hint is None
    to_pickup_window(d, world)
    assert d.hint is None  # no "ENTER - PICK UP" either


def test_each_kind_has_its_own_tutorial():
    d, _world, _, _ = make()
    d.start_monster()
    d.reset()
    d.start_hitchhiker(impostor=False)  # the first hitchhiker still gets its hint
    assert d.hint == ("HITCHHIKER AHEAD", "dim")
    assert d.seen_hints == {"monster", "hitchhiker"}


def test_the_rules_are_the_same_without_the_hints():
    # a second monster still kills you if the lights are on, and lets you pass if they are off
    d, world, score, _ = second_time("monster")
    d.start_monster()
    world.headlights.light = 1.0
    drive(d, world, 6)
    assert d.dead and d.hint is None
    d, world, score, _ = second_time("monster")
    d.start_monster()
    world.headlights.light = 0.0
    for _ in range(int(7 / DT)):
        world.position += SPEED * DT
        d.update(DT)
        if d.mode == RESULT:
            break
    assert d.mode == RESULT and score.display == S.MONSTER_BONUS
    # a second hitchhiker can still be picked up (and an impostor still kills)
    d, world, score, _ = second_time("hitchhiker")
    d.start_hitchhiker(impostor=False)
    to_pickup_window(d, world)
    assert d.pick_up()
    drive(d, world, S.HITCH_BOARDING_TIME + 0.2)
    assert score.display == S.HITCH_BONUS


def test_results_still_show_as_feedback_without_the_tutorial():
    d, world, _, _ = second_time("monster")
    d.start_monster()
    world.headlights.light = 0.0
    for _ in range(int(7 / DT)):
        world.position += SPEED * DT
        d.update(DT)
        if d.mode == RESULT:
            break
    assert d.hint == ("IT DIDN'T SEE YOU", "good")


def test_the_tutorial_is_remembered_across_directors_and_can_be_switched_off(
    monkeypatch,
):
    seen = set()
    d1, *_ = make()
    d1.seen_hints = seen
    d1.start_monster()
    d2, *_ = make()
    d2.seen_hints = seen  # e.g. the next run's director gets the app's set
    d2.start_monster()
    assert d1.hint is not None and d2.hint is None
    monkeypatch.setattr(
        S, "ROADSIDE_HINTS_ONLY_FIRST", False
    )  # always-on, for experiments
    d3, *_ = make()
    d3.seen_hints = seen
    d3.start_monster()
    assert d3.hint is not None
