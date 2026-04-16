#!/usr/bin/env python3
"""Calibrate C922 intrinsics from saved ChArUco images."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src" / "arm_perception"))

from arm_perception.calibration_artifacts import (  # noqa: E402
    CALIBRATION_DIR,
    camera_info_yaml,
    save_yaml,
)


def _import_cv2():
    try:
        import cv2  # type: ignore
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "OpenCV with aruco support is required. Run this script inside the repo .venv."
        ) from exc
    if not hasattr(cv2, "aruco"):
        raise RuntimeError("This OpenCV build does not include cv2.aruco.")
    return cv2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-glob",
        default="data/calibration/charuco/*.png",
        help="Glob for ChArUco images captured from the bridge receiver.",
    )
    parser.add_argument(
        "--output",
        default=str(CALIBRATION_DIR / "camera_intrinsics.yaml"),
        help="Output YAML path.",
    )
    parser.add_argument("--camera-name", default="c922_windows_bridge_540p")
    parser.add_argument("--squares-x", type=int, default=7)
    parser.add_argument("--squares-y", type=int, default=10)
    parser.add_argument("--square-length-m", type=float, default=0.020)
    parser.add_argument("--marker-length-m", type=float, default=0.015)
    parser.add_argument("--dictionary", default="DICT_4X4_50")
    parser.add_argument("--min-charuco-corners", type=int, default=8)
    return parser.parse_args()


def _create_charuco_board(cv2, dictionary, squares_x: int, squares_y: int, square_length: float, marker_length: float):
    if hasattr(cv2.aruco, "CharucoBoard"):
        return cv2.aruco.CharucoBoard((squares_x, squares_y), square_length, marker_length, dictionary)
    return cv2.aruco.CharucoBoard_create(squares_x, squares_y, square_length, marker_length, dictionary)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    args = _parse_args()
    cv2 = _import_cv2()

    dictionary_id = getattr(cv2.aruco, args.dictionary, None)
    if dictionary_id is None:
        raise SystemExit(f"Unknown aruco dictionary: {args.dictionary}")

    image_paths = sorted(REPO_ROOT.glob(args.input_glob))
    if not image_paths:
        raise SystemExit(f"No images matched {args.input_glob}")

    dictionary = cv2.aruco.getPredefinedDictionary(dictionary_id)
    board = _create_charuco_board(
        cv2,
        dictionary,
        args.squares_x,
        args.squares_y,
        args.square_length_m,
        args.marker_length_m,
    )

    all_charuco_corners = []
    all_charuco_ids = []
    image_size = None
    accepted_images = []

    for image_path in image_paths:
        image = cv2.imread(str(image_path))
        if image is None:
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = cv2.aruco.detectMarkers(gray, dictionary)
        if ids is None or len(ids) == 0:
            continue
        retval, charuco_corners, charuco_ids = cv2.aruco.interpolateCornersCharuco(
            corners,
            ids,
            gray,
            board,
        )
        if retval is None or int(retval) < args.min_charuco_corners:
            continue
        if charuco_corners is None or charuco_ids is None:
            continue
        all_charuco_corners.append(charuco_corners)
        all_charuco_ids.append(charuco_ids)
        image_size = (gray.shape[1], gray.shape[0])
        accepted_images.append(image_path)

    if not accepted_images or image_size is None:
        raise SystemExit(
            "No usable ChArUco observations were found. Capture more frames with varied board poses."
        )

    reprojection_error, camera_matrix, distortion_coefficients, _, _ = cv2.aruco.calibrateCameraCharuco(
        all_charuco_corners,
        all_charuco_ids,
        board,
        image_size,
        None,
        None,
    )

    output_path = Path(args.output).expanduser()
    payload = camera_info_yaml(
        camera_name=args.camera_name,
        image_width=image_size[0],
        image_height=image_size[1],
        camera_matrix=camera_matrix,
        distortion_coefficients=distortion_coefficients,
    )
    payload["calibration_method"] = "charuco"
    payload["charuco_board"] = {
        "squares_x": args.squares_x,
        "squares_y": args.squares_y,
        "square_length_m": args.square_length_m,
        "marker_length_m": args.marker_length_m,
        "dictionary": args.dictionary,
    }
    payload["frames_used"] = len(accepted_images)
    payload["reprojection_error_px"] = float(reprojection_error)
    payload["source_images"] = [_display_path(path) for path in accepted_images]
    save_yaml(output_path, payload)

    print(f"[camera_intrinsics] wrote {output_path}")
    print(f"  frames_used={len(accepted_images)}")
    print(f"  reprojection_error_px={float(reprojection_error):.4f}")
    print(f"  image_size={image_size[0]}x{image_size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
