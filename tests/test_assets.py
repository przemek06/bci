"""The (git-ignored) copy in assets/audio/ must match what the code uses and what the import tool documents."""

import subprocess

from helpers import requires_audio

from nightdrive import samples
from nightdrive import settings as S
from tools import import_audio


def test_every_used_sample_is_documented_and_vice_versa():
    assert set(import_audio.SFX) == set(samples.SAMPLES)


def test_music_playlist_matches_the_import_manifest():
    assert {name for name, _ in S.MUSIC_PLAYLIST} <= set(import_audio.MUSIC)
    assert {name for name, _ in S.MUSIC_PLAYLIST} == set(import_audio.MUSIC)


@requires_audio
def test_assets_audio_has_exactly_the_used_files():
    sfx_files = {f.stem for f in S.SFX_DIR.glob("*") if f.suffix in (".wav", ".mp3")}
    music_files = {f.stem for f in S.MUSIC_DIR.glob("*.mp3")}
    assert sfx_files == set(samples.SAMPLES)
    assert music_files == {name for name, _ in S.MUSIC_PLAYLIST}
    for license_file in import_audio.LICENSES:
        assert (S.AUDIO_DIR / "licenses" / license_file).exists()


def test_audio_is_git_ignored_but_credits_and_licenses_are_tracked():
    def ignored(path):
        result = subprocess.run(
            ["git", "check-ignore", "-q", path], check=False, cwd=import_audio.ROOT
        )
        return result.returncode == 0

    assert ignored("asset_packs/Horror SFX Free/Ambient/Scream.wav")
    assert ignored("assets/audio/sfx/scream.wav")
    assert ignored("assets/audio/music/comfort.mp3")
    assert ignored(
        "anywhere/else/new_pack/some_sound.wav"
    )  # any audio file, not just ours
    assert not ignored("assets/audio/CREDITS.md")
    assert not ignored("assets/audio/licenses/lonely_nightmare_LICENSE.txt")
    assert not ignored("assets/audio/licenses/darkworld_audio_license.pdf")
