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
  ssvep_demo.py              # SSVEP demo window: several buttons flickering at different frequencies + which one you look at (python -m nightdrive.ssvep_demo)
  attention/ssvep_sim.py     # SimulatedEeg / SimulatedSource: synthetic EEG for demos, tools and tests (no headset)
  attention/ssvep.py         # SSVEP measure (SNR in dB at the flicker frequency) + SsvepDetector (one target: calibrate, hold, re-arm) + SsvepSelector (several targets: which one?): pure logic
  lsl/eeg_reader.py          # threaded reader of the raw `NightDriveEEG` stream (rolling window)
  light_switch.py            # LightSwitch interface, ClickLightSwitch, SsvepLightSwitch + the stimulus flicker function
  roadside.py                # the roadside monster (lights off!) and hitchhikers (some are impostors): pure logic
  score.py                   # the run's score (pure logic): rises with time, `add(points, reason)` for everything else; shown on the dashboard
  headlights.py              # headlight switch + random flicker state (pure logic); renderer turns `light` 0..1 into visibility
  calibration_scene.py       # full-screen gaze calibration (draws to the window itself)
  gaze/                      # webcam/mouse eye tracking, calibration, GazeMonitor (see the gaze section)
  qte.py                     # quick-time event logic (random letter, timing, outcome), no drawing
  samples.py                 # recorded SFX (YourPalRob, Darkworld Audio) from `assets/audio/sfx/`: levelling + mapping of samples to game moments
  ghost_audio.py             # sound for the eyes-closed ghost (pure logic over the Sfx player; drive scene feeds it the ghost state)
  sfx.py                     # sound effects: the Sfx player (one-shots with stereo pan, loops, composites layered from recordings; **no synthesis**); `python -m nightdrive.sfx` to audition
  audio.py                   # background music: shuffled playlist, fade/duck (tracks in `assets/audio/music/`)
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

An experimental feature that already exists. It is separate from the planned `AttentionSource` / `DistractionDetector` path (that still does not exist). A ghost appears suddenly with the prompt "RELAX AND CLOSE YOUR EYES"; for the first `GhostConfig.relax_s` (3 s) nothing counts and no bars show, so the player can calm down; then the player must keep their eyes closed for `hold_s` (`EyesClosedConfig`, currently 1.2 s; the on-screen text deliberately says `GhostConfig.prompt_seconds` = 5 s instead) within `deadline_s` (`GhostConfig`, 10 s, counted from the end of the relax time), detected from occipital alpha (alpha rises strongly when the eyes close). Fail and the ghost kills the run (full-screen jump scare, then the normal game-over screen). Keyboard fallback: hold SPACE.

```
python tools/gpype_alpha_stream.py        # terminal 1: Unicorn -> g.Pype -> LSL stream "NightDriveAlpha"
python tools/gpype_alpha_stream.py --simulate   # same, no headset (fake 10 Hz signal, alpha never "jumps")
python -m nightdrive --eyes bci           # terminal 2: play with the headset (default is --eyes keyboard)
python -m nightdrive --eyes bci --no-eyes-log   # same, without the live console log
python tools/lsl_alpha_print.py           # sanity check: prints relative alpha from the stream
python tools/eyes_closed_demo.py          # try calibration + the detector in the console, no game
```

In the drive scene the debug key **G** spawns a ghost immediately (E still spawns a road event, `1`-`7` a specific one).

**Data flow.** `tools/gpype_alpha_stream.py` (own process, because g.Pype's app loop wants the main thread, which pygame also needs): `HybridBlack(enable_oscar=True)` (g.Pype's OSCAR artifact removal on the whole stream, so both branches get cleaned data) -> `Router` with two separate branches, each with its own filters, FFT and band power. The ghost (alpha) branch, with the same filters as the original: occipital channels (EEG channels 5,6,7 = PO7, Oz, PO8, nominal layout; `--channels` overrides) -> `Bandpass` 1-40 Hz -> `Bandstop` at mains (`--mains`, 50 Hz default) -> `FFT` (1 s window, 75% overlap, about 4 updates/s) -> `BandPower` alpha 8-12 Hz and broadband 2-30 Hz -> `LSLSender` `NightDriveAlpha`, carrying `(alpha, broad)` per channel. The attention branch is described in its own section below. In the game: `lsl/alpha_reader.py` (background thread, never blocks the loop) -> relative alpha = sum(alpha) / sum(broad) -> `attention/eyes_closed.py` `EyesClosedDetector` -> `attention/eyes_source.py` -> `ghost/`.

