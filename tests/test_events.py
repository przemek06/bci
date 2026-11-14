import random
from types import SimpleNamespace

from nightdrive import settings as S
from nightdrive.events import AFTERMATH, DEAD, IDLE, IMPACT, QTE, EventDirector
from nightdrive.qte import SUCCESS, TIMEOUT, WRONG_KEY, Qte, random_letter


def make_world():
    return SimpleNamespace(
        position=0.0,
        speed=S.CRUISE_SPEED,
        cruise=S.CRUISE_SPEED,
        speed_rate=0.8,
        actors=[],
        headlights=SimpleNamespace(on=True, flickering=False),
        track=SimpleNamespace(
            length=600_000, mark=lambda *a: None, clear_marks=lambda: None
        ),
    )


def run(director, world, seconds, dt=1 / 60):
    for _ in range(int(seconds / dt)):
        world.position = (world.position + world.speed * dt) % world.track.length
        director.update(dt)


def test_qte_outcomes():
    q = Qte("K", 1.5)
    q.update(0.5)
    q.press("k")
    assert q.result == SUCCESS and q.reaction == 0.5

    q = Qte("K", 1.5)
    q.press("J")
    assert q.result == WRONG_KEY

    q = Qte("K", 1.5)
    q.update(1.6)
    assert q.result == TIMEOUT and q.remaining == 0


def test_random_letter_avoids_previous():
    rng = random.Random(0)
    letters = {random_letter(rng, "A") for _ in range(200)}
    assert "A" not in letters and len(letters) > 10


def test_success_brakes_and_returns_to_idle():
    w = make_world()
    d = EventDirector(w, random.Random(1))
    assert d.trigger() and d.state == QTE and len(w.actors) == 1
    assert not d.trigger()  # already running
    run(d, w, 0.4)
    d.press(d.qte.letter)
    d.update(1 / 60)
    assert d.state == AFTERMATH and d.saved_count == 1
    assert w.cruise < S.CRUISE_SPEED
    run(d, w, S.AFTERMATH_TIME + 0.5)
    assert d.state == IDLE and w.actors == [] and w.cruise == S.CRUISE_SPEED
    assert d.history[0]["result"] == SUCCESS


def test_wrong_key_ends_game_when_reaching_creature():
    w = make_world()
    d = EventDirector(w, random.Random(1))
    d.trigger()
    wrong = "A" if d.qte.letter != "A" else "B"
    d.press(wrong)
    d.update(1 / 60)
    assert d.state == IMPACT
    run(d, w, S.QTE_WINDOW + 0.5)  # long enough for the car to reach the creature
    assert d.state == DEAD
    assert d.history[0]["result"] == WRONG_KEY


def test_timeout_ends_game():
    w = make_world()
    d = EventDirector(w, random.Random(2))
    d.trigger()
    run(d, w, S.QTE_WINDOW + 1.0)
    assert d.state == DEAD
    assert d.history[0]["result"] == TIMEOUT
    assert d.saved_count == 0


def test_every_event_has_its_art():
    from nightdrive.art import Art
    from nightdrive.events import CATALOGUE

    art = Art()
    for ev in CATALOGUE:
        assert ev.sprite in art.sprites, ev.name
        assert ev.name in art.jumpscares, ev.name


def test_every_event_can_be_survived_and_can_kill():
    from nightdrive.events import CATALOGUE

    for ev in CATALOGUE:
        for press_right in (True, False):
            w = make_world()
            d = EventDirector(w, random.Random(0))
            d._last_event = None
            d.rng = SimpleNamespace(
                choice=lambda seq, ev=ev: ev if ev in seq else seq[0],
                uniform=random.Random(0).uniform,
            )
            assert d.trigger() and d.event is ev
            if press_right:
                d.press(d.qte.letter)
                run(d, w, S.AFTERMATH_TIME + 0.5)
                assert d.state == IDLE and w.actors == [], ev.name
            else:
                run(d, w, S.QTE_WINDOW + 1.5)
                assert d.state == DEAD, ev.name


def test_bad_headlights_shorten_the_qte_window():
    for on, flickering, expected in (
        (True, False, S.QTE_WINDOW),
        (False, False, S.QTE_WINDOW_DARK),
        (True, True, S.QTE_WINDOW_DARK),
    ):
        w = make_world()
        w.headlights.on, w.headlights.flickering = on, flickering
        d = EventDirector(w, random.Random(1))
        d.trigger()
        assert d.qte.window == expected
        # the creature is placed so the car reaches it right as the window ends
        assert abs(w.actors[0].z - w.speed * expected) < 1
        run(d, w, expected + 0.05)
        assert d.qte.result == TIMEOUT
        assert d.history == [] or d.history[0]["window"] == expected
