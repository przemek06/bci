# CLAUDE.md

Guidance for Claude Code when working in this repository. Read `PLAN.md` for the phased roadmap and current status.

## Project summary

**Night Drive** is a pygame game controlled (passively) by a brain-computer interface. The player sees a pixel-art, pseudo-3D night road from the driver's seat (first person, OutRun-style road projection). No keyboard input is needed while they stay focused: the car just drives, calm music plays. When the player's attention drops, the game spawns a random event on the road (something scary or funny jumping out) followed by a quick-time event (QTE) that needs a fast keypress.

Later, each session gets objectives based on the P300 response (e.g. noticing a lost dog by the roadside). Every BCI-driven mechanic needs a non-BCI fallback so the game can be developed and tested without hardware.

This is a research/experiment setup: sessions are timed, everything is logged, and event markers are sent back over LSL so they can be aligned with the EEG recording.

## Hardware and data flow

- **EEG device:** g.tec Unicorn Hybrid Black (8 EEG channels at 250 Hz, Bluetooth, plus accelerometer/gyro/counter channels). Nominal EEG layout is Fz, C3, Cz, C4, Pz, PO7, Oz, PO8. Verify against the actual stream. Never hardcode channel indices; read the channel labels from the LSL stream info.
- **Streaming:** the EEG is streamed over LSL (Lab Streaming Layer) from a different computer on the same network. The game machine is the LSL *consumer* via `pylsl`. The game also publishes its own marker stream (`NightDriveMarkers`, type `Markers`, string, irregular rate) so LabRecorder can record both.
- **Dev machine:** macOS (darwin). Most development happens without the headset, so a fake EEG publisher (`tools/fake_eeg_stream.py`) is a first-class part of the project.

## Tech stack

- Python (pin a version with reliable wheels for pygame and pylsl; verify before bumping to the newest release)
- `pygame-ce` (community edition; import name is still `pygame`)
- `pylsl` for LSL, `numpy` and `scipy` for signal processing
- `venv` + `pip` with a **single `requirements.txt`** (runtime and dev tools together). Don't split it into multiple requirements files; add `pylsl`/`scipy` to it when BCI work starts.
- Config in TOML (`config/default.toml`), read with the stdlib `tomllib`

## Commands

These are the intended commands. The scaffolding does not exist yet (see PLAN.md Phase 0), so update this section as each one lands.

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt           # all deps
python -m nightdrive --source random      # play with random attention simulation
python -m nightdrive --source keyboard    # play, hold a key to simulate distraction
python -m nightdrive --source bci         # play with live LSL EEG
python tools/fake_eeg_stream.py           # publish synthetic Unicorn-like EEG over LSL
pytest                                    # tests (headless, no hardware)
ruff check . && ruff format .
```

## Architecture (target layout)

```
nightdrive/                  # flat package at the repo root, so `python -m nightdrive` works without installing
  __main__.py, app.py        # entry point, CLI args, main loop, window/scaling
  settings.py                # constants (resolution, road geometry, palette, speeds)
  scenes.py                  # MenuScene, DriveScene
  world.py                   # driving state + drawing the whole first-person view
  track.py                   # procedural looping road (curves, hills, roadside props)
  renderer.py                # pseudo-3D segment projection, fog, sprite scaling
  art.py                     # procedural pixel art: sprites, sky, hills, cockpit
  headlights.py              # headlight switch + random flicker state (pure logic); renderer turns `light` 0..1 into visibility
  qte.py                     # quick-time event logic (random letter, timing, outcome), no drawing
  samples.py                 # recorded SFX (YourPalRob, Darkworld Audio) from `assets/audio/sfx/`: levelling + mapping of samples to game moments
  sfx.py                     # procedural sound effects (numpy synthesis): scares per event, riser, engine; `python -m nightdrive.sfx` to audition
  audio.py                   # background music: shuffled playlist, fade/duck/mute (tracks in `assets/audio/music/`)
  events.py                  # event catalogue (deer, chicken), Actor, EventDirector state machine
  (planned below)
  game/                      # HUD, particles
  attention/                 # AttentionSource abstraction + implementations
    base.py                  #   AttentionSource protocol, AttentionState dataclass
    random_source.py         #   simulated focus, no hardware
    keyboard_source.py       #   manual toggle for debugging
    bci_source.py            #   LSL EEG -> focus level
    processing.py            #   filtering, band power, artifact rejection
    calibration.py           #   per-user baseline
  objectives/                # Objective + ResponseDetector abstractions (P300 vs click)
  lsl/                       # stream resolver, background reader, marker outlet
  session/                   # session state machine, scoring, logging
  assets/                    # procedural sprite and audio generators (+ later real files)
