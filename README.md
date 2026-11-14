
## Eye tracking (optional)

Webcam gaze tracking (MediaPipe iris landmarks + a per-user calibration). Looking away from the road for a few seconds triggers a distraction event, replacing the random timer.

```
python -m nightdrive --gaze webcam                 # auto: built-in camera + every USB phone listed by `adb devices` (needs scrcpy)
python -m nightdrive --gaze webcam --gaze-camera 1 # other camera index, e.g. iPhone via Continuity Camera
python -m nightdrive --gaze webcam --gaze-camera http://PHONE_IP:PORT/video   # Android IP-camera app stream
python -m nightdrive --gaze mouse                  # no hardware: the mouse stands in for the gaze
```

Or toggle **EYE TRACKING** in the menu, then run **CALIBRATE EYES** (15 dots, ~30 s). The calibration is saved to `data/gaze_calibration.json`. The first run downloads the face model (~4 MB) to `data/models/`. macOS will ask for camera permission for your terminal/IDE. In game, `G` shows/hides the gaze dot.

**Better vertical tracking with several cameras:** list more than one camera and their features are combined; put a phone below (or above) the screen, since a different viewing angle sees up/down eye movement much better. Every camera must see your face, and you must recalibrate whenever the camera set changes.

```
python -m nightdrive --gaze webcam --gaze-camera 0 http://PHONE_IP:PORT/video
```

Tip: put each camera at eye level or just below the screen, keep it steady, and avoid strong backlight.

**Android phone over USB with scrcpy (FOSS, no app on the phone):**

```
brew install scrcpy android-platform-tools     # enable USB debugging on the phone
python -m nightdrive --gaze webcam --gaze-camera scrcpy:front
python -m nightdrive --gaze webcam --gaze-camera 0 scrcpy:front:SERIAL   # laptop camera + a specific phone (see `adb devices`)
```

`scrcpy[:front|back[:serial]]` starts scrcpy itself and reads its camera feed through a FIFO. Keep the phone screen unlocked on first use. Resolution and fps are `GAZE_SCRCPY_*` in `settings.py`.

**Calibration covers the whole screen.** The calibration scene switches to full screen so the dots span your entire display, then returns to the window. Gaze is stored in desktop coordinates, so the game window can be small and moved or resized afterwards without recalibrating (recalibrate if you move the camera or change monitors; only the main display is supported). The result screen shows the cross-validated expected error for x and y; if y is much worse than x, move the phone closer to the screen's vertical centre line or lower/raise it.

**Camera positions (geometric model).** With L2CS, calibration also fits a 3D model: each camera's position and rotation (and a shared eye offset) are estimated from your head motion and the calibration dots, then every camera's gaze ray from your 3D eye position is intersected with the screen and fused. Set your display size in `GAZE_SCREEN_CM` (`nightdrive/settings.py`); camera 0 is assumed at the top centre of the screen, other cameras can be anywhere. The result screen shows which method (`geometry` or `regression`) had the lower cross-validated error and uses that one.

**Head movement.** Features include the 3D head pose and position (from MediaPipe's facial transformation matrix) per camera. Calibration has two rounds (about 45 s): round 1 head still, round 2 you keep watching each dot while slowly leaning, turning and tilting your head, so the fit learns to compensate. Poses far outside what you showed during calibration are clipped, so move within the range you calibrated.

**Neural gaze model (L2CS-Net).** `--gaze-model auto|l2cs|mediapipe` (default `auto`: L2CS when torch is installed). L2CS-Net (ResNet50 trained on Gaze360) predicts gaze yaw/pitch from the face crop, already compensated for head pose and much better at vertical gaze than iris landmarks; its output is fed, together with head pose and position, into the same calibration regression. It runs on the Apple GPU (MPS) at ~7 ms/frame. The ~96 MB weights are downloaded to `data/models/` on first use and checked against a SHA-256 (they come from a community Hugging Face mirror of the official release). Calibrations are tied to the model and camera set, so changing either needs a new calibration.

Two Android phones over USB (find serials with `adb devices`; the serial is required when several devices are connected):

```
python -m nightdrive --gaze webcam --gaze-camera scrcpy:front:SERIAL_A scrcpy:front:SERIAL_B
```
