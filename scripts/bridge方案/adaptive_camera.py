#!/usr/bin/env python3
"""Adaptive camera control helpers for the Windows C922 bridge."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

from camera_controls import get_camera_control_value, set_camera_control


@dataclass(frozen=True)
class QualityMetrics:
    mean_luma: float
    overexposed_ratio: float
    contrast_span: float
    sharpness: float
    color_cast: float
    mean_b: float
    mean_g: float
    mean_r: float
    roi_bounds_px: tuple[int, int, int, int]


@dataclass(frozen=True)
class FeedbackSnapshot:
    timestamp_ms: int
    board_visible: bool
    board_confidence: float
    corners_detected: int
    object_confidence: float
    mean_luma: float
    overexposed_ratio: float
    sharpness: float
    requested_mode: str


def add_adaptive_camera_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--adaptive-mode",
        choices=("off", "quality", "hybrid"),
        default="off",
        help=(
            "Adaptive camera mode. 'quality' uses image-quality metrics only; "
            "'hybrid' also consumes the optional localhost feedback channel."
        ),
    )
    parser.add_argument(
        "--adaptive-roi",
        default="0.10,0.12,0.80,0.72",
        help=(
            "Normalized ROI x,y,w,h used for quality metrics and adaptive control. "
            "Defaults to the central tabletop area."
        ),
    )
    parser.add_argument(
        "--adaptive-eval-interval-sec",
        type=float,
        default=0.35,
        help="How often to recompute adaptive metrics.",
    )
    parser.add_argument(
        "--adaptive-cooldown-sec",
        type=float,
        default=0.75,
        help="Minimum delay between successive camera-control changes.",
    )
    parser.add_argument(
        "--adaptive-target-luma",
        type=float,
        default=118.0,
        help="Desired ROI mean luma in 0-255 grayscale space.",
    )
    parser.add_argument(
        "--adaptive-luma-tolerance",
        type=float,
        default=12.0,
        help="No exposure/gain changes are made while ROI luma stays within this band.",
    )
    parser.add_argument(
        "--adaptive-max-overexposed-ratio",
        type=float,
        default=0.02,
        help="Maximum acceptable fraction of pixels above the overexposed threshold.",
    )
    parser.add_argument(
        "--adaptive-overexposed-threshold",
        type=float,
        default=245.0,
        help="Grayscale threshold used to count overexposed pixels.",
    )
    parser.add_argument(
        "--adaptive-min-sharpness",
        type=float,
        default=110.0,
        help="Minimum Laplacian variance before a focus rescue is considered.",
    )
    parser.add_argument(
        "--adaptive-color-cast-threshold",
        type=float,
        default=14.0,
        help="Minimum mean-channel deviation before white-balance correction is considered.",
    )
    parser.add_argument(
        "--adaptive-min-corners",
        type=int,
        default=20,
        help="Hybrid mode threshold for the minimum number of visible board corners.",
    )
    parser.add_argument(
        "--adaptive-min-board-confidence",
        type=float,
        default=0.50,
        help="Hybrid mode threshold for board visibility confidence.",
    )
    parser.add_argument(
        "--adaptive-min-object-confidence",
        type=float,
        default=0.35,
        help="Hybrid mode threshold for downstream object confidence.",
    )
    parser.add_argument(
        "--adaptive-feedback-freshness-sec",
        type=float,
        default=2.0,
        help="How long a feedback packet stays valid in hybrid mode.",
    )
    parser.add_argument(
        "--feedback-host",
        default="127.0.0.1",
        help="Local host for the optional adaptive feedback channel.",
    )
    parser.add_argument(
        "--feedback-port",
        type=int,
        default=65434,
        help="Local TCP port for the optional adaptive feedback channel.",
    )
    parser.add_argument(
        "--adaptive-exposure-step",
        type=float,
        default=1.0,
        help="Raw exposure step applied per adaptive change.",
    )
    parser.add_argument(
        "--adaptive-gain-step",
        type=float,
        default=4.0,
        help="Raw gain step applied per adaptive change.",
    )
    parser.add_argument(
        "--adaptive-wb-step",
        type=float,
        default=200.0,
        help="White-balance temperature step applied per adaptive change.",
    )
    parser.add_argument(
        "--adaptive-focus-step",
        type=float,
        default=2.0,
        help="Raw focus step applied per focus rescue.",
    )
    parser.add_argument("--adaptive-exposure-min", type=float, default=-11.0)
    parser.add_argument("--adaptive-exposure-max", type=float, default=-1.0)
    parser.add_argument("--adaptive-gain-min", type=float, default=0.0)
    parser.add_argument("--adaptive-gain-max", type=float, default=255.0)
    parser.add_argument("--adaptive-wb-min", type=float, default=2800.0)
    parser.add_argument("--adaptive-wb-max", type=float, default=6500.0)
    parser.add_argument("--adaptive-focus-min", type=float, default=0.0)
    parser.add_argument("--adaptive-focus-max", type=float, default=40.0)
    parser.add_argument(
        "--adaptive-log-metrics",
        action="store_true",
        help="Print adaptive image-quality metrics at runtime.",
    )


class AdaptiveCameraController:
    def __init__(
        self,
        args: argparse.Namespace,
        emit: Callable[[str], None],
    ) -> None:
        self._args = args
        self._emit = emit
        self._enabled = args.adaptive_mode != "off"
        self._hybrid_mode = args.adaptive_mode == "hybrid"
        self._roi_norm = _parse_roi(args.adaptive_roi)
        self._last_eval_monotonic = 0.0
        self._last_adjust_monotonic = 0.0
        self._focus_direction = 1.0
        self._bad_streak = 0
        self._latest_feedback: FeedbackSnapshot | None = None
        self._latest_metrics: QualityMetrics | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def latest_metrics(self) -> QualityMetrics | None:
        return self._latest_metrics

    def update_feedback(self, feedback_payload: dict) -> None:
        if not self._hybrid_mode:
            return

        self._latest_feedback = FeedbackSnapshot(
            timestamp_ms=int(feedback_payload.get("timestamp_ms", 0)),
            board_visible=bool(feedback_payload.get("board_visible", False)),
            board_confidence=float(feedback_payload.get("board_confidence", 0.0)),
            corners_detected=int(feedback_payload.get("corners_detected", 0)),
            object_confidence=float(feedback_payload.get("object_confidence", 0.0)),
            mean_luma=float(feedback_payload.get("mean_luma", 0.0)),
            overexposed_ratio=float(feedback_payload.get("overexposed_ratio", 0.0)),
            sharpness=float(feedback_payload.get("sharpness", 0.0)),
            requested_mode=str(feedback_payload.get("requested_mode", "normal")),
        )

    def process_frame(self, capture, cv2_module, frame) -> QualityMetrics | None:
        if not self._enabled:
            return None

        now = time.monotonic()
        if now - self._last_eval_monotonic < self._args.adaptive_eval_interval_sec:
            return self._latest_metrics

        self._last_eval_monotonic = now
        metrics = compute_quality_metrics(
            frame,
            self._roi_norm,
            cv2_module,
            overexposed_threshold=self._args.adaptive_overexposed_threshold,
        )
        self._latest_metrics = metrics

        if self._args.adaptive_log_metrics:
            self._emit(_format_metrics(metrics))

        if now - self._last_adjust_monotonic < self._args.adaptive_cooldown_sec:
            return metrics

        poor_image = self._is_poor_image(metrics)
        if poor_image:
            self._bad_streak += 1
        else:
            self._bad_streak = 0

        if self._bad_streak < 2 and not self._should_force_recovery(metrics):
            return metrics

        if self._apply_brightness_adjustment(capture, cv2_module, metrics, now):
            self._bad_streak = 0
            return metrics

        if self._apply_color_adjustment(capture, cv2_module, metrics, now):
            self._bad_streak = 0
            return metrics

        if self._should_try_focus(metrics):
            if self._apply_focus_adjustment(capture, cv2_module, metrics, now):
                self._bad_streak = 0

        return metrics

    def _is_poor_image(self, metrics: QualityMetrics) -> bool:
        too_dark = metrics.mean_luma < self._args.adaptive_target_luma - self._args.adaptive_luma_tolerance
        too_bright = metrics.mean_luma > self._args.adaptive_target_luma + self._args.adaptive_luma_tolerance
        clipped = metrics.overexposed_ratio > self._args.adaptive_max_overexposed_ratio
        blurry = metrics.sharpness < self._args.adaptive_min_sharpness
        color_cast = metrics.color_cast > self._args.adaptive_color_cast_threshold
        return too_dark or too_bright or clipped or blurry or color_cast

    def _should_force_recovery(self, metrics: QualityMetrics) -> bool:
        if metrics.overexposed_ratio > self._args.adaptive_max_overexposed_ratio * 2.0:
            return True
        if self._hybrid_mode and self._task_quality_bad():
            return True
        return False

    def _task_quality_bad(self) -> bool:
        feedback = self._latest_feedback
        if feedback is None:
            return False

        age_sec = max(0.0, time.time() - feedback.timestamp_ms / 1000.0)
        if age_sec > self._args.adaptive_feedback_freshness_sec:
            return False

        if feedback.requested_mode.lower() in {"recover", "refocus", "brighten"}:
            return True

        if not feedback.board_visible:
            return True
        if feedback.board_confidence < self._args.adaptive_min_board_confidence:
            return True
        if feedback.corners_detected < self._args.adaptive_min_corners:
            return True
        if feedback.object_confidence < self._args.adaptive_min_object_confidence:
            return True
        return False

    def _apply_brightness_adjustment(self, capture, cv2_module, metrics: QualityMetrics, now: float) -> bool:
        multiplier = 2.0 if self._hybrid_mode and self._task_quality_bad() else 1.0
        if metrics.overexposed_ratio > self._args.adaptive_max_overexposed_ratio:
            if self._step_control(
                capture,
                cv2_module,
                "exposure",
                -self._args.adaptive_exposure_step * multiplier,
                self._args.adaptive_exposure_min,
                self._args.adaptive_exposure_max,
                reason=f"overexposed ratio {metrics.overexposed_ratio:.3f}",
            ):
                self._last_adjust_monotonic = now
                return True
            if self._step_control(
                capture,
                cv2_module,
                "gain",
                -self._args.adaptive_gain_step * multiplier,
                self._args.adaptive_gain_min,
                self._args.adaptive_gain_max,
                reason=f"overexposed ratio {metrics.overexposed_ratio:.3f}",
            ):
                self._last_adjust_monotonic = now
                return True

        target_low = self._args.adaptive_target_luma - self._args.adaptive_luma_tolerance
        target_high = self._args.adaptive_target_luma + self._args.adaptive_luma_tolerance
        if metrics.mean_luma < target_low:
            if self._step_control(
                capture,
                cv2_module,
                "exposure",
                self._args.adaptive_exposure_step * multiplier,
                self._args.adaptive_exposure_min,
                self._args.adaptive_exposure_max,
                reason=f"mean luma {metrics.mean_luma:.1f} below target",
            ):
                self._last_adjust_monotonic = now
                return True
            if self._step_control(
                capture,
                cv2_module,
                "gain",
                self._args.adaptive_gain_step * multiplier,
                self._args.adaptive_gain_min,
                self._args.adaptive_gain_max,
                reason=f"mean luma {metrics.mean_luma:.1f} below target",
            ):
                self._last_adjust_monotonic = now
                return True
            return False

        if metrics.mean_luma > target_high:
            if self._step_control(
                capture,
                cv2_module,
                "exposure",
                -self._args.adaptive_exposure_step * multiplier,
                self._args.adaptive_exposure_min,
                self._args.adaptive_exposure_max,
                reason=f"mean luma {metrics.mean_luma:.1f} above target",
            ):
                self._last_adjust_monotonic = now
                return True
            if self._step_control(
                capture,
                cv2_module,
                "gain",
                -self._args.adaptive_gain_step * multiplier,
                self._args.adaptive_gain_min,
                self._args.adaptive_gain_max,
                reason=f"mean luma {metrics.mean_luma:.1f} above target",
            ):
                self._last_adjust_monotonic = now
                return True
        return False

    def _apply_color_adjustment(self, capture, cv2_module, metrics: QualityMetrics, now: float) -> bool:
        if metrics.color_cast <= self._args.adaptive_color_cast_threshold:
            return False

        wb_value = get_camera_control_value(capture, cv2_module, "wb_temperature")
        if wb_value is None:
            return False

        if metrics.mean_b > metrics.mean_r:
            delta = -self._args.adaptive_wb_step
            note = "image skewed blue, warming slightly"
        else:
            delta = self._args.adaptive_wb_step
            note = "image skewed red, cooling slightly"

        if self._step_control(
            capture,
            cv2_module,
            "wb_temperature",
            delta,
            self._args.adaptive_wb_min,
            self._args.adaptive_wb_max,
            reason=note,
        ):
            self._last_adjust_monotonic = now
            return True
        return False

    def _should_try_focus(self, metrics: QualityMetrics) -> bool:
        if metrics.sharpness >= self._args.adaptive_min_sharpness:
            return False
        if not self._hybrid_mode:
            return False
        return self._task_quality_bad()

    def _apply_focus_adjustment(self, capture, cv2_module, metrics: QualityMetrics, now: float) -> bool:
        delta = self._focus_direction * self._args.adaptive_focus_step
        if self._step_control(
            capture,
            cv2_module,
            "focus",
            delta,
            self._args.adaptive_focus_min,
            self._args.adaptive_focus_max,
            reason=f"sharpness {metrics.sharpness:.1f} below target",
        ):
            self._last_adjust_monotonic = now
            return True

        self._focus_direction *= -1.0
        if self._step_control(
            capture,
            cv2_module,
            "focus",
            self._focus_direction * self._args.adaptive_focus_step,
            self._args.adaptive_focus_min,
            self._args.adaptive_focus_max,
            reason=f"sharpness {metrics.sharpness:.1f} below target",
        ):
            self._last_adjust_monotonic = now
            return True
        return False

    def _step_control(
        self,
        capture,
        cv2_module,
        control_name: str,
        delta: float,
        minimum: float,
        maximum: float,
        reason: str,
    ) -> bool:
        current = get_camera_control_value(capture, cv2_module, control_name)
        if current is None:
            return False

        target = min(max(current + delta, minimum), maximum)
        if abs(target - current) < 1e-6:
            return False

        ok, readback, error_text = set_camera_control(capture, cv2_module, control_name, target)
        readback_text = "n/a" if readback is None else f"{readback:.3f}"
        message = (
            "Adaptive camera control | "
            f"{control_name} current={current:.3f} target={target:.3f} "
            f"readback={readback_text} ok={ok} reason={reason}"
        )
        if error_text:
            message += f" error={error_text}"
        self._emit(message)

        if control_name == "focus" and ok:
            if readback is not None and (readback <= minimum + 1e-6 or readback >= maximum - 1e-6):
                self._focus_direction *= -1.0
        return ok


def compute_quality_metrics(
    frame,
    roi_norm: tuple[float, float, float, float],
    cv2_module,
    overexposed_threshold: float,
) -> QualityMetrics:
    height, width = frame.shape[:2]
    x0 = int(round(roi_norm[0] * width))
    y0 = int(round(roi_norm[1] * height))
    x1 = int(round((roi_norm[0] + roi_norm[2]) * width))
    y1 = int(round((roi_norm[1] + roi_norm[3]) * height))
    x0 = max(0, min(x0, width - 1))
    y0 = max(0, min(y0, height - 1))
    x1 = max(x0 + 1, min(x1, width))
    y1 = max(y0 + 1, min(y1, height))

    roi = frame[y0:y1, x0:x1]
    gray = cv2_module.cvtColor(roi, cv2_module.COLOR_BGR2GRAY)
    gray_f = gray.astype(np.float32)
    channels = roi.astype(np.float32)
    mean_b, mean_g, mean_r = channels.reshape(-1, 3).mean(axis=0)
    mean_rgb = (mean_b + mean_g + mean_r) / 3.0
    lap = cv2_module.Laplacian(gray, cv2_module.CV_32F)

    return QualityMetrics(
        mean_luma=float(gray_f.mean()),
        overexposed_ratio=float((gray_f >= float(overexposed_threshold)).mean()),
        contrast_span=float(np.percentile(gray_f, 95.0) - np.percentile(gray_f, 5.0)),
        sharpness=float(lap.var()),
        color_cast=float(max(abs(mean_b - mean_rgb), abs(mean_g - mean_rgb), abs(mean_r - mean_rgb))),
        mean_b=float(mean_b),
        mean_g=float(mean_g),
        mean_r=float(mean_r),
        roi_bounds_px=(x0, y0, x1, y1),
    )


def _parse_roi(text: str) -> tuple[float, float, float, float]:
    try:
        x, y, w, h = [float(part.strip()) for part in text.split(",")]
    except Exception as exc:  # pragma: no cover - validated on startup
        raise ValueError(
            "adaptive ROI must be a comma-separated x,y,w,h tuple in normalized coordinates"
        ) from exc

    for value in (x, y, w, h):
        if value < 0.0 or value > 1.0:
            raise ValueError("adaptive ROI values must stay in the [0, 1] range")
    if w <= 0.0 or h <= 0.0:
        raise ValueError("adaptive ROI width/height must be positive")
    if x + w > 1.0 or y + h > 1.0:
        raise ValueError("adaptive ROI must stay inside the image bounds")
    return x, y, w, h


def _format_metrics(metrics: QualityMetrics) -> str:
    x0, y0, x1, y1 = metrics.roi_bounds_px
    return (
        "Adaptive metrics | "
        f"roi=({x0},{y0})-({x1},{y1}) "
        f"luma={metrics.mean_luma:.1f} "
        f"over={metrics.overexposed_ratio:.3f} "
        f"contrast={metrics.contrast_span:.1f} "
        f"sharpness={metrics.sharpness:.1f} "
        f"cast={metrics.color_cast:.1f}"
    )