tools/                       # fake EEG streamer, replay, offline analysis scripts
tests/
config/
data/sessions/               # per-session logs (git-ignored)
```

### Core abstractions (keep these boundaries)

1. **`AttentionSource`** is the only thing the game knows about the brain. It produces an `AttentionState(focus: float in 0..1, quality: float in 0..1, t: float)` on request. Implementations: random, keyboard, BCI. The game never imports `pylsl` or touches EEG samples outside `attention/bci_source.py`, `attention/processing.py` and `lsl/`.
2. **`DistractionDetector`** (in the game layer, not in the sources) turns the continuous focus level into discrete "distracted" triggers. It adds hysteresis (focus below threshold for N seconds, with cooldowns) and ignores samples with low `quality`. Because it is shared, random and BCI modes trigger events through exactly the same code path.
3. **`EventDirector`** picks an event from a data-driven catalogue (scary/funny, weights, sprite, sound, QTE type and time limit) and runs it. It does not know what caused the trigger.
4. **`Objective` and `ResponseDetector`** (Phase 11 and later): an objective presents a stimulus (lost dog) and asks a `ResponseDetector` whether the player noticed it. One implementation is a mouse click on the target, the other is P300 classification of EEG epochs time-locked to the stimulus onset marker.
5. **`MarkerSink`**: everything noteworthy (session start, calibration, focus-state changes, event spawn, QTE outcome, stimulus onset) goes through one interface with LSL and file/CSV implementations, so logging and LSL markers can never drift apart.

### Rules that matter

- **Never block the game loop on the network.** LSL pulling runs in a background thread into a thread-safe ring buffer. The main thread only reads the latest computed state. If the stream drops, `AttentionSource` reports low `quality` and the game degrades gracefully (see PLAN.md Phase 9). It must not crash or freeze.
- **Use LSL timestamps** (`pylsl.local_clock()` and per-sample timestamps with time correction) for anything that gets aligned with EEG. Use the game's own monotonic clock for gameplay timing. Don't mix the two without an explicit conversion.
- **Game logic must be testable headless.** Keep simulation (world state, detector, director, QTE timing, scoring) free of drawing code, take time as a parameter (`dt` or an injectable clock) and randomness from a seedable `random.Random`. Tests run with `SDL_VIDEODRIVER=dummy` and `SDL_AUDIODRIVER=dummy` when pygame is needed at all.
- **Pixel art pipeline:** render to a small internal surface (default 320x180) and scale up by an integer factor with nearest-neighbour. Never smooth-scale. Never draw at window resolution.
- **Assets are replaceable.** Sprites and sounds are requested by name through `assets/`. At first they are generated procedurally. Later real files can override them without code changes elsewhere.
- **Everything tunable lives in config** (thresholds, cooldowns, QTE windows, event weights, session length, calibration duration). No magic numbers scattered in game code.
- **Every BCI feature needs a non-BCI path** (random or keyboard source, click-based objective) selectable from the CLI or config.

## Conventions

- **Keep it simple.** Don't overcomplicate tooling or structure. One `requirements.txt`, no extra config layers or abstractions until they are needed.
- Python with type hints, dataclasses for plain state, `Protocol`/ABC for the abstractions above. Format and lint with ruff.
- Match the style of the surrounding code. Keep modules small and single-purpose.
- Tests for pure logic (detector, director, QTE, scoring, band power on synthetic signals). Don't write tests that need a real display, audio device or headset.
- Don't commit session data, recordings or secrets (`data/` is git-ignored). Keep large binaries out of git unless they are final assets.
- Commit only when asked.

## EEG and signal-processing notes (for whoever touches `attention/`)

- The Unicorn uses hybrid (dry-ish) electrodes over Bluetooth. Expect noisy signal, motion/blink/muscle artifacts, and occasional packet loss. Check the validation channel/counter where the stream provides it.
- Pipeline sketch: notch (50 Hz, Europe; make it configurable), band-pass about 1-40 Hz, sliding window (about 2-4 s, 50% overlap or updated about every 0.25-0.5 s), simple amplitude-based artifact rejection, band power (theta 4-8, alpha 8-13, beta 13-30 Hz), then a candidate focus index.
- Candidate indices to compare offline, behind a pluggable interface: beta/(alpha+theta) engagement index, frontal theta, occipital alpha (Oz, PO7, PO8; higher alpha suggests lower external attention). Pick by looking at recorded calibration data, not by assumption.
- Always normalise per user and per session using a calibration baseline (focused task versus relaxed/mind-wandering). Map to 0..1 with a robust scaler and smooth over time. Absolute band-power values are not comparable between people or sessions.
- Treat "focus" from consumer-grade EEG as a noisy, probabilistic signal. The detector's hysteresis exists because of that.
- P300 (later): oddball-style stimulus with rare targets, epochs about -200 to 800 ms around the onset marker, baseline-corrected, from Pz/Cz (also Fz/Oz). Single-trial detection is hard, so expect to average over repeated stimuli or use a simple LDA classifier trained on a short calibration block. Stimulus onset must be marked at the frame the stimulus actually appears (flip time), not when it was scheduled.

## Audio assets

- The **full downloaded packs** live in `asset_packs/` (git-ignored, ~400 MB). Never load from there and never commit it.
- The game reads only the **working copy in `assets/audio/`** (`music/*.mp3`, `sfx/<key>.wav`), under clean names. **Audio never goes into git or its history**: `.gitignore` blocks `assets/audio/music/`, `assets/audio/sfx/` and every `*.wav`/`*.mp3`/`*.ogg`/`*.flac`. Only `assets/audio/CREDITS.md` and `licenses/` are tracked. A fresh clone has no audio: put the packs in `asset_packs/` and run `python tools/import_audio.py`; tests that need audio are skipped until then (`requires_audio` in `tests/conftest.py`). Never `git add -f` an audio file.
- To use a new sound: add it to `tools/import_audio.py` (key -> file in the pack), add the key and its target loudness to `nightdrive/samples.py`, then run `python tools/import_audio.py`. `tests/test_assets.py` fails if the code, the manifest and the folder disagree (including unused files).
- Licenses: Lonely Nightmare is CC BY 4.0 (credit required); Darkworld Audio allows use in games without attribution (license copied to `assets/audio/licenses/`, tracked); Horror SFX Free shipped without a license file (credit given anyway, terms unverified). The Ririsaurus packs (creature vocals) allow use but say **do not redistribute**: satisfied as long as the audio stays out of git (it does: see above).

## Status

Done: menu, endless pseudo-3D night drive, events + random-letter QTE (deer, chicken, Trump, yeti, scooter kid on a crosswalk, truck at a crossroads, deep one). Debug keys in the drive scene: `E` random event, `1`-`7` a specific event (order of `CATALOGUE`). Quiet shuffled music (Lonely Nightmare, CC BY 4.0, Crow Shade: keep the in-game and README credit), ducks during a QTE, cuts to silence on the jump scare, `F10` mutes music and effects. Recorded SFX (Horror SFX Free by YourPalRob, Darkworld Audio Survival Effects, Ririsaurus creature packs; credits in the menu and README) are layered under the synth scares (crash, thud, glass, the driver's cry) and used for creature-appear sounds, the headlight switch (dashboard button, 3 variants), flicker buzz loop, panic breathing during a QTE, a gasp when a creature appears, an exhale when saved, a frog-ambience loop and rare distant one-shots (`AMBIENT_ONESHOTS` in settings; they can distract, so switch off for strict experiments). The deer, yeti and deep-one scares are now fully recorded (shrieks, roar, DeepOne growls); still synthesised in `sfx.py`: truck/chicken/scooter/Trump scares, riser, saved, zap, engine, and the unused fallbacks alert/click (`tests/test_sfx.py::test_synthesised_sounds_left` tracks the list). `SFX_VOLUME` scales everything and the scares are loud on purpose. Headlights: `Space` toggles them (letters are all QTE keys, so don't bind letters); they flicker every 25-50 s until switched off and on again; off = near-darkness; dashboard lamp + hint; if the lights are off or flickering when an event fires, the QTE window is `QTE_WINDOW_DARK` (1.0 s) instead of `QTE_WINDOW` (1.5 s). Failing a QTE ends the run: full-screen jump scare (close-up per creature), then a game-over screen with retry. Events are currently triggered by a random timer or the `E` key via `DriveScene.on_distracted()`, a placeholder for the attention input. Next: `AttentionSource` + `DistractionDetector` (PLAN.md Phase 3), then session logging. No BCI yet.
