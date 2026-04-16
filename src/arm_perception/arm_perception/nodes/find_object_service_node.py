#!/usr/bin/env python3
"""Geometry-first `/find_object` service for SOMA Arm."""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import rclpy
from arm_interfaces.msg import PerceptionFeedback
from arm_interfaces.srv import FindObject
from builtin_interfaces.msg import Time as TimeMsg
from rclpy.node import Node
from sensor_msgs.msg import Image

from arm_perception.calibration_artifacts import (
    CALIBRATION_DIR,
    is_pending,
    load_yaml,
    pixel_to_world,
    roi_bounds,
    roi_center_pixels,
    sanitize_roi,
    valid_roi,
    world_to_pixel,
)


_CV2_CACHE = None
_CV2_TRIED = False


def _get_cv2():
    global _CV2_CACHE, _CV2_TRIED
    if _CV2_TRIED:
        return _CV2_CACHE
    _CV2_TRIED = True
    try:  # pragma: no cover - environment-dependent
        import cv2  # type: ignore

        _CV2_CACHE = cv2
    except Exception:
        _CV2_CACHE = None
    return _CV2_CACHE


@dataclass
class TargetSpec:
    label: str
    mode: str
    roi_norm: dict | None = None
    world_xy_m: tuple[float, float] | None = None
    query: str = ""


@dataclass
class DetectionResult:
    label: str
    score: float
    pixel_x: float
    pixel_y: float
    message: str
    method: str
    world_x: float | None = None
    world_y: float | None = None


