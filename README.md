# Night Drive

A calm pixel-art night drive that is (eventually) steered by your attention. Pseudo-3D, first person.
When you lose focus something jumps onto the road and you need to hit the prompted letter fast.

## Run

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m nightdrive
```

Keys: Enter/arrows in the menu, `Esc` back, `F11` fullscreen, `F10` mute all audio.
While driving: `Space` toggles the headlights (they flicker now and then: switch them off and on again).
Debug while driving: `E` random event, `1`-`7` a specific event.

Sound effects are a mix of synthesised sounds and recorded effects. `python -m nightdrive.sfx` lets you audition them (the jump-scare
sounds are loud: lower your volume first, and tune `SFX_VOLUME` in `nightdrive/settings.py`).

## Credits

Sound effects: *Horror SFX Free* by YourPalRob, *Survival Effects [Free]* by Darkworld Audio, and the
monster/beast/abyssal packs by Riria/Ririsaurus.

Music: *Lonely Nightmare* soundtrack pack by Crow Shade, licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Music by Crow Shade.

## Audio assets

Audio is **not stored in git**. The full asset packs go in `asset_packs/`, and
`python tools/import_audio.py` copies the files the game uses into `assets/audio/`. Both are git-ignored, as is
every `*.wav`, `*.mp3` and `*.ogg`. Without those files the game still runs, silently, and the tests that need
them are skipped. See `assets/audio/CREDITS.md` for credits and licenses.
