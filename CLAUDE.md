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
  qte.py                     # quick-time event logic (random letter, timing, outcome), no drawing
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

In the drive scene the debug key **G** spawns a ghost immediately (E still spawns a road event).

**Data flow.** `tools/gpype_alpha_stream.py` (own process, because g.Pype's app loop wants the main thread, which pygame also needs): `HybridBlack(enable_oscar=True)` (g.Pype's OSCAR artifact removal on the whole stream, so both branches get cleaned data) -> `Router` with two separate branches, each with its own filters, FFT and band power. The ghost (alpha) branch, with the same filters as the original: occipital channels (EEG channels 5,6,7 = PO7, Oz, PO8, nominal layout; `--channels` overrides) -> `Bandpass` 1-40 Hz -> `Bandstop` at mains (`--mains`, 50 Hz default) -> `FFT` (1 s window, 75% overlap, about 4 updates/s) -> `BandPower` alpha 8-12 Hz and broadband 2-30 Hz -> `LSLSender` `NightDriveAlpha`, carrying `(alpha, broad)` per channel. The attention branch is described in its own section below. In the game: `lsl/alpha_reader.py` (background thread, never blocks the loop) -> relative alpha = sum(alpha) / sum(broad) -> `attention/eyes_closed.py` `EyesClosedDetector` -> `attention/eyes_source.py` -> `ghost/`.

**Detector** (pure logic, time passed in, tested headless). Calibrated on eyes-open relative alpha: threshold = median + max(3 x robust spread, 0.10). Then a 1 s moving average, hysteresis (closed above the threshold, open again below a lower release level), a hold timer that forgives dips shorter than `grace_s` (0.5 s), and loss of signal resets the hold. All tunables are in `EyesClosedConfig` (`eyes_closed.py`) and `GhostConfig` (`ghost/encounter.py`), deliberately not in `settings.py`; fold them into `config/default.toml` when that exists.

**Eye sources** (`attention/eyes_source.py`) share one interface and the same detector, so the keyboard path exercises the real logic: `KeyboardEyes` (hold SPACE) and `BciEyes` (auto-calibrates from the first ~17 s of eyes-open data after the stream appears, prints a live `[eyes] raw/avg/thr` log). `App` updates `app.eyes` every frame in every scene.

**Ghost package** (`nightdrive/ghost/`): `encounter.py` (pure state machine: IDLE/ACTIVE/PASSED/DEAD, deadline, pauses and cancels without killing the player if the EEG drops), `visuals.py` (procedural ghost art + overlay), `challenge.py` (`GhostChallenge`, the single object the drive scene talks to). Death reuses `GameOverScene` through the `"ghost"` jump-scare image registered in `app.assets.jumpscares`.

**Merge notes.** Everything is new files except these small hooks: `scenes.py` `DriveScene` (import, `self.ghost`, update, draw, G key, an E-key guard, ESC reset), `app.py` (`--eyes`, `--no-eyes-log`, `app.eyes`, per-frame update, stop on exit), and `requirements.txt` (`gpype[devices,lsl]`, `pylsl`, `scipy`). Tests: `tests/test_eyes_closed.py`, `tests/test_ghost.py`.

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
- While a quick-time event runs, the level must be at or above `pass_level` (1.4) for `hold_s` (1 s) in total. Progress drains 2x faster while the level is below, so a brief slip is forgiven but a long one resets. Then the event passes (`EventDirector.pass_by_focus()`); `history` records `"input": "focus"` (or `"key"`).
- Focusing takes longer than a key press, so when focus can be used (the attention source is calibrated and has a fresh signal) the event window is `qte_window_s` (5 s) instead of 1.5 s (`EventDirector.qte_window`). Otherwise nothing changes: letters only, normal window. `--attention off` never changes anything.
- On screen, under the letter prompt: "OR FOCUS 1.2 / 1.4" and a cyan progress bar. The key still works; a wrong key still fails at once.
- Frozen while a ghost is on screen (the source ignores data then, since closed eyes distort the EEG).

**Code map.** `attention/base.py` (`AttentionState`, `AttentionSource` protocol), `focus_index.py` (pure estimator), `bci_source.py` (`BciAttention`), `sim_sources.py` (`NullAttention`, `RandomAttention`, `KeyboardAttention`), `factory.py`; `lsl/reader.py` (generic background `StreamReader`; `AlphaReader` and `BandReader` are thin wrappers); `focus_pass.py`. Hooks into existing code: `DriveScene` (`self.focus`, sets `director.qte_window`, calls `director.pass_by_focus()`, draws the meter), `EventDirector` (`qte_window`, `pass_by_focus`, `input` in history), `Qte` (`succeed_by_focus`, `via`), `App` (`--attention`, `--no-attention-log`). Tests: `tests/test_attention.py`.

**Known gaps.** The index is a noisy proxy and not validated against any ground truth for "attention". Muscle activity (clenching the jaw or frowning, which is also what "focusing hard" tends to look like) raises high beta and gamma, so a player can pass by tensing up; there is no artifact rejection. Broadband artifacts (movement, electrode pops) also push the ratio up and can give free passes. In recorded real data the raw value swung by more than +-100% and the smoothed level by tens of percent, so `pass_level` and `hold_s` are untuned guesses: check the `[attention]` / `[focus]` console log and tune. For about the first minute after the publisher starts the filters are still settling (band power in the millions), so start the game about a minute after the publisher; calibration done on that transient is not representative. Channel indices are nominal, not read from stream labels.

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

## Status

Done: menu, endless pseudo-3D night drive, events + random-letter QTE (deer, chicken). Failing a QTE ends the run: full-screen jump scare (close-up per creature), then a game-over screen with retry. Events are currently triggered by a random timer or the `E` key via `DriveScene.on_distracted()`, a placeholder for the attention input. Next: `AttentionSource` + `DistractionDetector` (PLAN.md Phase 3), then audio. BCI exists only as the experimental eyes-closed ghost scare (see "Implemented: g.Pype BCI + eyes-closed ghost scare" above); the attention-driven events are still not wired to EEG.