**Detector** (pure logic, time passed in, tested headless). Calibrated on eyes-open relative alpha: threshold = median + max(3 x robust spread, 0.10). Then a 1 s moving average, hysteresis (closed above the threshold, open again below a lower release level), a hold timer that forgives dips shorter than `grace_s` (0.5 s), and loss of signal resets the hold. All tunables are in `EyesClosedConfig` (`eyes_closed.py`) and `GhostConfig` (`ghost/encounter.py`), deliberately not in `settings.py`; fold them into `config/default.toml` when that exists.

**Eye sources** (`attention/eyes_source.py`) share one interface and the same detector, so the keyboard path exercises the real logic: `KeyboardEyes` (hold SPACE) and `BciEyes` (auto-calibrates from the first ~17 s of eyes-open data after the stream appears, prints a live `[eyes] raw/avg/thr` log). `App` updates `app.eyes` every frame in every scene.

**Ghost package** (`nightdrive/ghost/`): `encounter.py` (pure state machine: IDLE/ACTIVE/PASSED/DEAD, deadline, pauses and cancels without killing the player if the EEG drops), `visuals.py` (procedural ghost art + overlay), `challenge.py` (`GhostChallenge`, the single object the drive scene talks to). Death reuses `GameOverScene` through the `"ghost"` jump-scare image registered in `app.assets.jumpscares`.

**Merge notes.** Everything is new files except these small hooks: `scenes.py` `DriveScene` (import, `self.ghost`, update, draw, G key, an E-key guard, ESC reset), `app.py` (`--eyes`, `--no-eyes-log`, `app.eyes`, per-frame update, stop on exit), and `requirements.txt` (`gpype[devices,lsl]`, `pylsl`, `scipy`). Tests: `tests/test_eyes_closed.py`, `tests/test_ghost.py`.