class FindObjectServiceNode(Node):
    def __init__(self) -> None:
        super().__init__("find_object_service")
        self.declare_parameter("image_topic", "/camera/image_raw")
        self.declare_parameter("service_name", "/find_object")
        self.declare_parameter("feedback_topic", "/camera_feedback")
        self.declare_parameter("enable_feedback_bridge", True)
        self.declare_parameter("feedback_host", "127.0.0.1")
        self.declare_parameter("feedback_port", 65434)
        self.declare_parameter("feedback_interval_sec", 0.5)
        self.declare_parameter("requested_mode_default", "normal")
        self.declare_parameter("workspace_yaml", str(CALIBRATION_DIR / "workspace.yaml"))
        self.declare_parameter("eye_to_hand_yaml", str(CALIBRATION_DIR / "eye_to_hand.yaml"))

        image_topic = self.get_parameter("image_topic").value
        service_name = self.get_parameter("service_name").value
        feedback_topic = self.get_parameter("feedback_topic").value
        self._enable_feedback_bridge = bool(self.get_parameter("enable_feedback_bridge").value)
        self._feedback_host = str(self.get_parameter("feedback_host").value)
        self._feedback_port = int(self.get_parameter("feedback_port").value)
        self._requested_mode_default = str(self.get_parameter("requested_mode_default").value)
        self._workspace_path = Path(str(self.get_parameter("workspace_yaml").value)).expanduser()
        self._eye_to_hand_path = Path(str(self.get_parameter("eye_to_hand_yaml").value)).expanduser()

        self._workspace = {}
        self._eye_to_hand = {}
        self._workspace_mtime = None
        self._eye_to_hand_mtime = None
        self._latest_frame: np.ndarray | None = None
        self._latest_stamp: TimeMsg | None = None
        self._feedback_socket: socket.socket | None = None

        self._reload_calibration(force=True)

        self.create_subscription(Image, image_topic, self._on_image, 10)
        self.create_service(FindObject, service_name, self._handle_find_object)
        self._feedback_pub = self.create_publisher(PerceptionFeedback, feedback_topic, 10)
        self.create_timer(
            float(self.get_parameter("feedback_interval_sec").value),
            self._publish_feedback,
        )

        self.get_logger().info(
            "Find object service ready | "
            f"image_topic={image_topic} service={service_name} "
            f"feedback_topic={feedback_topic} workspace_yaml={self._workspace_path}"
        )

    def _reload_calibration(self, force: bool = False) -> None:
        workspace_mtime = self._workspace_path.stat().st_mtime if self._workspace_path.exists() else None
        if force or workspace_mtime != self._workspace_mtime:
            self._workspace = load_yaml(self._workspace_path)
            self._workspace_mtime = workspace_mtime

        eye_mtime = self._eye_to_hand_path.stat().st_mtime if self._eye_to_hand_path.exists() else None
        if force or eye_mtime != self._eye_to_hand_mtime:
            self._eye_to_hand = load_yaml(self._eye_to_hand_path)
            self._eye_to_hand_mtime = eye_mtime

    def _on_image(self, msg: Image) -> None:
        frame = _decode_image(msg)
        if frame is None:
            return
        self._latest_frame = frame
        self._latest_stamp = msg.header.stamp
        self._reload_calibration()

    def _handle_find_object(self, request: FindObject.Request, response: FindObject.Response):
        self._reload_calibration()
        query = request.text_query.strip().lower()
        response.stamp = self._latest_stamp or self.get_clock().now().to_msg()

        if self._latest_frame is None:
            response.success = False
            response.message = "No camera frame received yet."
            return response

        if is_pending(self._workspace):
            response.success = False
            response.message = (
                "workspace calibration is still pending; run the Week 1 calibration scripts "
                "before using /find_object for world grounding."
            )
            return response

        target = _resolve_target_spec(query, self._workspace)
        if target is None:
            response.success = False
            response.message = (
                "Unsupported query for the current geometry-first pipeline. "
                "Supported categories: board/workspace, bin/container, piece/object, or named_targets in workspace.yaml."
            )
            return response

        detection = _detect_target(self._latest_frame, self._workspace, target)
        if detection is None:
            response.success = False
            response.label = target.label
            response.message = "No plausible target instance was found in the calibrated workspace."
            return response

        if detection.world_x is not None and detection.world_y is not None:
            world_x, world_y = detection.world_x, detection.world_y
        else:
            world_x, world_y = pixel_to_world(detection.pixel_x, detection.pixel_y, self._workspace)

        if world_x is None or world_y is None:
            response.success = False
            response.label = detection.label
            response.score = float(detection.score)
            response.pixel_x = float(detection.pixel_x)
            response.pixel_y = float(detection.pixel_y)
            response.world_x = 0.0
            response.world_y = 0.0
            response.message = (
                "Target was localized in pixels, but pixel_to_world_homography is missing or invalid."
            )
            return response

        response.success = True
        response.label = detection.label
        response.score = float(detection.score)
        response.pixel_x = float(detection.pixel_x)
        response.pixel_y = float(detection.pixel_y)
        response.world_x = float(world_x)
        response.world_y = float(world_y)
        response.message = detection.message
        return response

    def _publish_feedback(self) -> None:
        if self._latest_frame is None:
            return
        self._reload_calibration()

        metrics = _compute_feedback_metrics(
            self._latest_frame,
            self._workspace,
            requested_mode_default=self._requested_mode_default,
        )
        msg = PerceptionFeedback()
        msg.stamp = self._latest_stamp or self.get_clock().now().to_msg()
        msg.board_visible = metrics["board_visible"]
        msg.board_confidence = float(metrics["board_confidence"])
        msg.corners_detected = int(metrics["corners_detected"])
        msg.object_confidence = float(metrics["object_confidence"])
        msg.mean_luma = float(metrics["mean_luma"])
        msg.overexposed_ratio = float(metrics["overexposed_ratio"])
        msg.sharpness = float(metrics["sharpness"])
        msg.requested_mode = str(metrics["requested_mode"])
        self._feedback_pub.publish(msg)

        if self._enable_feedback_bridge:
            self._send_feedback(metrics)

    def _send_feedback(self, metrics: dict) -> None:
        payload = json.dumps(metrics, separators=(",", ":")).encode("utf-8") + b"\n"
        if self._feedback_socket is None:
            try:
                self._feedback_socket = socket.create_connection(
                    (self._feedback_host, self._feedback_port),
                    timeout=0.2,
                )
                self._feedback_socket.settimeout(0.2)
            except OSError:
                self._feedback_socket = None
                return

        try:
            self._feedback_socket.sendall(payload)
        except OSError:
            try:
                self._feedback_socket.close()
            except OSError:
                pass
            self._feedback_socket = None

    def destroy_node(self):
        if self._feedback_socket is not None:
            try:
                self._feedback_socket.close()
            except OSError:
                pass
            self._feedback_socket = None
        super().destroy_node()


def _decode_image(msg: Image) -> np.ndarray | None:
    if msg.encoding not in {"bgr8", "rgb8"}:
        return None
    frame = np.frombuffer(msg.data, dtype=np.uint8).reshape((msg.height, msg.width, 3))
    if msg.encoding == "rgb8":
        return frame[:, :, ::-1].copy()
    return frame.copy()


