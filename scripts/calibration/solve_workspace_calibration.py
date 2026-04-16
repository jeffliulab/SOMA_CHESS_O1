#!/usr/bin/env python3
"""Solve eye-to-hand and planar workspace calibration from one ChArUco image."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src" / "arm_perception"))

from arm_perception.calibration_artifacts import (  # noqa: E402
    CALIBRATION_DIR,
    homography_from_points,
    normalize_bbox,
    pixel_to_world,
    quaternion_xyzw_from_rotation_matrix,
    save_yaml,
    load_yaml,
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
    parser.add_argument("--image", required=True, help="Reference ChArUco image path.")
    parser.add_argument(
        "--camera-info",
        default=str(CALIBRATION_DIR / "camera_intrinsics.yaml"),
        help="Shared camera intrinsics YAML.",
    )
    parser.add_argument(
        "--eye-to-hand-output",
        default=str(CALIBRATION_DIR / "eye_to_hand.yaml"),
        help="Output eye-to-hand YAML.",
    )
    parser.add_argument(
        "--workspace-output",
        default=str(CALIBRATION_DIR / "workspace.yaml"),
        help="Output workspace YAML.",
    )
    parser.add_argument("--camera-frame", default="camera_optical_frame")
    parser.add_argument("--world-frame", default="roarm_base_link")
    parser.add_argument("--squares-x", type=int, default=7)
    parser.add_argument("--squares-y", type=int, default=10)
    parser.add_argument("--square-length-m", type=float, default=0.020)
    parser.add_argument("--marker-length-m", type=float, default=0.015)
    parser.add_argument("--dictionary", default="DICT_4X4_50")
    parser.add_argument("--board-origin-world-x", type=float, default=0.0)
    parser.add_argument("--board-origin-world-y", type=float, default=0.0)
    parser.add_argument("--board-origin-world-z", type=float, default=0.0)
    parser.add_argument("--board-yaw-deg", type=float, default=0.0)
    parser.add_argument("--workspace-origin-x", type=float, default=0.0)
    parser.add_argument("--workspace-origin-y", type=float, default=0.0)
    parser.add_argument("--workspace-width-m", type=float, default=None)
    parser.add_argument("--workspace-height-m", type=float, default=None)
    parser.add_argument(
        "--bin-roi-norm",
        nargs=4,
        type=float,
        metavar=("X", "Y", "W", "H"),
        default=(0.02, 0.02, 0.18, 0.22),
        help="Fallback normalized ROI for the spare-piece container.",
    )
    parser.add_argument(
        "--board-roi-pad-norm",
        type=float,
        default=0.04,
        help="Extra normalized padding added around detected chessboard corners.",
    )
    parser.add_argument(
        "--reachability-margin-m",
        type=float,
        default=0.03,
        help="Inset margin used when auto-generating W1.8 test points.",
    )
    parser.add_argument(
        "--chessboard-inner-corners",
        nargs=2,
        type=int,
        metavar=("COLS", "ROWS"),
        default=(7, 7),
        help="Actual workspace chessboard inner-corner pattern used by /find_object.",
    )
    return parser.parse_args()


def _create_charuco_board(cv2, dictionary, squares_x: int, squares_y: int, square_length: float, marker_length: float):
    if hasattr(cv2.aruco, "CharucoBoard"):
        return cv2.aruco.CharucoBoard((squares_x, squares_y), square_length, marker_length, dictionary)
    return cv2.aruco.CharucoBoard_create(squares_x, squares_y, square_length, marker_length, dictionary)


def _load_camera_info(path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    data = load_yaml(path)
    if str(data.get("status", "")).lower() == "pending_calibration":
        raise SystemExit(f"camera intrinsics are still pending in {path}")
    k = np.asarray(data["camera_matrix"]["data"], dtype=np.float64).reshape(3, 3)
    d = np.asarray(data.get("distortion_coefficients", {}).get("data", []), dtype=np.float64).reshape(-1, 1)
    return k, d, data


def _board_corner_object_points(board) -> np.ndarray:
    if hasattr(board, "getChessboardCorners"):
        return np.asarray(board.getChessboardCorners(), dtype=np.float64)
    if hasattr(board, "chessboardCorners"):
        return np.asarray(board.chessboardCorners, dtype=np.float64)
    raise RuntimeError("Unable to extract ChArUco chessboard corner object points from OpenCV board.")


def _rotation_matrix_z(yaw_rad: float) -> np.ndarray:
    c = math.cos(yaw_rad)
    s = math.sin(yaw_rad)
    return np.array(
        [
            [c, -s, 0.0],
            [s, c, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _workspace_polygon(args: argparse.Namespace, board_world_xy: np.ndarray) -> list[list[float]]:
    if args.workspace_width_m and args.workspace_height_m:
        x0 = float(args.workspace_origin_x)
        y0 = float(args.workspace_origin_y)
        width = float(args.workspace_width_m)
        height = float(args.workspace_height_m)
        return [
            [x0, y0],
            [x0 + width, y0],
            [x0 + width, y0 + height],
            [x0, y0 + height],
        ]

    min_xy = board_world_xy.min(axis=0)
    max_xy = board_world_xy.max(axis=0)
    return [
        [float(min_xy[0]), float(min_xy[1])],
        [float(max_xy[0]), float(min_xy[1])],
        [float(max_xy[0]), float(max_xy[1])],
        [float(min_xy[0]), float(max_xy[1])],
    ]


def _auto_reachability_points(polygon: list[list[float]], bin_polygon: list[list[float]], margin: float) -> list[list[float]]:
    xs = [float(point[0]) for point in polygon]
    ys = [float(point[1]) for point in polygon]
    x0 = min(xs)
    x1 = max(xs)
    y0 = min(ys)
    y1 = max(ys)
    points = [
        [x0 + margin, y0 + margin],
        [x1 - margin, y0 + margin],
        [x1 - margin, y1 - margin],
        [x0 + margin, y1 - margin],
        [0.5 * (x0 + x1), 0.5 * (y0 + y1)],
    ]
    if bin_polygon:
        bx = [float(point[0]) for point in bin_polygon]
        by = [float(point[1]) for point in bin_polygon]
        points.append([0.5 * (min(bx) + max(bx)), 0.5 * (min(by) + max(by))])
    return [[float(px), float(py)] for px, py in points]


def main() -> int:
    args = _parse_args()
    cv2 = _import_cv2()

    image_path = Path(args.image).expanduser()
    if not image_path.exists():
        raise SystemExit(f"reference image not found: {image_path}")

    camera_info_path = Path(args.camera_info).expanduser()
    camera_matrix, distortion_coefficients, camera_info = _load_camera_info(camera_info_path)

    dictionary_id = getattr(cv2.aruco, args.dictionary, None)
    if dictionary_id is None:
        raise SystemExit(f"Unknown aruco dictionary: {args.dictionary}")

    dictionary = cv2.aruco.getPredefinedDictionary(dictionary_id)
    board = _create_charuco_board(
        cv2,
        dictionary,
        args.squares_x,
        args.squares_y,
        args.square_length_m,
        args.marker_length_m,
    )

    image = cv2.imread(str(image_path))
    if image is None:
        raise SystemExit(f"failed to read {image_path}")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    image_size = (gray.shape[1], gray.shape[0])

    corners, ids, _ = cv2.aruco.detectMarkers(gray, dictionary)
    if ids is None or len(ids) == 0:
        raise SystemExit("no aruco markers were detected in the reference image")

    retval, charuco_corners, charuco_ids = cv2.aruco.interpolateCornersCharuco(
        corners,
        ids,
        gray,
        board,
    )
    if retval is None or int(retval) < 6 or charuco_corners is None or charuco_ids is None:
        raise SystemExit("not enough ChArUco corners were detected for workspace calibration")

    object_points_all = _board_corner_object_points(board)
    object_points_board = object_points_all[charuco_ids.flatten()].reshape(-1, 3).astype(np.float64)
    image_points = charuco_corners.reshape(-1, 2).astype(np.float64)

    solved, rvec, tvec = cv2.solvePnP(
        object_points_board,
        image_points,
        camera_matrix,
        distortion_coefficients,
    )
    if not solved:
        raise SystemExit("solvePnP failed for the ChArUco reference image")

    rotation_camera_from_board, _ = cv2.Rodrigues(rvec)
    translation_camera_from_board = tvec.reshape(3)

    yaw_rad = math.radians(float(args.board_yaw_deg))
    rotation_world_from_board = _rotation_matrix_z(yaw_rad)
    translation_world_from_board = np.array(
        [
            float(args.board_origin_world_x),
            float(args.board_origin_world_y),
            float(args.board_origin_world_z),
        ],
        dtype=np.float64,
    )

    rotation_board_from_camera = rotation_camera_from_board.T
    translation_board_from_camera = -rotation_board_from_camera @ translation_camera_from_board
    rotation_world_from_camera = rotation_world_from_board @ rotation_board_from_camera
    translation_world_from_camera = (
        rotation_world_from_board @ translation_board_from_camera + translation_world_from_board
    )

    board_world_xy = (
        rotation_world_from_board @ object_points_board.T
    ).T[:, :2] + translation_world_from_board[:2]
    homography = homography_from_points(image_points, board_world_xy)

    min_xy = image_points.min(axis=0)
    max_xy = image_points.max(axis=0)
    pad_x = float(args.board_roi_pad_norm) * image_size[0]
    pad_y = float(args.board_roi_pad_norm) * image_size[1]
    board_roi_norm = normalize_bbox(
        image.shape,
        min_xy[0] - pad_x,
        min_xy[1] - pad_y,
        max_xy[0] + pad_x,
        max_xy[1] + pad_y,
    )

    existing_workspace = load_yaml(Path(args.workspace_output).expanduser())
    bin_roi_norm = {
        "x": float(args.bin_roi_norm[0]),
        "y": float(args.bin_roi_norm[1]),
        "width": float(args.bin_roi_norm[2]),
        "height": float(args.bin_roi_norm[3]),
    }
    if isinstance(existing_workspace.get("bin_roi_norm"), dict):
        bin_roi_norm = {
            "x": float(existing_workspace["bin_roi_norm"].get("x", bin_roi_norm["x"])),
            "y": float(existing_workspace["bin_roi_norm"].get("y", bin_roi_norm["y"])),
            "width": float(existing_workspace["bin_roi_norm"].get("width", bin_roi_norm["width"])),
            "height": float(existing_workspace["bin_roi_norm"].get("height", bin_roi_norm["height"])),
        }

    board_polygon_xy = [
        [float(x), float(y)]
        for x, y in (
            (rotation_world_from_board @ corner.reshape(3, 1)).reshape(3)[:2] + translation_world_from_board[:2]
            for corner in _board_corner_object_points(board)[:4]
        )
    ]
    tabletop_polygon_xy = _workspace_polygon(args, board_world_xy)

    bin_pixel_corners = [
        (
            image_size[0] * bin_roi_norm["x"],
            image_size[1] * bin_roi_norm["y"],
        ),
        (
            image_size[0] * (bin_roi_norm["x"] + bin_roi_norm["width"]),
            image_size[1] * bin_roi_norm["y"],
        ),
        (
            image_size[0] * (bin_roi_norm["x"] + bin_roi_norm["width"]),
            image_size[1] * (bin_roi_norm["y"] + bin_roi_norm["height"]),
        ),
        (
            image_size[0] * bin_roi_norm["x"],
            image_size[1] * (bin_roi_norm["y"] + bin_roi_norm["height"]),
        ),
    ]
    workspace_for_projection = {"pixel_to_world_homography": [float(v) for v in homography.flatten()]}
    bin_region_xy_m = []
    for px, py in bin_pixel_corners:
        world_x, world_y = pixel_to_world(px, py, workspace_for_projection)
        if world_x is not None and world_y is not None:
            bin_region_xy_m.append([float(world_x), float(world_y)])

    reachable_points_xy_m = _auto_reachability_points(
        tabletop_polygon_xy,
        bin_region_xy_m,
        margin=float(args.reachability_margin_m),
    )

    eye_to_hand_payload = {
        "status": "calibrated",
        "camera_frame": str(args.camera_frame),
        "world_frame": str(args.world_frame),
        "translation_xyz_m": [float(v) for v in translation_world_from_camera],
        "quaternion_xyzw": quaternion_xyzw_from_rotation_matrix(rotation_world_from_camera),
        "calibration_method": "charuco_pnp",
        "reference_image": _display_path(image_path),
        "source_camera_info": _display_path(camera_info_path),
        "board_origin_in_world_m": [
            float(args.board_origin_world_x),
            float(args.board_origin_world_y),
            float(args.board_origin_world_z),
        ],
        "board_yaw_deg": float(args.board_yaw_deg),
    }

    workspace_payload = dict(existing_workspace) if isinstance(existing_workspace, dict) else {}
    workspace_payload.update(
        {
            "status": "geometry_calibrated",
            "world_frame": str(args.world_frame),
            "camera_frame": str(args.camera_frame),
            "reference_image": _display_path(image_path),
            "camera_info_yaml": _display_path(camera_info_path),
            "image_size": [int(image_size[0]), int(image_size[1])],
            "board_roi_norm": board_roi_norm,
            "bin_roi_norm": bin_roi_norm,
            "board_polygon_xy_m": board_polygon_xy,
            "tabletop_polygon_xy_m": tabletop_polygon_xy,
            "pixel_to_world_homography": [float(v) for v in homography.flatten()],
            "bin_region_xy_m": bin_region_xy_m,
            "reachable_test_points_xy_m": reachable_points_xy_m,
            "no_go_regions_xy_m": workspace_payload.get("no_go_regions_xy_m", []),
            "chessboard_inner_corners": [
                int(args.chessboard_inner_corners[0]),
                int(args.chessboard_inner_corners[1]),
            ],
            "charuco_board": {
                "squares_x": int(args.squares_x),
                "squares_y": int(args.squares_y),
                "square_length_m": float(args.square_length_m),
                "marker_length_m": float(args.marker_length_m),
                "dictionary": str(args.dictionary),
            },
        }
    )
    workspace_payload.setdefault("named_targets", {})
    workspace_payload["notes"] = [
        "Generated by scripts/calibration/solve_workspace_calibration.py",
        "Run validate_workspace_reachability.py after manual W1.8 reach tests to merge no-go zones.",
    ]

    eye_to_hand_path = Path(args.eye_to_hand_output).expanduser()
    workspace_path = Path(args.workspace_output).expanduser()
    save_yaml(eye_to_hand_path, eye_to_hand_payload)
    save_yaml(workspace_path, workspace_payload)

    print(f"[eye_to_hand] wrote {eye_to_hand_path}")
    print(f"[workspace]   wrote {workspace_path}")
    print(f"  charuco_corners={len(image_points)}")
    print(f"  board_roi_norm={board_roi_norm}")
    print(f"  reachability_points={len(reachable_points_xy_m)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
