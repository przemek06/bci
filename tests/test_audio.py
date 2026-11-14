import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from helpers import requires_audio

from nightdrive import settings as S
from nightdrive.audio import Music


@requires_audio
def test_playlist_files_exist():
    for name, gain in S.MUSIC_PLAYLIST:
        assert (S.MUSIC_DIR / f"{name}.mp3").exists(), name
        assert 0 < gain <= 1


def test_target_volume_ducks():
    m = Music(enabled=False)
    assert m.target == S.MUSIC_VOLUME
    m.duck = True
    assert m.target == S.MUSIC_VOLUME * S.MUSIC_DUCK
    assert not hasattr(m, "toggle_mute")  # there is no player-facing mute any more


def test_disabled_music_is_a_silent_noop():
    m = Music(enabled=False)
    m.start()
    m.update(1 / 60)
    m.stop()
    assert not m.playing


@requires_audio
def test_music_plays_fades_in_and_stops():
    pygame.init()
    m = Music(enabled=True)
    assert m.ok
    m.start()
    assert m.playing and pygame.mixer.music.get_busy()
    for _ in range(120):
        m.update(1 / 60)
    assert 0 < m.level <= S.MUSIC_VOLUME
    m.stop()
    assert not pygame.mixer.music.get_busy()
    pygame.quit()
