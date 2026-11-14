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
  calibration_scene.py       # full-screen gaze calibration (draws to the window itself)
  gaze/                      # webcam/mouse eye tracking, calibration, GazeMonitor (see the gaze section)
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

## Implemented: g.Pype BCI + eyes-closed ghost scare

An experimental feature that already exists. It is separate from the planned `AttentionSource` / `DistractionDetector` path (that still does not exist). A ghost appears suddenly; the player must keep their eyes closed for `hold_s` (3 s) within `deadline_s` (8 s), detected from occipital alpha (alpha rises strongly when the eyes close). Fail and the ghost kills the run (full-screen jump scare, then the normal game-over screen). Keyboard fallback: hold SPACE.

```
python tools/gpype_alpha_stream.py        # terminal 1: Unicorn -> g.Pype -> LSL stream "NightDriveAlpha"
python tools/gpype_alpha_stream.py --simulate   # same, no headset (fake 10 Hz signal, alpha never "jumps")
python -m nightdrive --eyes bci           # terminal 2: play with the headset (default is --eyes keyboard)
python -m nightdrive --eyes bci --no-eyes-log   # same, without the live console log
python tools/lsl_alpha_print.py           # sanity check: prints relative alpha from the stream
python tools/eyes_closed_demo.py          # try calibration + the detector in the console, no game
```

In the drive scene the debug key **G** spawns a ghost immediately (E still spawns a road event, `1`-`7` a specific one).

