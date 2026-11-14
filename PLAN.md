# PLAN.md: Night Drive (BCI driving game)

## 1. Vision

A calm, atmospheric, pixel-art night drive. The player does nothing while focused. A car glides down a moonlit road with simple looping music. When the player's attention drifts, the world reacts: something scary or funny jumps onto the road and a quick-time event (QTE) demands a fast keypress. Attention is measured from EEG (g.tec Unicorn Hybrid Black, streamed over LSL from another computer), but the whole game must also run without the headset via a random-based attention simulator.

Later, each session gets an objective based on the P300 response, such as noticing a lost dog by the roadside, with a click-based alternative when no EEG is available.

It is also a research instrument: timed sessions, full logging, and LSL markers for alignment with the EEG recording.

## 2. Decisions so far

| Topic | Decision |
|---|---|
| Language / lib | Python + pygame-ce |
| Focus computation | In the game process, from the raw LSL EEG stream, with a calibration baseline |
| Assets | Procedural placeholders first (generated sprites, synthesized chiptune). Real art and music can replace them later without code changes |
| Sessions | Timed sessions with logging, plus LSL event markers |
| Attention abstraction | `AttentionSource` with `random`, `keyboard` (debug) and `bci` implementations |
| Platform | macOS for development. The BCI laptop and the game computer are different machines on the same network |

### Assumptions (change if wrong)

- **Camera/view (decided):** pseudo-3D, driver's view (first person, OutRun-style): the road is drawn as projected segments with curves and hills, roadside sprites are scaled by distance, the dashboard/hood and steering wheel are overlaid at the bottom. Things "jump out" from the roadside onto the road ahead.
- **Resolution:** internal 320x180, scaled by an integer factor to the window (fullscreen option). 60 FPS.
- **QTE input:** keyboard (e.g. `SPACE` to brake, `LEFT`/`RIGHT` to swerve, or a single prompted key). Keyboard use is only for QTEs, which is consistent with "most of the time no input".
- **Consequence of a failed QTE:** mild (bump, screen shake, slowdown, score penalty). No game over. The game is about being pulled back into focus, not punishment.
- **Session length:** configurable, default 10 minutes, after an optional calibration block.
- **Mains frequency:** 50 Hz notch (Poland/EU), configurable.

## 3. Game design

### 3.1 Scene (always on)
- Pseudo-3D road (segment-based projection, gentle curves and hills), night sky with twinkling stars and moon, distant hill silhouettes with horizontal parallax following curves, roadside trees/posts/streetlamps as distance-scaled sprites, dashed centre line, fog fading to dark with distance.
- Driver's view: dashboard/hood overlay with subtle bob and steering wheel sway, headlight pool brightening the road ahead, a few particles (moths and bugs in the headlight beam).
- Subtle HUD: session time, optional focus meter (debug/experimenter only, hidden in participant mode).
- Music: a simple, mellow loop (procedural chiptune: bass + arpeggio + soft pad). Engine hum and ambient crickets as low-volume layers.

### 3.2 Focus state -> events
- `AttentionSource` yields `focus` 0..1 and `quality`.
- `DistractionDetector`: if smoothed focus stays under `distraction_threshold` for `distraction_hold_s`, with quality above `min_quality` and no event/cooldown active, it fires `distracted`. It re-arms only after focus recovers above `recovery_threshold` (hysteresis) and a minimum cooldown has passed.
- `EventDirector` picks from the catalogue (weighted, avoids repeating the last event, balances scary vs funny).
- Example events:
  - **Scary:** glowing-eyed deer, ghost in the headlights, hand rising from the ground, giant spider dropping from a tree, shadow figure.
  - **Funny:** chicken crossing, cow in sunglasses, dancing skeleton, UFO beam picking up a bush, a tiny car honking.
- Each event: sprite + animation, sound sting, music duck, optional camera shake/flash, then a QTE.

### 3.3 QTE
- Prompt shown with a shrinking timer bar (default window about 1.5 s, configurable per event).
- Types: single key (brake), direction (swerve L/R), mash (a few presses). Start with single key, add others later.
- Outcomes: success (dodge/brake, the funny/scary thing reacts, small reward), failure (bump, slowdown, shake), timeout counts as failure. Outcome logged with the reaction time.
- After resolution the game returns to calm driving and waits for the next distraction.

### 3.4 Objectives (later)
- Per-session objective, e.g. "notice the lost dog": a dog sprite appears at the roadside at an unpredictable time, rarely (oddball). Embedded among non-target stimuli (other roadside objects) so a P300 can be elicited.
- Non-BCI alternative: player clicks the dog. BCI version: P300 classifier over epochs time-locked to stimulus onset marker.
- Both produce the same `ObjectiveResult` so scoring/logging is identical.

## 4. Architecture

See `CLAUDE.md` for the layout and the rules. In short:

```
EEG device -> (other PC) -> LSL -> [lsl reader thread] -> processing -> BciAttentionSource --\
                                                       RandomAttentionSource ----------------+--> DistractionDetector -> EventDirector -> QTE
                                                       KeyboardAttentionSource --------------/                                   |
                                                                                                                                  v
                                                                   MarkerSink (LSL markers + CSV log) <------ scoring / session / objectives
```