def _resolve_target_spec(query: str, workspace: dict) -> TargetSpec | None:
    named_targets = workspace.get("named_targets") or {}
    if isinstance(named_targets, dict):
        for label, spec in named_targets.items():
            aliases = [str(label).lower()]
            aliases.extend(str(item).lower() for item in spec.get("aliases", []))
            if any(alias and alias in query for alias in aliases):
                world_xy = spec.get("world_xy_m") or spec.get("world_xy")
                if isinstance(world_xy, (list, tuple)) and len(world_xy) >= 2:
                    return TargetSpec(
                        label=str(label),
                        mode="fixed_world",
                        world_xy_m=(float(world_xy[0]), float(world_xy[1])),
                        query=query,
                    )
                roi = spec.get("roi_norm") or spec.get("region")
                return TargetSpec(
                    label=str(label),
                    mode=str(spec.get("mode", "region")),
                    roi_norm=roi if isinstance(roi, dict) else None,
                    query=query,
                )

    if any(token in query for token in ("board", "chessboard", "workspace", "tabletop", "table")):
        return TargetSpec(
            label="board",
            mode="board",
            roi_norm=workspace.get("board_roi_norm"),
            query=query,
        )
    if any(token in query for token in ("bin", "box", "container", "storage")):
        return TargetSpec(
            label="bin",
            mode="region",
            roi_norm=workspace.get("bin_roi_norm"),
            query=query,
        )
    if any(
        token in query
        for token in (
            "piece",
            "pawn",
            "knight",
            "bishop",
            "rook",
            "queen",
            "king",
            "object",
            "item",
            "sponge",
            "block",
            "cube",
        )
    ):
        return TargetSpec(
            label="object",
            mode="foreground",
            roi_norm=workspace.get("object_search_roi_norm") or workspace.get("board_roi_norm"),
            query=query,
        )
    return None


def _detect_target(frame: np.ndarray, workspace: dict, target: TargetSpec) -> DetectionResult | None:
    if target.mode == "fixed_world" and target.world_xy_m is not None:
        pixel_x, pixel_y = world_to_pixel(target.world_xy_m[0], target.world_xy_m[1], workspace)
        if pixel_x is None or pixel_y is None:
            pixel_x, pixel_y = 0.0, 0.0
        return DetectionResult(
            label=target.label,
            score=1.0,
            pixel_x=float(pixel_x),
            pixel_y=float(pixel_y),
            world_x=float(target.world_xy_m[0]),
            world_y=float(target.world_xy_m[1]),
            method="named_target",
            message=f"Resolved named target '{target.label}' from workspace.yaml.",
        )

    roi = sanitize_roi(target.roi_norm or workspace.get("board_roi_norm"))
    if target.mode == "board":
        return _detect_board(frame, roi, workspace)
    if target.mode == "region":
        return _detect_region_target(frame, roi, target.label)
    if target.mode == "foreground":
        return _detect_foreground_target(frame, roi, target.query)
    return _detect_region_target(frame, roi, target.label)


def _detect_board(frame: np.ndarray, roi: dict, workspace: dict) -> DetectionResult | None:
    corners = _find_chessboard_corners(frame, roi, workspace)
    if corners is not None and corners.size > 0:
        center = corners.mean(axis=0)
        expected = _expected_corner_count(workspace)
        confidence = min(1.0, corners.shape[0] / max(1, expected))
        return DetectionResult(
            label="board",
            score=float(max(0.65, confidence)),
            pixel_x=float(center[0]),
            pixel_y=float(center[1]),
            method="chessboard_corners",
            message=f"Resolved board center from {corners.shape[0]} chessboard corners.",
        )
    return _detect_region_target(frame, roi, "board", fallback_score=0.45)


