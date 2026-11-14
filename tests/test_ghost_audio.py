"""GhostAudio is pure logic over a sound player, so it is tested here with a fake one."""

import itertools
import random
from types import SimpleNamespace

import numpy as np

from nightdrive import samples
from nightdrive import settings as S
from nightdrive.ghost_audio import ACTIVE, DEAD, IDLE, PASSED, GhostAudio


class FakeSfx:
    def __init__(self):
        self.calls = []
        self.loops = {}

    def play(self, name, pan=None):
        self.calls.append((name, pan))

    def loop(self, name, volume=1.0):
        self.loops[name] = volume

    def stop_loop(self, name):
        self.loops.pop(name, None)

    def played(self):
        return [name for name, _ in self.calls]


def make(seed=1):
    ghost = SimpleNamespace(
        encounter=SimpleNamespace(
            state=IDLE, time_left=10.0, cfg=SimpleNamespace(deadline_s=10.0)
        ),
        eyes_state=None,
    )
    sfx = FakeSfx()
    return GhostAudio(sfx, ghost, random.Random(seed)), sfx, ghost


def run(audio, seconds, dt=1 / 30):
    for _ in range(int(seconds / dt)):
        audio.update(dt)


def test_nothing_plays_while_idle():
    audio, sfx, _ = make()
    run(audio, 5)
    assert sfx.calls == [] and sfx.loops == {}


def test_appearing_plays_the_stinger_and_starts_the_drone():
    audio, sfx, ghost = make()
    ghost.encounter.state = ACTIVE
    audio.update(1 / 30)
    assert sfx.played()[0] == "ghost_appear"
    assert "ghost_rumble" in sfx.loops


def test_drone_swells_as_the_deadline_nears():
    audio, sfx, ghost = make()
    ghost.encounter.state = ACTIVE
    ghost.encounter.time_left = 10.0
    audio.update(1 / 30)
    calm = sfx.loops["ghost_rumble"]
    ghost.encounter.time_left = 1.0
    audio.update(1 / 30)
    assert sfx.loops["ghost_rumble"] > calm * 2
    assert sfx.loops["ghost_rumble"] <= S.GHOST_RUMBLE_VOLUME


def test_eyes_open_rattles_chains_creaks_and_knocks_panned_around_you():
    audio, sfx, ghost = make()
    ghost.encounter.state = ACTIVE
    run(audio, 30)
    shots = [(n, p) for n, p in sfx.calls if n != "ghost_appear"]
    assert len(shots) >= 8
    kinds = {n.split("_")[1] for n, _ in shots}
    assert kinds <= {"chain", "creak", "knock"} and len(kinds) >= 2
    pans = [p for _, p in shots]
    assert all(-1 <= p <= 1 for p in pans) and min(pans) < 0 < max(pans)


def test_rattles_come_faster_near_the_deadline():
    def count(time_left):
        audio, sfx, ghost = make(seed=3)
        ghost.encounter.state = ACTIVE
        ghost.encounter.time_left = time_left
        run(audio, 60)
        return len(sfx.calls)

    assert count(0.5) > count(9.5) * 1.3


def test_eyes_closed_means_footsteps_circling_you():
    audio, sfx, ghost = make()
    ghost.encounter.state = ACTIVE
    ghost.eyes_state = SimpleNamespace(closed=True)
    run(audio, 10)
    steps = [(n, p) for n, p in sfx.calls if n != "ghost_appear"]
    assert len(steps) >= 8 and all(n.startswith("ghost_step_") for n, _ in steps)
    pans = [p for _, p in steps]
    assert all(
        a * b < 0 for a, b in itertools.pairwise(pans)
    )  # alternates left / right


def test_passing_stops_the_drone_and_plays_relief():
    audio, sfx, ghost = make()
    ghost.encounter.state = ACTIVE
    run(audio, 2)
    ghost.encounter.state = PASSED
    audio.update(1 / 30)
    assert "ghost_rumble" not in sfx.loops and sfx.played()[-1] == "ghost_relief"


def test_death_and_signal_loss_stop_the_drone_without_relief():
    for end_state in (DEAD, IDLE):
        audio, sfx, ghost = make()
        ghost.encounter.state = ACTIVE
        run(audio, 2)
        ghost.encounter.state = end_state
        audio.update(1 / 30)
        assert "ghost_rumble" not in sfx.loops
        assert "ghost_relief" not in sfx.played()


def test_stop_silences_everything():
    audio, sfx, ghost = make()
    ghost.encounter.state = ACTIVE
    audio.update(1 / 30)
    audio.stop()
    assert sfx.loops == {}


def test_same_seed_same_sounds():
    def sounds(seed):
        audio, sfx, ghost = make(seed)
        ghost.encounter.state = ACTIVE
        run(audio, 20)
        return sfx.calls

    assert sounds(5) == sounds(5) and sounds(5) != sounds(6)


def test_loops_are_crossfaded_seamless():
    sr = 44100
    t = np.arange(10 * sr) / sr
    tone = np.stack([np.sin(2 * np.pi * 220 * t)] * 2, axis=1).astype(np.float32)
    loop = samples.make_loopable(tone, sr)
    step = np.abs(np.diff(loop[:, 0])).max()
    assert np.abs(loop[0, 0] - loop[-1, 0]) <= step * 1.5  # no click where it wraps
    assert len(loop) < len(tone)  # the overlap was consumed
    short = tone[:sr]  # too short to crossfade: returned untouched
    assert samples.make_loopable(short, sr) is short