**Data flow.** `tools/gpype_alpha_stream.py` (own process, because g.Pype's app loop wants the main thread, which pygame also needs): `HybridBlack` -> `Router` (EEG channels 5,6,7 = PO7, Oz, PO8, nominal layout; `--channels` overrides) -> `Bandpass` 1-40 Hz -> `Bandstop` at mains (`--mains`, 50 Hz default) -> `FFT` (1 s window, 75% overlap, about 4 updates/s) -> `BandPower` alpha 8-12 Hz and broadband 2-30 Hz -> `LSLSender`. The stream carries `(alpha, broad)` per channel. In the game: `lsl/alpha_reader.py` (background thread, never blocks the loop) -> relative alpha = sum(alpha) / sum(broad) -> `attention/eyes_closed.py` `EyesClosedDetector` -> `attention/eyes_source.py` -> `ghost/`.

**Detector** (pure logic, time passed in, tested headless). Calibrated on eyes-open relative alpha: threshold = median + max(3 x robust spread, 0.10). Then a 1 s moving average, hysteresis (closed above the threshold, open again below a lower release level), a hold timer that forgives dips shorter than `grace_s` (0.5 s), and loss of signal resets the hold. All tunables are in `EyesClosedConfig` (`eyes_closed.py`) and `GhostConfig` (`ghost/encounter.py`), deliberately not in `settings.py`; fold them into `config/default.toml` when that exists.

**Eye sources** (`attention/eyes_source.py`) share one interface and the same detector, so the keyboard path exercises the real logic: `KeyboardEyes` (hold SPACE) and `BciEyes` (auto-calibrates from the first ~17 s of eyes-open data after the stream appears, prints a live `[eyes] raw/avg/thr` log). `App` updates `app.eyes` every frame in every scene.

**Ghost package** (`nightdrive/ghost/`): `encounter.py` (pure state machine: IDLE/ACTIVE/PASSED/DEAD, deadline, pauses and cancels without killing the player if the EEG drops), `visuals.py` (procedural ghost art + overlay), `challenge.py` (`GhostChallenge`, the single object the drive scene talks to). Death reuses `GameOverScene` through the `"ghost"` jump-scare image registered in `app.assets.jumpscares`.

**Merge notes.** Everything is new files except these small hooks: `scenes.py` `DriveScene` (import, `self.ghost`, update, draw, G key, an E-key guard, ESC reset), `app.py` (`--eyes`, `--no-eyes-log`, `app.eyes`, per-frame update, stop on exit), and `requirements.txt` (`gpype[devices,lsl]`, `pylsl`, `scipy`). Tests: `tests/test_eyes_closed.py`, `tests/test_ghost.py`.

**How the ghost and the audio/headlight features fit together** (merge of the two lines of work). `App(seed, eyes, eyes_log, audio, gaze, camera, gaze_model)`: `main()` passes everything by keyword, so keep adding new options at the end. While a ghost challenge is running: road events cannot start (`DriveScene.on_distracted` returns early), the music ducks, and in keyboard eyes mode SPACE means "eyes closed" so it does not flip the headlights (BCI mode keeps the headlight switch). Ghost sounds: a moan when it appears (`ghost_moan`) and a scream + the driver's cry on death (`scare_ghost`), both from Horror SFX Free via `assets/audio/sfx/`. Tests: `tests/test_integration.py`.

**Known stale tests on main (not caused by the merge):** `test_closed_eyes_pass_after_hold` and `test_ghost_kills_if_eyes_stay_open` assume the old tunings (hold 3 s, ghost deadline 8 s) while `EyesClosedConfig`/`GhostConfig` now say 2 s and 10 s. Either the tests or the config/docs need updating by the owner of that feature.

**Known gaps.**
- Eyes-closed detection has been tested live on the Unicorn and works: the eyes-open calibration gives a sensible threshold and closing the eyes passes the ghost. It has only been tried on one person so far. The default threshold settings (`k_spread`, `min_rise`) may need tuning for other people or noisier electrode contact; use the `[eyes]` console log to check.- Channel indices 5,6,7 are the nominal Unicorn layout and are not read from stream labels (see the "never hardcode channel indices" rule).
- No artifact rejection (blinks, jaw, motion). The OSCAR option of `HybridBlack` is off.
- Windows: pair the Unicorn in Bluetooth first and close Unicorn Suite before streaming (otherwise `OPEN_DEVICE_FAILED`). macOS: the g.Pype docs say the amplifier's app loop must run on the main thread there; the publisher currently waits on `input()` and has not been tried on macOS.

## Implemented: eye gaze (webcam / mouse), optional

Gaze tracking drives the *distraction* path, which is what the random timer stood in for. Off by default; enable with `--gaze webcam|mouse` or the **EYE TRACKING** menu entry (then **CALIBRATE EYES**, a full-screen dot calibration saved to `data/gaze_calibration.json`). Usage, camera/phone options (scrcpy, IP cameras, several cameras), the L2CS-Net / MediaPipe models and the geometric model are documented in `README.md` ("Eye tracking").

Code: `nightdrive/gaze/` (`tracker.py` `GazeTracker` + `GazeMonitor`, `webcam_source.py`, `mouse_source.py`, `l2cs.py`, `calibration.py`, `geometry.py`, `features.py`, `session.py`, `download.py`, `base.py`), `nightdrive/calibration_scene.py` (a scene that draws straight to the window: `draws_window = True`, handled in `App.run`), tests in `tests/test_gaze.py`. Gaze is stored in desktop coordinates; `App.gaze_canvas_point()` maps it onto the game canvas. Heavy dependencies (`mediapipe`, `opencv-python`, `torch`) are only needed when gaze is used.

**How it fits with the rest (merge of the eye-gaze branch with main).** In the drive scene, when the gaze tracker is `ready`, `GazeMonitor` (looking outside `GAZE_ROAD_BOX` for `GAZE_AWAY_TIME`, then `GAZE_COOLDOWN`) triggers `on_distracted()` *instead of* the random timer; without gaze the timer is used. A running ghost challenge blocks both. Keys: **`G` = spawn a ghost** (main's debug key), **`Tab` = show/hide the gaze marker** (the branch originally used G; every letter is a QTE answer, so non-letters are preferred for UI). The menu has 3 entries (4 with a calibratable source) and was re-spaced so it does not collide with the credit lines. Tests: `tests/test_integration.py` (gaze section).

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

Done: menu, endless pseudo-3D night drive, events + random-letter QTE (deer, chicken, Trump, yeti, scooter kid on a crosswalk, truck at a crossroads, deep one). Debug keys in the drive scene: `E` random event, `1`-`7` a specific event (order of `CATALOGUE`), `G` ghost, `Tab` gaze marker. Quiet shuffled music (Lonely Nightmare, CC BY 4.0, Crow Shade: keep the in-game and README credit), ducks during a QTE, cuts to silence on the jump scare, `F10` mutes music and effects. Recorded SFX (Horror SFX Free by YourPalRob, Darkworld Audio Survival Effects, Ririsaurus creature packs; credits in the menu and README) are layered under the synth scares (crash, thud, glass, the driver's cry) and used for creature-appear sounds, the headlight switch (dashboard button, 3 variants), flicker buzz loop, panic breathing during a QTE, a gasp when a creature appears, an exhale when saved, a frog-ambience loop and rare distant one-shots (`AMBIENT_ONESHOTS` in settings; they can distract, so switch off for strict experiments). The deer, yeti and deep-one scares are now fully recorded (shrieks, roar, DeepOne growls); still synthesised in `sfx.py`: truck/chicken/scooter/Trump scares, riser, saved, zap, engine, and the unused fallbacks alert/click (`tests/test_sfx.py::test_synthesised_sounds_left` tracks the list). `SFX_VOLUME` scales everything and the scares are loud on purpose. Headlights: `Space` toggles them (letters are all QTE keys, so don't bind letters); they flicker every 25-50 s until switched off and on again; off = near-darkness; dashboard lamp + hint; if the lights are off or flickering when an event fires, the QTE window is `QTE_WINDOW_DARK` (1.0 s) instead of `QTE_WINDOW` (1.5 s). Failing a QTE ends the run: full-screen jump scare (close-up per creature), then a game-over screen with retry. Events are currently triggered by a random timer or the `E` key via `DriveScene.on_distracted()`, a placeholder for the attention input. Next: `AttentionSource` + `DistractionDetector` (PLAN.md Phase 3), then session logging. BCI exists only as the experimental eyes-closed ghost scare (see "Implemented: g.Pype BCI + eyes-closed ghost scare" above); the attention-driven events are still not wired to EEG.