def _detect_region_target(
    frame: np.ndarray,
    roi: dict,
    label: str,
    fallback_score: float = 0.30,
) -> DetectionResult:
    cv2 = _get_cv2()
    x0, y0, x1, y1 = roi_bounds(frame.shape, roi)
    center_x, center_y = roi_center_pixels(frame.shape, roi)
    if cv2 is None:
        return DetectionResult(
            label=label,
            score=float(fallback_score),
            pixel_x=float(center_x),
            pixel_y=float(center_y),
            method="roi_center",
            message=f"OpenCV unavailable; returned calibrated ROI center for {label}.",
        )

    roi_frame = frame[y0:y1, x0:x1]
    gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    adaptive = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        6,
    )
    edges = cv2.Canny(blur, 40, 120)
    mask = cv2.bitwise_or(adaptive, edges)
    kernel = np.ones((3, 3), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    roi_area = max(1.0, float((x1 - x0) * (y1 - y0)))
    best_score = -1.0
    best_center = (center_x, center_y)
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < roi_area * 0.02:
            continue
        rect = cv2.minAreaRect(contour)
        (cx, cy), (width, height), _ = rect
        rect_area = max(1.0, float(width * height))
        fill = area / rect_area
        score = min(1.0, area / roi_area * 0.8 + max(0.0, min(fill, 1.0)) * 0.2)
        if score > best_score:
            best_score = score
            best_center = (x0 + float(cx), y0 + float(cy))

    if best_score <= 0.0:
        return DetectionResult(
            label=label,
            score=float(fallback_score),
            pixel_x=float(center_x),
            pixel_y=float(center_y),
            method="roi_center",
            message=f"Returned calibrated ROI center for {label}.",
        )

    return DetectionResult(
        label=label,
        score=float(best_score),
        pixel_x=float(best_center[0]),
        pixel_y=float(best_center[1]),
        method="contour_region",
        message=f"Resolved {label} from the dominant contour inside its calibrated ROI.",
    )


def _detect_foreground_target(frame: np.ndarray, roi: dict, query: str) -> DetectionResult | None:
    cv2 = _get_cv2()
    if cv2 is None:
        return None

    x0, y0, x1, y1 = roi_bounds(frame.shape, roi)
    roi_frame = frame[y0:y1, x0:x1]
    gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    kernel_size = max(9, int(min(roi_frame.shape[:2]) * 0.08) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    tophat = cv2.morphologyEx(blur, cv2.MORPH_TOPHAT, kernel)
    blackhat = cv2.morphologyEx(blur, cv2.MORPH_BLACKHAT, kernel)
    enhanced = cv2.max(tophat, blackhat)
    _, threshold = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    edges = cv2.Canny(blur, 45, 120)
    mask = cv2.bitwise_or(threshold, edges)
    close_kernel = np.ones((3, 3), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=2)
    mask = cv2.dilate(mask, close_kernel, iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    roi_area = max(1.0, float((x1 - x0) * (y1 - y0)))
    selector = _spatial_hint(query)
    best = None
    best_score = -1.0
    for contour in contours:
        area = float(cv2.contourArea(contour))
        area_ratio = area / roi_area
        if area_ratio < 0.002 or area_ratio > 0.20:
            continue
        perimeter = max(float(cv2.arcLength(contour, True)), 1.0)
        x, y, width, height = cv2.boundingRect(contour)
        extent = area / max(1.0, float(width * height))
        circularity = float(4.0 * np.pi * area / (perimeter * perimeter))
        aspect = float(width) / max(1.0, float(height))
        aspect_bonus = max(0.0, 1.0 - min(abs(aspect - 1.0), 1.5) / 1.5)
        moments = cv2.moments(contour)
        if abs(moments["m00"]) < 1e-6:
            continue
        cx = x0 + float(moments["m10"] / moments["m00"])
        cy = y0 + float(moments["m01"] / moments["m00"])
        base_score = min(1.0, area_ratio * 2.5 + extent * 0.25 + circularity * 0.15 + aspect_bonus * 0.10)
        final_score = base_score + 0.15 * _position_bonus(cx, cy, x0, y0, x1, y1, selector)
        if final_score > best_score:
            best_score = final_score
            best = (cx, cy)

    if best is None:
        return None

    return DetectionResult(
        label="object",
        score=float(min(best_score, 1.0)),
        pixel_x=float(best[0]),
        pixel_y=float(best[1]),
        method="foreground_blob",
        message="Resolved object candidate from foreground contour heuristics inside the calibrated workspace ROI.",
    )


def _spatial_hint(query: str) -> str:
    if "left" in query and "right" not in query:
        return "left"
    if "right" in query:
        return "right"
    if "top" in query or "upper" in query:
        return "top"
    if "bottom" in query or "lower" in query:
        return "bottom"
    if "center" in query or "middle" in query:
        return "center"
    return "largest"


def _position_bonus(cx: float, cy: float, x0: int, y0: int, x1: int, y1: int, selector: str) -> float:
    width = max(1.0, float(x1 - x0))
    height = max(1.0, float(y1 - y0))
    norm_x = (cx - x0) / width
    norm_y = (cy - y0) / height
    if selector == "left":
        return 1.0 - norm_x
    if selector == "right":
        return norm_x
    if selector == "top":
        return 1.0 - norm_y
    if selector == "bottom":
        return norm_y
    if selector == "center":
        dx = abs(norm_x - 0.5) * 2.0
        dy = abs(norm_y - 0.5) * 2.0
        return max(0.0, 1.0 - max(dx, dy))
    return 0.0


def _find_chessboard_corners(frame: np.ndarray, roi: dict, workspace: dict) -> np.ndarray | None:
    cv2 = _get_cv2()
    if cv2 is None:
        return None

    pattern = workspace.get("chessboard_inner_corners") or [7, 7]
    if len(pattern) != 2:
        pattern = [7, 7]
    cols = int(pattern[0])
    rows = int(pattern[1])
    if cols < 2 or rows < 2:
        return None

    x0, y0, x1, y1 = roi_bounds(frame.shape, roi)
    roi_frame = frame[y0:y1, x0:x1]
    gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
    flags = cv2.CALIB_CB_NORMALIZE_IMAGE
    success = False
    corners = None
    if hasattr(cv2, "findChessboardCornersSB"):
        success, corners = cv2.findChessboardCornersSB(gray, (cols, rows), flags=flags)
    if not success:
        success, corners = cv2.findChessboardCorners(gray, (cols, rows), flags=flags)
        if success:
            criteria = (
                cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                30,
                0.001,
            )
            corners = cv2.cornerSubPix(gray, corners, (5, 5), (-1, -1), criteria)
    if not success or corners is None:
        return None

    reshaped = corners.reshape(-1, 2).astype(np.float64)
    reshaped[:, 0] += x0
    reshaped[:, 1] += y0
    return reshaped


def _expected_corner_count(workspace: dict) -> int:
    pattern = workspace.get("chessboard_inner_corners") or [7, 7]
    if len(pattern) != 2:
        return 49
    return int(pattern[0]) * int(pattern[1])


def _compute_feedback_metrics(frame: np.ndarray, workspace: dict, requested_mode_default: str = "normal") -> dict:
    roi = sanitize_roi(workspace.get("board_roi_norm"))
    x0, y0, x1, y1 = roi_bounds(frame.shape, roi)
    roi_frame = frame[y0:y1, x0:x1]
    gray_f = (
        0.114 * roi_frame[:, :, 0].astype(np.float32)
        + 0.587 * roi_frame[:, :, 1].astype(np.float32)
        + 0.299 * roi_frame[:, :, 2].astype(np.float32)
    )

    if gray_f.shape[0] >= 3 and gray_f.shape[1] >= 3:
        lap = (
            -4.0 * gray_f[1:-1, 1:-1]
            + gray_f[:-2, 1:-1]
            + gray_f[2:, 1:-1]
            + gray_f[1:-1, :-2]
            + gray_f[1:-1, 2:]
        )
        lap_var = float(lap.var())
    else:
        lap_var = 0.0

    mean_luma = float(gray_f.mean())
    overexposed_ratio = float((gray_f >= 245.0).mean())
    board_observation = _observe_board(frame, roi, workspace)
    board_visible = board_observation["visible"]
    board_confidence = float(board_observation["confidence"])
    corners_detected = int(board_observation["corners_detected"])

    requested_mode = requested_mode_default
    if not board_visible and (mean_luma < 90.0 or overexposed_ratio > 0.18 or lap_var < 45.0):
        requested_mode = "recover"

    return {
        "timestamp_ms": int(time.time() * 1000),
        "board_visible": bool(board_visible),
        "board_confidence": board_confidence,
        "corners_detected": corners_detected,
        "object_confidence": board_confidence,
        "mean_luma": mean_luma,
        "overexposed_ratio": overexposed_ratio,
        "sharpness": lap_var,
        "requested_mode": requested_mode,
    }


def _observe_board(frame: np.ndarray, roi: dict, workspace: dict) -> dict:
    corners = _find_chessboard_corners(frame, roi, workspace)
    expected = _expected_corner_count(workspace)
    if corners is not None and corners.size > 0:
        confidence = min(1.0, corners.shape[0] / max(1, expected))
        return {
            "visible": True,
            "confidence": max(0.65, confidence),
            "corners_detected": int(corners.shape[0]),
        }
    return {"visible": False, "confidence": 0.20, "corners_detected": 0}


def main(args=None) -> None:
    rclpy.init(args=args)
    node = FindObjectServiceNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()