**How the ghost and the audio/headlight features fit together** (merge of the two lines of work). `App(seed, eyes, eyes_log, audio, gaze, camera, gaze_model, lights)`: `main()` passes everything by keyword, so keep adding new options at the end. While a ghost challenge is running: road events cannot start (`DriveScene.on_distracted` returns early), the music ducks, and in keyboard eyes mode SPACE means "eyes closed" (it no longer has any headlight meaning). Ghost sounds (`nightdrive/ghost_audio.py`, `GhostAudio`): on appearing a stinger + eerie bell + moan (`ghost_appear`) and a low drone loop that swells as the deadline nears; with eyes open, chains/creaks/knocks panned around you, more often near the deadline; with eyes shut, footsteps circling you; on success the drone stops and a swoosh + exhale play (`ghost_relief`); on death the game-over scene plays `scare_ghost` (ghost scream + the driver's own scream + cry + drone). Sources: FilmCow (stinger, bell, drone, chains, creaks, knocks, footsteps, swoosh, scream) and Horror SFX Free (moan, ghost scream). Tests: `tests/test_integration.py`.

**Known stale tests on main (not caused by the merge):** `test_closed_eyes_pass_after_hold` and `test_ghost_kills_if_eyes_stay_open` assume the old tunings (hold 3 s, ghost deadline 8 s) while `EyesClosedConfig`/`GhostConfig` now say 2 s and 10 s. Either the tests or the config/docs need updating by the owner of that feature.

**Known gaps.**
- Eyes-closed detection has been tested live on the Unicorn and works: the eyes-open calibration gives a sensible threshold and closing the eyes passes the ghost. It has only been tried on one person so far. The default threshold settings (`k_spread`, `min_rise`) may need tuning for other people or noisier electrode contact; use the `[eyes]` console log to check.
- Channel indices 5,6,7 are the nominal Unicorn layout and are not read from stream labels (see the "never hardcode channel indices" rule).
- No artifact rejection (blinks, jaw, motion) in our own code; the only artifact handling is g.Pype's OSCAR, switched on with the documented `HybridBlack(enable_oscar=True)` (config key `AmplifierSource.Configuration.Keys.ENABLE_OSCAR`: "Whether OSCAR artifact removal runs on this stream"). It applies to the whole stream, so the alpha / eyes-closed branch and the attention branch both get OSCAR-cleaned data; the g.Pype docs describe no per-channel or per-branch option. A private, undocumented `Oscar` node was tried on the attention branch only and dropped (unverified, outside the documented placement).
- Windows: pair the Unicorn in Bluetooth first and close Unicorn Suite before streaming (otherwise `OPEN_DEVICE_FAILED`). macOS: the g.Pype docs say the amplifier's app loop must run on the main thread there; the publisher currently waits on `input()` and has not been tried on macOS.

## Implemented: attention index -> focus to pass quick-time events

Experimental. During a quick-time event (the letter prompt) the player can, instead of pressing the key, focus hard: if their attention level stays well above their own normal for a moment, the event is passed as if the right key had been pressed. This is the first real `AttentionSource` (see Core abstractions); there is still no `DistractionDetector`. (An earlier version that raised the scare frequency when attention dropped was removed.)

```
python tools/gpype_alpha_stream.py                       # publishes BOTH LSL streams (alpha + bands)
python -m nightdrive --attention bci                     # play with the live attention index
python -m nightdrive --attention keyboard                # no headset: hold UP to raise the level, DOWN to lower it
python -m nightdrive --attention random                  # no headset: the level drifts randomly
python -m nightdrive --eyes bci --attention bci          # ghost scare and focus-to-pass together
python tools/lsl_beta_high_print.py                      # standalone, like lsl_alpha_print.py: relative high-beta bar
python tools/lsl_gamma_print.py                          # same for gamma
python tools/lsl_attention_print.py                      # standalone: the calculated attention level (1.0 = normal) as a ### bar, | = focus-pass line
```
`--attention off` (default) leaves the game unchanged. `--no-attention-log` silences the console log.

**Publisher.** A separate branch next to the alpha one (see the ghost section): C3, Cz, C4, Pz (`--att-channels`; away from the eyes and forehead; OSCAR-cleaned like everything from the source) -> `Bandpass` 0.5-50 Hz -> `Bandstop` at mains -> `FFT` (1 s window, 75% overlap) -> `BandPower` theta 4-8, alpha 8-12, beta low 13-16, beta mid 16-20, beta high 20-30, gamma 30-45 Hz -> `LSLSender` `NightDriveBands`: `(theta, alpha, beta_low, beta_mid, beta_high, gamma)` per channel, about 4 updates/s (24 channels). The index adds up all three beta bands (low + mid + high) and gamma.

**Attention value** (`attention/focus_index.py`, plain, no logarithm): `attention = (beta + gamma) / alpha` on band powers summed over the channels, where beta = beta low + mid + high (13-30 Hz); theta is not used. Beta / gamma tend to rise when alert, alpha when relaxed or drowsy. Smoothed with a 2 s median (so it reacts within a second or two, and a short blink / jaw burst does not move a median). The baseline is the median of that over the first ~23 s of play (3 s settle + 20 s); afterwards it keeps following the last 5 minutes, so it means "how this person plays normally". `level = smoothed / baseline`: 1.0 = normal, 1.4 = 40% above normal (`AttentionState.level`).

**Focus to pass** (`nightdrive/focus_pass.py`, `FocusPassConfig`, pure `FocusMeter`, glue `FocusPass`, tested headless):
- For the first `delay_s` (2 s) of a quick-time event nothing counts and no bars show (only the "OR FOCUS" hint), so the player can settle, like the ghost's relax phase; counting then starts from zero. After that, the *average* level over the last `avg_s` (1 s) is compared with `pass_level` (currently 1.0, set in `FocusPassConfig`). While the average is at or above it, progress moves forward; while it is below, progress just stands still (it is not reset; set `drain` above 0 to make slips lose progress). After `hold_s` (currently 3 s) of progress in total, the event passes (`EventDirector.pass_by_focus()`); `history` records `"input": "focus"` (or `"key"`).
- Focusing takes longer than a key press, so when focus can be used (the attention source is calibrated and has a fresh signal) the event window is `delay_s + qte_window_s` (2 s settle time + 5 s to focus) instead of the normal `QTE_WINDOW` (`EventDirector.qte_window`; with the headlights off or flickering the window is shortened in the same proportion as main's `QTE_WINDOW_DARK / QTE_WINDOW`). Otherwise nothing changes: letters only, normal window. `--attention off` never changes anything.
- On screen, under the letter prompt: "OR FOCUS <average level> / <pass_level>" and a cyan progress bar (before `delay_s` has passed: only "OR FOCUS", no numbers and no bar). In the no-BCI mode (below) the key still works and a wrong key still fails at once.
- Frozen while a ghost is on screen (the source ignores data then, since closed eyes distort the EEG).
- **Development mock, no headset** (`tools/mock_eeg_streams.py`): publishes fake `NightDriveAlpha` / `NightDriveBands` streams in the real format, so the whole BCI path (calibration screen, focus pass, ghost) can be tried without the Unicorn: `python tools/mock_eeg_streams.py` in one terminal, then `python -m nightdrive --eyes bci --attention bci` in another. Keys in the mock's window: `c` eyes closed, `f` focused, `d` drowsy, `n` calm, `q` quit. The game never refers to the mock (a test guards this), and the mock refuses to start if real streams already exist, so the real game is just: start `tools/gpype_alpha_stream.py` instead of the mock. Its data are checked against the game's own parsing in `tests/test_mock_streams.py`.
- **Calibration before the first game** (`nightdrive/attention_calibration.py`, `AttentionCalibrationScene`, routed by `scenes.start_drive`): after START the screen "CALIBRATION" runs the baseline recording (about 25 s: sit still, eyes open, look at the screen; progress bar; "WAITING FOR THE HEADSET..." until the stream is seen, and a "NO HEADSET SIGNAL" warning after 8 s). When the baseline exists it shows "READY!" for a moment and starts the drive, so attention works from the first second of play. It only appears while the source `needs_calibration and not calibrated` (the headset); with `--attention off` / `keyboard` / `random` START goes straight into the game, and once calibrated later starts and game-over retries skip it. ENTER = play anyway (the baseline is then recorded during the drive and events wait for it), ESC = back to the menu. The recording starts when the screen opens, so nothing buffered earlier is used. Sources expose `needs_calibration`, `calibrated`, and (the headset) `calibration_progress` / `waiting_for_stream`.
- **The letter keys are the no-BCI mode** (`App.qte_keys`, true only with `--attention off`, the default). With any attention source on (`bci`, or the `keyboard` / `random` simulations of it) the letter keys do nothing (not even a wrong key fails the event) and the letter is not drawn: the prompt box says "FOCUS" instead, with the countdown bar and the focus meter, and the label reads "FOCUS" instead of "OR FOCUS". The key code (`EventDirector.press`, `Qte`, the letter prompt) is intact and used by the no-BCI mode. Two safeguards keep the BCI mode from being unwinnable: `DriveScene.on_distracted` starts no event until focus is ready (calibrated, fresh signal), and if the signal is lost mid-event `DriveScene.keys_active` turns the letters back on as a fallback for that event.

**Code map.** `attention/base.py` (`AttentionState`, `AttentionSource` protocol), `focus_index.py` (pure estimator), `bci_source.py` (`BciAttention`), `sim_sources.py` (`NullAttention`, `RandomAttention`, `KeyboardAttention`), `factory.py`; `lsl/reader.py` (generic background `StreamReader`; `AlphaReader` and `BandReader` are thin wrappers); `focus_pass.py`. Hooks into existing code: `DriveScene` (`self.focus`, sets `director.qte_window`, calls `director.pass_by_focus()`, draws the meter), `EventDirector` (`qte_window`, `pass_by_focus`, `input` in history), `Qte` (`succeed_by_focus`, `via`), `App` (`--attention`, `--no-attention-log`). Tests: `tests/test_attention.py`.

**Known gaps.** The index is a noisy proxy and not validated against any ground truth for "attention". Muscle activity (clenching the jaw or frowning, which is also what "focusing hard" tends to look like) raises high beta and gamma, so a player can pass by tensing up; there is no artifact rejection. Broadband artifacts (movement, electrode pops) also push the ratio up and can give free passes. In recorded real data the raw value swung by more than +-100% and the smoothed level by tens of percent, so `pass_level` and `hold_s` are untuned guesses: check the `[attention]` / `[focus]` console log and tune. For about the first minute after the publisher starts the filters are still settling (band power in the millions), so start the game about a minute after the publisher; calibration done on that transient is not representative. Channel indices are nominal, not read from stream labels.

## Implemented: eye gaze (webcam / mouse), optional

Gaze tracking drives the *distraction* path, which is what the random timer stood in for. Off by default; enable with `--gaze webcam|mouse` or the **EYE TRACKING** menu entry (then **CALIBRATE EYES**, a full-screen dot calibration saved to `data/gaze_calibration.json`). Usage, camera/phone options (scrcpy, IP cameras, several cameras), the L2CS-Net / MediaPipe models and the geometric model are documented in `README.md` ("Eye tracking").

Code: `nightdrive/gaze/` (`tracker.py` `GazeTracker` + `GazeMonitor`, `webcam_source.py`, `mouse_source.py`, `l2cs.py`, `calibration.py`, `geometry.py`, `features.py`, `session.py`, `download.py`, `base.py`), `nightdrive/calibration_scene.py` (a scene that draws straight to the window: `draws_window = True`, handled in `App.run`), tests in `tests/test_gaze.py`. Gaze is stored in desktop coordinates; `App.gaze_canvas_point()` maps it onto the game canvas. Heavy dependencies (`mediapipe`, `opencv-python`, `torch`) are only needed when gaze is used.

**How it fits with the rest (merge of the eye-gaze branch with main).** In the drive scene, when the gaze tracker is `ready`, `GazeMonitor` (looking outside `GAZE_ROAD_BOX` for `GAZE_AWAY_TIME`, then `GAZE_COOLDOWN`) triggers `on_distracted()` *instead of* the random timer; without gaze the timer is used. A running ghost challenge blocks both. Keys: **`G` = spawn a ghost** (main's debug key), **`Tab` = show/hide the gaze marker** (the branch originally used G; every letter is a QTE answer, so non-letters are preferred for UI). The menu has 3 entries (4 with a calibratable source) and was re-spaced so it does not collide with the credit lines. Tests: `tests/test_integration.py` (gaze section).

## Implemented: roadside monster and hitchhikers

**The monster is off while the headlight features are off** (`settings.HEADLIGHTS_ENABLED = False`, see the headlight section): it only makes sense with switchable lights.

**Hitchhikers are switched off for now** (`settings.HITCHHIKERS_ENABLED = False`): nothing spawns them and `H`/`I` do nothing, but the code, art, sounds and tests are intact (`start_hitchhiker()` still works), so turning the flag on brings them back. Monsters are unaffected.

Two encounters that stand beside the road (`nightdrive/roadside.py`, pure logic in `RoadsideDirector`; art in `creature_art.py`; HUD in `DriveScene._draw_roadside_hud`; tunables are the `ROADSIDE_*`, `MONSTER_*`, `HITCH_*` block in `settings.py`). One at a time, none during a QTE event or the ghost, and no QTE event or ghost during one (`DriveScene._scare_running()`); spawn timers pause while something else runs.

- **Monster.** Appears ~21000 units ahead with a growl, a thin dark figure with red glowing eyes. While you are within its sight (15000 ahead .. 3000 past) its suspicion rises in proportion to `headlights.light` (full light fills it in `MONSTER_NOTICE_TIME` = 1.3 s) and drains with the lights off; below ~0.57 light it only drains, so a dim flicker is not enough. It creeps towards the road as suspicion grows, a tension drone rises, and, **only for the first monster of the game**, a HUD warning + suspicion bar ("MONSTER! LIGHTS OFF!" / "STAY DARK..."). Later monsters have no text and no bar: just a monster by the road, and passing it with the lights on loses. Full suspicion: it lunges (0.35 s), then jump scare + game over ("THE MONSTER SAW YOU"). Drive past unseen: `MONSTER_BONUS` points. With the lights off the road and creature vanish into darkness except the glowing eyes; the QTE window is also shorter, see the headlights rules above.
- **Hitchhikers.** Stand on the right shoulder with a thumb out. **ENTER** (prompted on screen only for the first hitchhiker of the game, "HITCHHIKER AHEAD" then "ENTER - PICK UP") picks one up while they are within `HITCH_PICKUP_RANGE` (~1.5 s before you pass); the car slows, door sounds play, and 1.3 s later a real passenger gives `HITCH_BONUS` points. `HITCH_IMPOSTOR_CHANCE` (35%) of them are **impostors: picking one up ends the run**. Skipping anyone costs nothing. **The tell:** an impostor is the same sprite as a real hitchhiker except two pale eye pixels and a faint **yellow-green glow at the head** (`Sprite.glow_scale/glow_floor` make it readable from afar; it stays visible with the lights off, which is how darkness helps). No other creature uses that glow colour (the monster's is red). Do not make the tell any more obvious without asking: it is meant to be spotted.
- **Tutorial hints are one-time.** Each kind (monster, hitchhiker) shows its on-screen hints once per app session: `App.roadside_hints` is a set shared by every run, so a retry after game over does not repeat them. `settings.ROADSIDE_HINTS_ONLY_FIRST = False` shows them every time (handy for demos). The result messages ("IT DIDN'T SEE YOU", "+100 THANKS FOR THE RIDE") are feedback, not warnings, and always show. Warnings are never needed to survive: the sounds (growl, rising drone) and the monster creeping closer still tell the story.
- **Score.** Both feed `world.score.add(points, reason)` (see the score notes).
- **Death scenes.** `MONSTER_DEATH` and `IMPOSTOR_DEATH` (`EventType`s in `roadside.py`) reuse `GameOverScene` through the `"monster"` / `"impostor"` jump-scare images and the `scare_monster` / `scare_impostor` composites.
- **Debug keys:** `M` monster, `H` hitchhiker (random), `I` impostor. Tests: `tests/test_roadside.py` (rules with a stand-in world) and the roadside section of `tests/test_integration.py`.

## Implemented: the headlight button (click or SSVEP)

**All headlight features are switched off for now** (`settings.HEADLIGHTS_ENABLED = False`): the lights stay on, there is no dashboard button or lamp, no flicker, no light switch (so `--lights ssvep` is ignored with a console note), the roadside monster does not spawn (it needs the lights: it notices full lights and loses you when they are off) and the `M` debug key does nothing. The code and its tests are intact: set the flag to `True` to bring everything back. The tests run with it on (`tests/conftest.py`); `tests/test_headlights_off.py` covers the shipped default. The shorter quick-time window in the dark (`QTE_WINDOW_DARK`) stays in the code but cannot trigger while the lights are always on.

The headlights are operated by a big **button on the dashboard** (`art.LIGHT_BUTTON`, `art.draw_light_button`), not by a key. **SPACE does nothing while driving** (it is only "select" in the menus and "retry" on game over; in keyboard eyes mode it is the ghost's "eyes closed"). The button **flickers** at `HEADLIGHT_BUTTON_HZ` (15, a 50% duty square wave from `light_switch.stimulus_lit`, driven by the wall clock `World.clock`, only while driving; steady in the menu): that flicker is the visual stimulus a future SSVEP BCI will look for. Colours: lit half-cycle blue-white = lights on, orange = lights off, black = dark half-cycle; a white border on hover.

**The abstraction (`nightdrive/light_switch.py`).** `LightSwitch` has `stimulus_hz`, `hover`, `start()`, `stop()`, `handle_event(event) -> bool` (offered every pygame event) and `update(dt) -> bool` (once per frame); returning True toggles the headlights (`DriveScene.toggle_lights`: the toggle plus the switch sound). `ClickLightSwitch` is the only implementation: a left click inside the button (a few pixels forgiving; mapped from window to canvas by `App.window_to_canvas`). `SsvepLightSwitch` (below) is the BCI one. `App(..., lights="click"|"ssvep")` / `--lights click|ssvep` picks it via `make_light_switch`.

**SSVEP switch (`--lights ssvep`).** Look at the flickering button and the lights toggle; the mouse still works as a fallback.

```
python tools/gpype_eeg_stream.py              # terminal 1: Unicorn -> g.Pype -> LSL stream "NightDriveEEG" (raw occipital EEG)
python tools/gpype_eeg_stream.py --simulate   # same, no headset: a constant 15 Hz tone (always "attending")
python tools/ssvep_sim_stream.py              # no headset, and YOU decide: press Enter to "look at the button" / look away
python tools/ssvep_sim_stream.py --auto 8:20  # attend 8 s, look away 20 s, repeat (hands-free demo)
python -m nightdrive --lights ssvep           # terminal 2: the game (add --no-ssvep-log to silence the console log)
```

*Data flow.* `tools/gpype_eeg_stream.py` (own process, like the alpha tool): `HybridBlack` -> `Router` (channels 5,6,7 = PO7, Oz, PO8, nominal layout; `--channels` overrides) -> `Bandpass` 3-40 Hz -> `Bandstop` at mains -> `LSLSender`: 3 channels, 250 Hz, type EEG (checked: the stream reads back correctly with pylsl and a simulated 15 Hz tone measures +14 dB at 15 Hz and about -2 to -10 dB elsewhere). In the game: `lsl/eeg_reader.py` (daemon thread, ring buffer, `window(seconds)` -> channels x samples) -> `SsvepLightSwitch` measures the last `window_s` (2 s) every `step_s` (0.25 s) with `ssvep_score_db` -> `SsvepDetector`.

*The measure.* Hann-windowed FFT; signal = mean power within +-0.5 Hz of f and 2f, noise = mean power of the neighbouring bands (1.5-4.5 Hz away); score = 10 log10(sum signal / sum noise) over channels and harmonics. Being a ratio it ignores amplifier gain and electrode contact; strong 10 Hz alpha does not fool a 15 Hz detector. On synthetic EEG at 15 Hz: about -1.7 dB not attending vs +4.8 dB attending; 20 Hz separates even better; 6-7.5 Hz is weaker (1/f noise and alpha sit next to it), so prefer 15 Hz or higher.

*The decision (`SsvepDetector`).* Calibration: the first `calibration_s` (15 s) of **driving** after the stream is seen, with the button flickering and the player looking at the road (a baseline taken in the menu, where the button is steady, would be too optimistic). Threshold = baseline median + max(3 x robust spread, 3 dB), never below 3 dB nor above 12 dB (so a baseline polluted by staring cannot lock the switch). Then: average the last 3 scores, fire when above the threshold for `hold_s` (0.5 s), then disarm: to fire again the score must drop below the re-arm level (halfway between baseline and threshold) and `cooldown_s` (2 s) must pass. **One look = one toggle; staring never flip-flops the lights.** If the stream stalls for 1.5 s the hold resets. If the player leaves the drive scene (menu, game over) for more than a second, calibration restarts and any look in progress is dropped. The HUD shows `SSVEP: WAITING FOR EEG STREAM` / `CALIBRATING n%  LOOK AT THE ROAD` / `SIGNAL LOST` at the top left until it is ready. All tunables are in `SsvepConfig` (`attention/ssvep.py`), deliberately not in `settings.py`, like the eyes-closed ones.

*Measured end to end* (real game process + `ssvep_sim_stream.py --auto 8:20` over LSL, default config): calibration 15 s -> threshold 3.0 dB; one detection about 1-2 s after the simulated look began; no re-trigger during the 8 s stare; re-armed on looking away.

*Known gaps, not done yet.* Tested only on simulated EEG and through g.Pype's `Generator`: **never on the Unicorn**, so the thresholds (`min_threshold_db` 3, `hold_s`, window length) will need tuning on real signals (watch the `[ssvep]` console log). Channel indices 5,6,7 are the nominal layout and are not read from stream labels. No artifact rejection. No LSL markers at the stimulus transitions (the PSD method does not need phase, but you will want them for offline analysis). The stimulus is drawn at the game's frame rate: at 60 FPS 15 Hz is exactly 2 frames lit, 2 dark (only 30, 15, 10, 7.5 and 6 Hz are exact; 20 Hz is not); check the monitor really runs at 60 Hz and that frames are not dropped (a dropped frame distorts one cycle). Keep the frequency out of 8-12 Hz (alpha: swamps the measure and the ghost detection uses it). Tests: `tests/test_ssvep.py` (measure, rules, a real-LSL reader round trip, the switch with a stand-in reader, the drive scene, and an end-to-end run over LSL with the simulator).

## Implemented: the SSVEP demo (several flickering buttons)

```
python -m nightdrive.ssvep_demo                  # the headset: reads the LSL stream "NightDriveEEG" (run tools/gpype_eeg_stream.py first)
python -m nightdrive.ssvep_demo --source sim     # no headset: hover the mouse over a button (or press 1-4, 0 = away) to "look" at it
python tools/ssvep_sim_stream.py --freqs 6 7.5 13 17 [--auto 8:6]   # no headset, over LSL (even from another computer): type 1-4 + Enter to look at a button
python -m nightdrive.ssvep_demo --freqs 6 9 15 --wave square --calibration 15     # other frequencies / waveform / calibration length
```

A window with N big buttons (default 6, 7.5, 13 and 17 Hz) each flickering at its own frequency, a fixation cross, and the answer in big letters ("LOOKING AT: BUTTON 3 (13 Hz)" or "NOTHING"), also printed to the console on every change. Under each button: its live score in dB with a bar and a tick for its threshold; the selected button gets a green outline. **R** recalibrates, **ESC** quits. The footer shows FPS and a dropped-frame counter, because a stuttering flicker ruins the stimulus.

**How it decides** (`SsvepSelector` in `attention/ssvep.py`, driven by `DemoModel` in `ssvep_demo.py`). It first calibrates for `--calibration` seconds (10) while you look at the cross, not the buttons, recording each button's score. **Each button gets its own threshold from its own baseline** (median + max(3 x robust spread, 3 dB), no absolute floor): low frequencies sit on stronger background EEG, so raw scores are not comparable across buttons (on synthetic EEG, 6 Hz idles near -6 dB and 17 Hz near 0 dB). Then every 0.25 s each button's frequency is measured over the last 2 s (the same `ssvep_score_db` as the headlight switch); a button is a candidate while its smoothed score is above its threshold; the candidate with the biggest lead over its threshold wins if it beats the runner-up by 1 dB (otherwise ambiguous: nobody); a winner that holds for 0.5 s becomes the selection and stays until another one holds or nobody stands out for 0.75 s. Losing the stream clears the selection.

**Choosing frequencies.** Keep them out of 8-12 Hz (alpha) and make sure no button's 2nd harmonic equals another button's frequency (7.5 Hz and 15 Hz clash); the defaults satisfy both and `tests/test_ssvep_demo.py` checks it. The window draws a **sampled sine** by default (`--wave sine`, `stimulus_level` in `light_switch.py`): accurate for any frequency on a 60 Hz screen. `--wave square` is on/off like the headlight button, which is only a clean 50% duty cycle for 30, 15, 10, 7.5 and 6 Hz at 60 FPS (60/2k): **20 Hz is not** (1.5 frames per half-cycle, lit 2 frames of 3). Targets share a channel set and the measure of one button uses the neighbouring bands as noise, which includes the other buttons' peaks: that helps separate them.

**What was measured** (synthetic EEG, so optimistic): four buttons at 6 uV simulated response, 100% of the time the right button and never a wrong one; at 4 uV, 92% with the misses being only "nothing selected" on the weakest (6 Hz); over real LSL with `ssvep_sim_stream.py`: the right button reported about 1.5-1.7 s after the look began and released about 2.7 s after it ended. **The first calibration is the fragile moment**: if the player looks at a button during it, that button's baseline is polluted (its threshold rose to 9.2 dB in one run) and it becomes hard to select until `R`. Never tested on the Unicorn.

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
- Composite entries are `(sample key, start second)` or `(sample key, start second, gain)`; `samples.TRIMS` crops a sample on load.
- Samples listed in `samples.LOOPS` get their tail crossfaded into their head on load, so loops have no seam. One-shots can be panned: `sfx.play(name, pan=-1..1)`; `sfx.play_random([...])` picks one of several variants.
- To use a new sound: add it to `tools/import_audio.py` (key -> file in the pack), add the key and its target loudness to `nightdrive/samples.py`, then run `python tools/import_audio.py`. `tests/test_assets.py` fails if the code, the manifest and the folder disagree (including unused files).
- Licenses: Lonely Nightmare is CC BY 4.0 (credit required); Darkworld Audio and FilmCow allow use in games without attribution (FilmCow: no resale, no government/law-enforcement/hate-group projects) (license copied to `assets/audio/licenses/`, tracked); Horror SFX Free shipped without a license file (credit given anyway, terms unverified). The Ririsaurus packs (creature vocals) allow use but say **do not redistribute**: satisfied as long as the audio stays out of git (it does: see above).

## Status

Done: menu, endless pseudo-3D night drive, events + random-letter QTE (deer, chicken, Trump, yeti, scooter kid on a crosswalk, truck at a crossroads, deep one). Debug keys in the drive scene: `E` random event, `1`-`7` a specific event (order of `CATALOGUE`), `G` ghost, `Tab` gaze marker, `M` monster, `H` hitchhiker, `I` impostor. Quiet shuffled music (Lonely Nightmare, CC BY 4.0, Crow Shade: keep the in-game and README credit), ducks during a QTE, cuts to silence on the jump scare, There is deliberately **no player-facing settings or mute** (the menu only has START, the eye-tracking entries and QUIT); `F11` still toggles fullscreen but is not advertised. Recorded SFX (Horror SFX Free by YourPalRob, FilmCow Royalty Free SFX Library, Darkworld Audio Survival Effects, Ririsaurus creature packs; credits in the menu and README) are layered under the synth scares (crash, thud, glass, the driver's cry) and used for creature-appear sounds, the headlight switch (dashboard button, 3 variants), flicker buzz loop, panic breathing during a QTE, a gasp when a creature appears, an exhale when saved, a frog-ambience loop and rare distant one-shots (`AMBIENT_ONESHOTS` in settings; they can distract, so switch off for strict experiments). **Every sound is a recording; nothing is synthesised** (the numpy synthesiser and the `alert`/`click` fallbacks were removed). Stand-ins, because the packs have no real thing: truck horn = `Robotic_bass` (a low buzzy blast); chicken = two dinosaur shrieks plus a falling slide whistle; Trump "you're fired" = an angry phone slam plus a sad trombone made of falling slide whistles; saved = a soft ding (no tyre squeal; the scooter scare still has chair-squeak squeals); headlight zap = a CRT-TV switch-off; QTE riser = the last 1.5 s of the "Slow Stinger" swell (`TRIMS` in `samples.py`); engine = FilmCow `ambience - car sedan inside`. Swap any of them by changing one line in `tools/import_audio.py`. `tests/test_sfx.py::test_nothing_is_synthesised_any_more` guards this. `SFX_VOLUME` scales everything and the scares are loud on purpose. Headlights: a flickering dashboard button toggles them (see the headlight button section; letters are all QTE keys, so don't bind letters); they flicker every 25-50 s until switched off and on again; off = near-darkness; dashboard lamp + hint; if the lights are off or flickering when an event fires, the QTE window is `QTE_WINDOW_DARK` (1.0 s) instead of `QTE_WINDOW` (2.0 s). Score: an amber LCD on the right of the dashboard instrument panel (`art.draw_score`, 6 digits) and on the game-over screen. It rises `SCORE_PER_SECOND` (10) points per second of driving and nothing else affects it yet. **To make something score, call `world.score.add(points, reason)`** (negative for penalties; every call is kept in `score.history` for session logs), e.g. in the director when a QTE is saved, or when an objective is completed. `World.score` is reset when the menu or a new drive starts and advanced by `DriveScene.update`. Failing a QTE ends the run: full-screen jump scare (close-up per creature), then a game-over screen with retry. Events are currently triggered by a random timer or the `E` key via `DriveScene.on_distracted()`, a placeholder for the attention input. Next: `AttentionSource` + `DistractionDetector` (PLAN.md Phase 3), then session logging. BCI exists only as the experimental eyes-closed ghost scare (see "Implemented: g.Pype BCI + eyes-closed ghost scare" above); the attention-driven events are still not wired to EEG.