Key design points:
- The game depends only on the `AttentionSource` interface. Swapping mode is a CLI flag.
- The random source simulates plausible attention dynamics (alternating focused/distracted episodes with random durations, plus noise), not just coin flips, so the detector and director get realistic input. It is seedable for reproducible tests.
- The keyboard source (hold/toggle a key = distracted) lets a developer trigger any event on demand.
- Network/LSL work is in a background thread. The game loop is never blocked.
- Markers and CSV logs are produced by a single `MarkerSink` fan-out.

## 5. Roadmap

Each phase ends with something runnable and a clear "done when". Phases 0-6 need no hardware at all.

### Phase 0: Project scaffolding
- Package `nightdrive` under `src/`, a single `requirements.txt` (pygame-ce, numpy, pytest, ruff; pylsl and scipy are added in the BCI phases), venv + pip.
- Pin a Python version with working wheels for pygame-ce and pylsl on macOS (check; don't assume the newest).
- `.gitignore` (venv, `data/`, caches), `config/default.toml`, README with setup.
- **Smoke test:** `python -m nightdrive` opens a window; `pytest` and `ruff` run. Verify `import pylsl` finds `liblsl` on macOS.
- **Done when:** a blank 320x180 scaled window opens and closes cleanly; CI-less local checks pass.

### Phase 1: Core loop and rendering
- Fixed-timestep main loop at 60 FPS, injectable clock, scene manager (menu/calibration/drive/summary as scenes), integer-scaled low-res render target, fullscreen toggle, `ESC` handling.
- Config loader with typed dataclasses and CLI overrides (`--source`, `--seed`, `--session-minutes`, `--windowed`).
- **Done when:** a placeholder scene renders crisply at several window sizes with a stable frame rate.

### Phase 2: Night driving scene
- Procedural sprite generation (dashboard/hood, trees, posts, lamps, moon, stars) into cached surfaces behind an asset-by-name API.
- Pseudo-3D road renderer (segments, curves, hills, distance fog), sky and hill parallax, dashboard bob, headlight pool, particles, star twinkle.
- Speed variable in the world state (events will change it).
- **Done when:** a pleasant, looping, endless night drive plays with no input.

### Phase 3: Attention abstraction + simulated sources
- `AttentionSource` protocol and `AttentionState`.
- `RandomAttentionSource` (episode-based, seedable), `KeyboardAttentionSource`.
- Debug overlay: live focus trace, threshold lines, detector state (toggle with a key).
- **Done when:** `--source random` and `--source keyboard` both produce a visible, plausible focus trace. Unit tests cover the sources' ranges and seeding.

### Phase 4: Distraction detector, events and QTE
- `DistractionDetector` with hysteresis, hold time, cooldown, quality gating (pure logic, unit-tested with synthetic focus traces).
- Event catalogue (TOML or Python data), `EventDirector`, event sprites and animations (2 scary + 2 funny to start), the QTE (single key first), outcomes and consequences (speed change, shake, flash).
- **Done when:** in random mode, distraction episodes reliably trigger an event, the QTE works, the game returns to calm driving, and the same flow can be triggered by hand in keyboard mode.

### Phase 5: Audio
- Procedural chiptune loop generator (numpy -> `pygame.mixer.Sound`), engine hum, ambient layer, event stings, QTE success/fail sounds, music ducking during events.
- Volume settings in config, mute key. Audio device missing -> game still runs silently.
- **Done when:** the full loop has sound and no audible clicks at loop points.

### Phase 6: Session flow, scoring, logging
- Session state machine: menu/setup -> (calibration, BCI only) -> timed drive -> summary.
- Scoring: focus time ratio, events triggered, QTE success rate and mean reaction time.
- `MarkerSink` with CSV implementation: `data/sessions/<timestamp>/` containing `events.csv` (timestamped session/event/QTE records), `focus.csv` (focus + quality, downsampled), `config.toml` snapshot, and a seed/metadata file.
- **Done when:** a full 10-minute simulated session runs end to end and the logs reconstruct what happened.

### Phase 7: LSL infrastructure (can use the fake streamer)
- `tools/fake_eeg_stream.py`: publishes an 8-channel, 250 Hz Unicorn-like stream (labels, units, type `EEG`) with controllable alpha/beta/theta content and optional blink and noise artifacts, so the focus pipeline can be tested without a headset. Include a key or slider to switch "focused" or "distracted" profiles.
- `lsl/resolver.py`: find the stream by type/name with a timeout and clear messages, read channel labels from the stream info.
- `lsl/reader.py`: background thread that pulls chunks into a ring buffer with timestamps, handles disconnect/reconnect.
- `LslMarkerSink`: marker outlet (`NightDriveMarkers`), added to the `MarkerSink` fan-out.
- `tools/replay_xdf.py` (or CSV): replay a recorded EEG file as an LSL stream.
- **Done when:** the game on one machine receives the fake stream, markers show up in LabRecorder, and killing/restarting the streamer doesn't crash the game.
- **Network note:** LSL discovery uses multicast. Across Wi-Fi or subnets it may fail. Plan for a `lsl_api.cfg` (`KnownPeers`) and macOS firewall rules. Test early on the real two-machine setup.

### Phase 8: BCI attention source
- `processing.py`: notch + band-pass, sliding window, artifact rejection, band power, per-channel selection by label. All unit-tested on synthetic signals (e.g. a 10 Hz sine produces alpha power and so on).
- `calibration.py` + calibration scene: e.g. 60 s "focus" block (a simple engaging task such as counting or tracking a moving dot) and 60 s "relax / let your mind wander" block. Compute baseline statistics and the mapping to focus 0..1.
- `BciAttentionSource`: reads latest window, computes the index, normalises, smooths, outputs `focus` + `quality` (from artifact rate, signal amplitude, packet loss).
- Offline analysis script: run the pipeline on recorded calibration data and compare candidate indices (beta/(alpha+theta), frontal theta, occipital alpha). Pick the default from data.
- **Done when:** with the fake stream, switching the profile moves `focus` as expected. With the real headset, the calibration gives visibly separable focused vs. relaxed distributions.

### Phase 9: Integration and robustness
- Real two-machine test: Unicorn -> LSL on the BCI laptop -> network -> game computer. Measure end-to-end latency and clock offsets.
- Failure behaviour: stream lost -> quality 0 -> detector pauses, HUD warns the experimenter, auto-reconnect. Bad signal (electrode off) -> same. Provide an experimenter option to fall back to random mode mid-session (logged).
- Thresholds tuned on real data, exposed in config. Document the setup procedure in README (electrode check, stream start, calibration, run).
- **Done when:** a pilot session with a real participant completes with usable logs and no freezes.

### Phase 10: Polish
- Replace placeholder art and audio where wanted (drop-in files), more events (aim for 8-12), more QTE types, screen transitions, title/summary screens, participant mode (hides debug overlays), simple difficulty variants.

### Phase 11: Objectives framework + non-BCI objective
- `Objective` and `ResponseDetector` abstractions, `ObjectiveResult`, stimulus scheduler (rare targets among frequent non-targets, jittered intervals, no overlap with QTEs).
- First objective: lost dog. Click-based detector (`ClickResponseDetector`) implemented first.
- Stimulus onset marker emitted at the actual frame of appearance. Hits/misses/false clicks logged and scored.
- **Done when:** the lost-dog objective is playable in random/keyboard mode with mouse clicks and produces correct logs.

### Phase 12: P300 detection
- Epoching around stimulus-onset markers (using LSL timestamps), baseline correction, channel selection (Pz/Cz/Fz/Oz), averaging across trials and/or LDA single-trial classifier, short training block to fit per participant.
- `P300ResponseDetector` implementing the same interface as the click detector.
- Validate offline first on recorded sessions (target vs. non-target ERPs), then online.
- **Done when:** a clear target-vs-non-target difference is visible in grand averages from real sessions and the detector beats chance on held-out trials.

### Later / ideas
- More objectives (e.g. spot a specific sign, count a certain object).
- Adaptive difficulty from focus history, replay/visualisation of a session with EEG, multiple participants/profiles, packaging as a standalone app.

## 6. Testing strategy

- **Pure logic unit tests:** detector hysteresis, director selection, QTE timing, scoring, config parsing, band-power maths on synthetic signals, markers formatting.
- **Determinism:** every random component takes a seed. A fixed seed reproduces the same session in random mode.
- **Headless smoke tests:** run N seconds of the game with `SDL_VIDEODRIVER=dummy`, scripted attention trace, assert no exceptions and expected event count.
- **Hardware-free BCI testing:** fake EEG streamer + replay of recorded data.
- **Manual checklist** for each phase's "done when" (visuals, audio, feel).

## 7. Risks and open points

| Risk | Mitigation |
|---|---|
| EEG "focus" is a weak/noisy signal, especially with dry electrodes | Per-user calibration, pluggable index, hysteresis, quality gating, offline analysis before trusting it, random mode for control conditions |
| Event triggered by a blink or movement artifact rather than distraction | Artifact rejection and quality gating, require sustained low focus |
| LSL across machines/network (multicast, firewall) | Test the two-machine setup in Phase 7 rather than Phase 9, support `KnownPeers` |
| pygame/pylsl wheels for the newest Python on macOS | Pin the Python version in Phase 0 and check imports first |
| Stimulus timing accuracy for P300 (frame timing, markers) | Mark onset at flip time, log frame times, validate with a photodiode or at least a timing test later |
| Game itself being a visual stimulus confounds alpha-based measures | Keep visuals calm and consistent, compare indices on recorded data |

### Questions to settle later
- Exact QTE key scheme and how many QTE types.
- Participant-facing versus experimenter-facing screens (what is shown to whom, one or two monitors).
- Which recording format the lab prefers for EEG (XDF via LabRecorder is assumed).
- Whether the experiment needs conditions (e.g. BCI-driven vs. yoked random events) and counterbalancing. The random source could replay a previous session's event times for a "yoked" control, which is cheap to support if the logs are good.
