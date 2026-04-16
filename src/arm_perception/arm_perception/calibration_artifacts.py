"""Shared calibration artifact helpers for SOMA Arm."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np

try:
    import yaml
except ImportError:  # pragma: no cover - environment-dependent
    yaml = None


REPO_ROOT = Path(__file__).resolve().parents[3]
CALIBRATION_DIR = REPO_ROOT / "config" / "calibration"


def load_yaml(path: Path) -> dict:
    if yaml is None or not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def save_yaml(path: Path, data: dict) -> None:
    if yaml is None:  # pragma: no cover - environment-dependent
        raise RuntimeError("PyYAML is required to write calibration artifacts.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=False)


def is_pending(data: dict) -> bool:
    return str(data.get("status", "")).lower() == "pending_calibration"


def valid_roi(roi: dict) -> bool:
    try:
        x = float(roi["x"])
        y = float(roi["y"])
        w = float(roi["width"])
        h = float(roi["height"])
    except Exception:
        return False
    return x >= 0.0 and y >= 0.0 and w > 0.0 and h > 0.0 and x + w <= 1.0 and y + h <= 1.0


def sanitize_roi(roi: dict, fallback: dict | None = None) -> dict:
    if valid_roi(roi):
        return {
            "x": float(roi["x"]),
            "y": float(roi["y"]),
            "width": float(roi["width"]),
            "height": float(roi["height"]),
        }
    if fallback is not None and valid_roi(fallback):
        return sanitize_roi(fallback)
    return {"x": 0.10, "y": 0.12, "width": 0.80, "height": 0.72}


def roi_bounds(image_shape: tuple[int, int] | tuple[int, int, int], roi: dict) -> tuple[int, int, int, int]:
    height, width = image_shape[:2]
    safe_roi = sanitize_roi(roi)
    x0 = int(round(safe_roi["x"] * width))
    y0 = int(round(safe_roi["y"] * height))
    x1 = int(round((safe_roi["x"] + safe_roi["width"]) * width))
    y1 = int(round((safe_roi["y"] + safe_roi["height"]) * height))
    x0 = max(0, min(x0, width - 1))
    y0 = max(0, min(y0, height - 1))
    x1 = max(x0 + 1, min(x1, width))
    y1 = max(y0 + 1, min(y1, height))
    return x0, y0, x1, y1


def roi_center_pixels(
    image_shape: tuple[int, int] | tuple[int, int, int],
    roi: dict,
) -> tuple[float, float]:
    x0, y0, x1, y1 = roi_bounds(image_shape, roi)
    return 0.5 * (x0 + x1), 0.5 * (y0 + y1)


def normalize_bbox(
    image_shape: tuple[int, int] | tuple[int, int, int],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> dict:
    height, width = image_shape[:2]
    x0 = max(0.0, min(float(x0), float(width - 1)))
    y0 = max(0.0, min(float(y0), float(height - 1)))
    x1 = max(x0 + 1.0, min(float(x1), float(width)))
    y1 = max(y0 + 1.0, min(float(y1), float(height)))
    return {
        "x": x0 / float(width),
        "y": y0 / float(height),
        "width": (x1 - x0) / float(width),
        "height": (y1 - y0) / float(height),
    }


def pixel_to_world(pixel_x: float, pixel_y: float, workspace: dict) -> tuple[float | None, float | None]:
    values = workspace.get("pixel_to_world_homography") or []
    if len(values) != 9:
        return None, None
    matrix = np.array(values, dtype=np.float64).reshape(3, 3)
    point = np.array([pixel_x, pixel_y, 1.0], dtype=np.float64)
    transformed = matrix @ point
    if abs(float(transformed[2])) < 1e-9:
        return None, None
    return float(transformed[0] / transformed[2]), float(transformed[1] / transformed[2])


def world_to_pixel(world_x: float, world_y: float, workspace: dict) -> tuple[float | None, float | None]:
    values = workspace.get("pixel_to_world_homography") or []
    if len(values) != 9:
        return None, None
    matrix = np.array(values, dtype=np.float64).reshape(3, 3)
    det = float(np.linalg.det(matrix))
    if abs(det) < 1e-12:
        return None, None
    point = np.array([world_x, world_y, 1.0], dtype=np.float64)
    transformed = np.linalg.inv(matrix) @ point
    if abs(float(transformed[2])) < 1e-9:
        return None, None
    return float(transformed[0] / transformed[2]), float(transformed[1] / transformed[2])


def homography_from_points(pixel_points: Iterable[Iterable[float]], world_points: Iterable[Iterable[float]]) -> np.ndarray:
    pixel = np.asarray(list(pixel_points), dtype=np.float64)
    world = np.asarray(list(world_points), dtype=np.float64)
    if pixel.shape[0] < 4 or pixel.shape != world.shape or pixel.shape[1] != 2:
        raise ValueError("Need at least four 2D pixel/world correspondences with matching shapes.")

    rows = []
    for (u, v), (x, y) in zip(pixel, world):
        rows.append([u, v, 1.0, 0.0, 0.0, 0.0, -x * u, -x * v, -x])
        rows.append([0.0, 0.0, 0.0, u, v, 1.0, -y * u, -y * v, -y])
    matrix = np.asarray(rows, dtype=np.float64)
    _, _, vt = np.linalg.svd(matrix)
    homography = vt[-1].reshape(3, 3)
    if abs(homography[2, 2]) < 1e-12:
        raise ValueError("Computed homography is singular.")
    return homography / homography[2, 2]


def quaternion_xyzw_from_rotation_matrix(rotation: np.ndarray) -> list[float]:
    matrix = np.asarray(rotation, dtype=np.float64)
    trace = float(np.trace(matrix))
    if trace > 0.0:
        s = 0.5 / np.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (matrix[2, 1] - matrix[1, 2]) * s
        y = (matrix[0, 2] - matrix[2, 0]) * s
        z = (matrix[1, 0] - matrix[0, 1]) * s
    else:
        if matrix[0, 0] > matrix[1, 1] and matrix[0, 0] > matrix[2, 2]:
            s = 2.0 * np.sqrt(1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2])
            w = (matrix[2, 1] - matrix[1, 2]) / s
            x = 0.25 * s
            y = (matrix[0, 1] + matrix[1, 0]) / s
            z = (matrix[0, 2] + matrix[2, 0]) / s
        elif matrix[1, 1] > matrix[2, 2]:
            s = 2.0 * np.sqrt(1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2])
            w = (matrix[0, 2] - matrix[2, 0]) / s
            x = (matrix[0, 1] + matrix[1, 0]) / s
            y = 0.25 * s
            z = (matrix[1, 2] + matrix[2, 1]) / s
        else:
            s = 2.0 * np.sqrt(1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1])
            w = (matrix[1, 0] - matrix[0, 1]) / s
            x = (matrix[0, 2] + matrix[2, 0]) / s
            y = (matrix[1, 2] + matrix[2, 1]) / s
            z = 0.25 * s
    quat = np.asarray([x, y, z, w], dtype=np.float64)
    quat /= np.linalg.norm(quat)
    return [float(value) for value in quat]


def camera_info_yaml(
    camera_name: str,
    image_width: int,
    image_height: int,
    camera_matrix: np.ndarray,
    distortion_coefficients: np.ndarray,
    distortion_model: str = "plumb_bob",
) -> dict:
    k = np.asarray(camera_matrix, dtype=np.float64).reshape(3, 3)
    d = np.asarray(distortion_coefficients, dtype=np.float64).flatten()
    projection = np.array(
        [
            [k[0, 0], 0.0, k[0, 2], 0.0],
            [0.0, k[1, 1], k[1, 2], 0.0],
            [0.0, 0.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    return {
        "status": "calibrated",
        "camera_name": str(camera_name),
        "image_width": int(image_width),
        "image_height": int(image_height),
        "distortion_model": str(distortion_model),
        "camera_matrix": {"rows": 3, "cols": 3, "data": [float(v) for v in k.flatten()]},
        "distortion_coefficients": {"rows": 1, "cols": int(len(d)), "data": [float(v) for v in d]},
        "rectification_matrix": {
            "rows": 3,
            "cols": 3,
            "data": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        },
        "projection_matrix": {"rows": 3, "cols": 4, "data": [float(v) for v in projection.flatten()]},
    }
