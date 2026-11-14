from nightdrive import settings as S
from nightdrive.track import Track


def test_track_is_seeded():
    a, b = Track(1), Track(1)
    assert [s.curve for s in a.segments] == [s.curve for s in b.segments]
    assert [s.y2 for s in a.segments] != [s.y2 for s in Track(2).segments]


def test_track_loops_seamlessly():
    t = Track(5)
    assert abs(t.segments[0].y1 - t.segments[-1].y2) < 1e-6
    assert t.length == len(t.segments) * S.SEGMENT_LENGTH


def test_segments_are_contiguous():
    t = Track(5)
    for prev, nxt in zip(t.segments, t.segments[1:]):
        assert prev.z2 == nxt.z1 and prev.y2 == nxt.y1


def test_segment_at_wraps():
    t = Track(5)
    assert t.segment_at(t.length + 1) is t.segments[0]
