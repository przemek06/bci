import pytest

from nightdrive import settings as S

# Audio is git-ignored, so a fresh clone has none until `python tools/import_audio.py` is run.
requires_audio = pytest.mark.skipif(
    not any(S.SFX_DIR.glob("*")) or not any(S.MUSIC_DIR.glob("*")),
    reason="assets/audio is empty: run tools/import_audio.py (needs asset_packs/)",
)
