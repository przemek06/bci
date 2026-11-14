"""Webcam gaze source: OpenCV capture + MediaPipe FaceLandmarker, one background thread per camera.

A camera can be a local index (0 = built-in) or a stream URL, so phones (Continuity
Camera, DroidCam, IP Webcam, ...) can be used. With several cameras the per-camera
feature vectors are concatenated and the calibration regression learns how to weigh
them; a camera placed below or above the screen sees vertical eye motion much better.
"""

import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

from .. import settings as S
from .base import GazeFeatures
from .download import download
from .features import N_FEATURES, gaze_features

_model_lock = threading.Lock()


def parse_camera(value) -> int | str:
    s = str(value)
    return int(s) if s.isdigit() else s


def ensure_model(path: Path = Path(S.GAZE_MODEL_FILE)) -> Path:
    with _model_lock:
        if not path.exists():
            download(S.GAZE_MODEL_URL, path)
    return path


def open_scrcpy(spec: str):
    """Start scrcpy for `scrcpy[:front|back[:serial]]` and return (fifo_path, process, tmpdir).

    scrcpy records the phone camera (over USB) as MKV into a FIFO that OpenCV reads.
    """
    if not shutil.which("scrcpy"):
        raise RuntimeError("scrcpy not found (brew install scrcpy)")
    _, _, rest = spec.partition(":")
    facing, _, serial = rest.partition(":")
    tmp = tempfile.mkdtemp(prefix="nightdrive-")
    fifo = os.path.join(tmp, "cam.mkv")
    os.mkfifo(fifo)
    cmd = ["scrcpy", "--video-source=camera", f"--camera-facing={facing or 'front'}"]
    cmd += [f"--camera-size={S.GAZE_SCRCPY_SIZE}", f"--camera-fps={S.GAZE_SCRCPY_FPS}"]
    cmd += ["--no-playback", "--no-audio", f"--record={fifo}", "--record-format=mkv"]
    if serial:
        cmd.append(f"--serial={serial}")
    log = open(os.path.join(tmp, "scrcpy.log"), "w")  # noqa: SIM115 - owned by the child process
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
    log.close()
    return fifo, proc, tmp


