"""L2CS-Net (ResNet50, Gaze360 weights) gaze direction from a face crop.

Unlike iris landmarks, a network trained on faces at many head poses returns the gaze
direction already compensated for head pose, and it is much better at vertical gaze.
Needs torch + torchvision and a ~96 MB weights file, downloaded on first use.
"""

import hashlib
import threading
from pathlib import Path

import numpy as np

from .. import settings as S
from .download import download

BINS = 90
_lock = threading.Lock()
_model = None


def ensure_weights(path: Path = Path(S.GAZE_L2CS_FILE)) -> Path:
    if not path.exists():
        download(S.GAZE_L2CS_URL, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != S.GAZE_L2CS_SHA256:
        path.unlink()
        raise RuntimeError("L2CS weights checksum mismatch; file removed, retry")
    return path


def available() -> bool:
    try:
        import torch  # noqa: F401
        import torchvision  # noqa: F401
    except ImportError:
        return False
    return True


def _build():
    import torch
    from torch import nn
    from torchvision.models.resnet import Bottleneck, ResNet

    class L2CS(ResNet):
        def __init__(self):
            super().__init__(Bottleneck, [3, 4, 6, 3])
            self.fc = nn.Identity()
            self.fc_yaw_gaze = nn.Linear(2048, BINS)
            self.fc_pitch_gaze = nn.Linear(2048, BINS)

        def forward(self, x):
            x = self.maxpool(self.relu(self.bn1(self.conv1(x))))
            x = self.avgpool(self.layer4(self.layer3(self.layer2(self.layer1(x)))))
            x = torch.flatten(x, 1)
            return self.fc_yaw_gaze(x), self.fc_pitch_gaze(x)

    model = L2CS()
    state = torch.load(ensure_weights(), map_location="cpu", weights_only=True)
    state = {k: v for k, v in state.items() if not k.startswith("fc_finetune")}
    model.load_state_dict(state, strict=False)  # only the unused ResNet fc is absent
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    return model.eval().to(device), device


def _get():
    global _model
    with _lock:
        if _model is None:
            _model = _build()
        return _model


def face_crop(frame_rgb: np.ndarray, landmarks_px: np.ndarray) -> np.ndarray:
    """Square crop around the face landmarks, resized to 224x224."""
    import cv2

    x0, y0 = landmarks_px.min(axis=0)
    x1, y1 = landmarks_px.max(axis=0)
    side = max(x1 - x0, y1 - y0) * S.GAZE_L2CS_FACE_SCALE
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ax, ay = round(cx - side / 2), round(cy - side / 2)
    side = round(side)
    # pad so crops that leave the frame keep their geometry
    padded = cv2.copyMakeBorder(frame_rgb, side, side, side, side, cv2.BORDER_CONSTANT)
    crop = padded[ay + side : ay + 2 * side, ax + side : ax + 2 * side]
    return cv2.resize(crop, (224, 224))


def predict(frame_rgb: np.ndarray, landmarks_px: np.ndarray) -> tuple[float, float]:
    """Gaze (yaw, pitch) in radians, in the camera frame."""
    import torch

    model, device = _get()
    img = face_crop(frame_rgb, landmarks_px).astype(np.float32) / 255.0
    img = (img - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
    x = torch.from_numpy(img.transpose(2, 0, 1)[None].astype(np.float32)).to(device)
    with _lock, torch.no_grad():
        yaw_logits, pitch_logits = model(x)
        idx = torch.arange(BINS, dtype=torch.float32, device=device)
        yaw = (torch.softmax(yaw_logits, 1) * idx).sum(1) * 4 - 180
        pitch = (torch.softmax(pitch_logits, 1) * idx).sum(1) * 4 - 180
    return float(np.radians(yaw.item())), float(np.radians(pitch.item()))
