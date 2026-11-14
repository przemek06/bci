"""Maps camera-space gaze features to screen coordinates (ridge-regularised polynomial fit)."""

import json
from pathlib import Path

import numpy as np

from .features import N_BASE, N_KEY

RIDGES = (0.003, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0)

# 3x5 grid of calibration targets (normalised canvas coords)
# more rows than columns: vertical gaze is the harder axis
TARGETS = [(x, y) for y in (0.1, 0.3, 0.5, 0.7, 0.9) for x in (0.08, 0.5, 0.92)]
# second round: the user moves their head while looking at each dot
MOVING_TARGETS = [(x, y) for y in (0.1, 0.5, 0.9) for x in (0.08, 0.5, 0.92)]


def base_cols(n_features: int, block: int | None) -> np.ndarray:
    """Columns the regression uses: the first N_BASE features of each camera block."""
    if not block or block <= N_BASE:
        return np.arange(n_features)
    return np.array(
        [c * block + i for c in range(n_features // block) for i in range(N_BASE)]
    )


def design_matrix(
    features: np.ndarray, block: int, quad: bool = True, n_key: int = N_KEY
) -> np.ndarray:
    """Bias + linear terms (+ quadratic terms of the key features of each camera block)."""
    f = np.atleast_2d(features)
    if not quad:
        return np.column_stack([np.ones(len(f)), f])
    key = [i for i in range(f.shape[1]) if i % block < n_key]
    quad = [f[:, i] * f[:, j] for a, i in enumerate(key) for j in key[a:]]
    return np.column_stack([np.ones(len(f)), f, *quad])


class GazeCalibration:
    def __init__(
        self,
        weights: np.ndarray,
        n_features: int,
        error: float = 0.0,
        mean: np.ndarray | None = None,
        scale: np.ndarray | None = None,
        block: int | None = None,
        quad: bool = True,
        error_xy: tuple[float, float] = (0.0, 0.0),
        tag: str = "",
        raw_block: int | None = None,
    ):
        self.method = "regression"
        self.raw_block = raw_block  # per-camera block size of incoming vectors
        self.cols = base_cols(n_features, raw_block)
        self.tag = tag  # backend + camera count this was calibrated for
        self.quad = quad
        self.error_xy = (
            error_xy  # cross-validated RMS error of x and y, fraction of the screen
        )
        self.weights = weights  # (terms, 2)
        self.n_features = n_features
        self.error = error  # RMS distance on the calibration samples, in screen widths
        n_used = len(self.cols)
        self.mean = np.zeros(n_used) if mean is None else mean
        self.scale = np.ones(n_used) if scale is None else scale
        self.block = block or n_used  # used features per camera

    @staticmethod
    def _solve(x: np.ndarray, y: np.ndarray, ridge: float) -> np.ndarray:
        reg = ridge * len(x) * np.eye(x.shape[1])
        reg[0, 0] = 0.0  # don't penalise the bias
        return np.linalg.solve(x.T @ x + reg, x.T @ y)

    @classmethod
    def fit(
        cls,
        features: np.ndarray,
        targets: np.ndarray,
        block: int | None = None,
    ) -> "GazeCalibration":
        """Fit on all samples. Model type and regularisation are picked by leave-one-target-out
        cross-validation, since few distinct dots make an unregularised fit look perfect
        on the calibration data while being useless elsewhere; the reported error is the CV error.
        """
        features = np.asarray(features, dtype=float)
        targets = np.asarray(targets, dtype=float)
        if len(features) < 9:
            raise ValueError("need at least 9 calibration samples")
        raw_block = block
        n_total = features.shape[1]
        features = features[:, base_cols(n_total, raw_block)]
        block = N_BASE if raw_block and raw_block > N_BASE else features.shape[1]
        mean = features.mean(axis=0)
        scale = features.std(axis=0)
        scale[scale < 1e-9] = 1.0
        z = (features - mean) / scale
        groups = np.unique(targets, axis=0)
        best = None
        for quad in (False, True):
            x = design_matrix(z, block, quad)
            for ridge in RIDGES:
                sq = []
                for g in groups:
                    held = np.all(targets == g, axis=1)
                    if held.all():
                        continue
                    w = cls._solve(x[~held], targets[~held], ridge)
                    sq.append((x[held] @ w - targets[held]) ** 2)
                if not sq:
                    continue
                mse = np.concatenate(sq).mean(axis=0)  # per axis
                score = mse.sum()
                if best is None or score < best[0]:
                    best = (score, quad, ridge, mse)
        if best is None:
            raise ValueError("need at least two distinct calibration targets")
        _, quad, ridge, mse = best
        w = cls._solve(design_matrix(z, block, quad), targets, ridge)
        err_xy = (float(np.sqrt(mse[0])), float(np.sqrt(mse[1])))
        return cls(
            w,
            n_total,
            float(np.sqrt(mse.sum())),
            mean,
            scale,
            block,
            quad,
            err_xy,
            raw_block=raw_block,
        )

    def predict(self, features: np.ndarray) -> np.ndarray:
        # clip so a head pose never seen in calibration can't extrapolate wildly
        f = np.atleast_2d(features)[:, self.cols]
        f = np.clip((f - self.mean) / self.scale, -4.0, 4.0)
        return design_matrix(f, self.block, self.quad) @ self.weights

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "weights": self.weights.tolist(),
                    "n_features": self.n_features,
                    "error": self.error,
                    "mean": self.mean.tolist(),
                    "scale": self.scale.tolist(),
                    "block": self.block,
                    "quad": self.quad,
                    "error_xy": list(self.error_xy),
                    "tag": self.tag,
                    "kind": "regression",
                    "raw_block": self.raw_block,
                }
            )
        )

    @classmethod
    def load(cls, path: Path):
        try:
            d = json.loads(Path(path).read_text())
            if d.get("kind") == "geometry":
                from .geometry import GeometricCalibration

                return GeometricCalibration.from_dict(d)
            return cls(
                np.array(d["weights"]),
                int(d["n_features"]),
                float(d["error"]),
                np.array(d["mean"]),
                np.array(d["scale"]),
                int(d["block"]),
                bool(d["quad"]),
                tuple(d["error_xy"]),
                d.get("tag", ""),
                d.get("raw_block"),
            )
        except (OSError, ValueError, KeyError):
            return None  # missing or from an older version: recalibrate