class _CameraWorker:
    def __init__(self, camera: int | str, use_l2cs: bool = False):
        self.camera = camera
        self.use_l2cs = use_l2cs
        self.lock = threading.Lock()
        self.latest: GazeFeatures | None = None
        self.status = "starting"
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run, daemon=True, name=f"gaze-{camera}"
        )
        self._proc: subprocess.Popen | None = None
        self._tmp: str | None = None
        self._frame = None
        self._frame_id = 0

    def close(self) -> None:
        """Stop an external helper (scrcpy); this also unblocks reads on its FIFO."""
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        if self._tmp:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None

    def _watch_scrcpy(self, fifo: str) -> None:
        """If scrcpy dies before streaming, say why and unblock the reader waiting on the FIFO."""
        proc, tmp = self._proc, self._tmp
        proc.wait()
        if self.latest is not None or self.stop_event.is_set():
            return
        try:
            lines = Path(tmp, "scrcpy.log").read_text().splitlines()
        except OSError:
            lines = []
        errors = [ln for ln in lines if ln.startswith("ERROR")]
        reason = (errors or lines or ["no output"])[0 if errors else -1]
        self.status = f"scrcpy failed: {reason.removeprefix('ERROR: ')}"
        if len(errors) > 1 and "Multiple" in errors[0]:
            self.status = (
                "several ADB devices: use scrcpy:front:SERIAL (see `adb devices`)"
            )
        for _ in range(40):  # open+close the write end so the blocked open() returns
            try:
                os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
                return
            except OSError:
                time.sleep(0.05)

    def _grab(self, cap) -> None:
        """Keep only the newest frame so a slow detector never builds up latency."""
        while not self.stop_event.is_set():
            ok, frame = cap.read()
            if not ok:
                if isinstance(self.camera, str) and self.camera.startswith("scrcpy"):
                    break  # scrcpy ended
                self.status = "camera read failed"
                time.sleep(0.1)
                continue
            with self.lock:
                self._frame = frame
                self._frame_id += 1

    def _run(self) -> None:
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks.python import BaseOptions, vision

            self.status = "downloading model"
            model = ensure_model()
            if self.use_l2cs:
                from . import l2cs

                l2cs.ensure_weights()
                self.status = "loading L2CS"
                l2cs._get()
            landmarker = vision.FaceLandmarker.create_from_options(
                vision.FaceLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=str(model)),
                    running_mode=vision.RunningMode.IMAGE,
                    num_faces=1,
                    output_face_blendshapes=True,
                    output_facial_transformation_matrixes=True,
                )
            )
            source = self.camera
            if isinstance(source, str) and source.startswith("scrcpy"):
                self.status = "starting scrcpy"
                source, self._proc, self._tmp = open_scrcpy(source)
                threading.Thread(
                    target=self._watch_scrcpy, args=(source,), daemon=True
                ).start()
            cap = cv2.VideoCapture(source)
            if not cap.isOpened():
                if not self.status.startswith(("scrcpy failed", "several")):
                    self.status = "camera unavailable (check camera permission / URL / USB debugging)"
                self.close()
                return
        except Exception as e:  # noqa: BLE001 - missing deps/scrcpy, no network for the model, ...
            self.status = f"error: {e}"
            return
        grab = threading.Thread(target=self._grab, args=(cap,), daemon=True)
        grab.start()
        seen = 0
        try:
            while not self.stop_event.is_set():
                with self.lock:
                    frame, fid = self._frame, self._frame_id
                if frame is None or fid == seen:
                    time.sleep(0.005)
                    continue
                seen = fid
                h, w = frame.shape[:2]
                rgb = np.ascontiguousarray(frame[:, :, ::-1])
                result = landmarker.detect(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                )
                if not result.face_landmarks:
                    self.status = "no face"
                    continue
                pts = np.array([(p.x, p.y) for p in result.face_landmarks[0]])
                blend = {c.category_name: c.score for c in result.face_blendshapes[0]}
                matrix = (
                    result.facial_transformation_matrixes[0]
                    if len(result.facial_transformation_matrixes)
                    else None
                )
                net = None
                if self.use_l2cs:
                    px = pts * np.array([w, h])
                    net = l2cs.predict(rgb, px)
                values, quality = gaze_features(pts, w, h, blend, matrix, net)
                self.status = "tracking" if quality > 0 else "blink"
                with self.lock:
                    self.latest = GazeFeatures(values, quality, time.monotonic())
        finally:
            self.stop_event.set()
            self.close()  # ends scrcpy, which unblocks a read on its FIFO
            grab.join(timeout=3)
            if (
                not grab.is_alive()
            ):  # releasing while a read is in flight crashes OpenCV
                cap.release()
            landmarker.close()


class WebcamGazeSource:
    needs_calibration = True
    block = N_FEATURES

    def __init__(self, cameras: list | int | str = 0, use_l2cs: bool = False):
        self.use_l2cs = use_l2cs
        if not isinstance(cameras, (list, tuple)):
            cameras = [cameras]
        self.cameras = list(cameras)
        self._workers: list[_CameraWorker] = []

    def start(self) -> None:
        if self._workers:
            return
        self._workers = [_CameraWorker(c, self.use_l2cs) for c in self.cameras]
        for w in self._workers:
            w.thread.start()

    def stop(self) -> None:
        for w in self._workers:
            w.stop_event.set()
        for w in self._workers:
            w.close()
        for w in self._workers:
            w.thread.join(timeout=2)
        self._workers = []

    def latest(self) -> GazeFeatures | None:
        """Newest sample of every camera combined; None until all cameras have a fresh one."""
        parts = []
        for w in self._workers:
            with w.lock:
                parts.append(w.latest)
        if not parts or any(p is None for p in parts):
            return None
        newest = max(p.t for p in parts)
        if any(newest - p.t > S.GAZE_STALE for p in parts):
            return None  # one camera lost the face
        return GazeFeatures(
            np.concatenate([p.values for p in parts]),
            min(p.quality for p in parts),
            newest,
            newest - min(p.t for p in parts),
        )

    def status(self) -> str:
        if not self._workers:
            return "stopped"
        if len(self._workers) == 1:
            return self._workers[0].status
        return " | ".join(f"cam{i}: {w.status}" for i, w in enumerate(self._workers))
