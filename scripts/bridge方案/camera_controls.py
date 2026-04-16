#!/usr/bin/env python3
"""Shared camera-control helpers for Windows-native camera workflows."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class CameraControlSpec:
    arg_name: str
    prop_attr: str
    label: str


CONTROL_SPECS = {
    "brightness": CameraControlSpec("brightness", "CAP_PROP_BRIGHTNESS", "brightness"),
    "contrast": CameraControlSpec("contrast", "CAP_PROP_CONTRAST", "contrast"),
    "saturation": CameraControlSpec("saturation", "CAP_PROP_SATURATION", "saturation"),
    "sharpness": CameraControlSpec("sharpness", "CAP_PROP_SHARPNESS", "sharpness"),
    "gain": CameraControlSpec("gain", "CAP_PROP_GAIN", "gain"),
    "auto_wb": CameraControlSpec("auto_wb", "CAP_PROP_AUTO_WB", "auto_wb"),
    "wb_temperature": CameraControlSpec(
        "wb_temperature", "CAP_PROP_WB_TEMPERATURE", "wb_temperature"
    ),
    "auto_exposure": CameraControlSpec(
        "auto_exposure", "CAP_PROP_AUTO_EXPOSURE", "auto_exposure"
    ),
    "exposure": CameraControlSpec("exposure", "CAP_PROP_EXPOSURE", "exposure"),
    "autofocus": CameraControlSpec("autofocus", "CAP_PROP_AUTOFOCUS", "autofocus"),
    "focus": CameraControlSpec("focus", "CAP_PROP_FOCUS", "focus"),
}

CONTROL_LOG_ORDER = (
    "brightness",
    "contrast",
    "saturation",
    "sharpness",
    "gain",
    "auto_wb",
    "wb_temperature",
    "auto_exposure",
    "exposure",
    "autofocus",
    "focus",
)

CAMERA_PROFILE_CHOICES = ("none", "c922_freeze_auto")


def add_camera_control_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--camera-profile",
        choices=CAMERA_PROFILE_CHOICES,
        default="none",
        help=(
            "Optional Windows-side camera-control profile. "
            "'c922_freeze_auto' is the W1.4 starting point for C922."
        ),
    )
    parser.add_argument(
        "--show-settings-dialog",
        action="store_true",
        help=(
            "Open the native DirectShow camera settings dialog after startup. "
            "Useful for the one-time W1.4 manual tuning pass."
        ),
    )
    parser.add_argument(
        "--log-camera-controls",
        action="store_true",
        help="Print current camera-control readback after opening the camera.",
    )

    for option in ("brightness", "contrast", "saturation", "sharpness", "gain"):
        parser.add_argument(f"--{option.replace('_', '-')}", type=float, default=None)

    parser.add_argument(
        "--auto-wb",
        choices=("on", "off"),
        default=None,
        help="Override OpenCV CAP_PROP_AUTO_WB.",
    )
    parser.add_argument(
        "--wb-temperature",
        type=float,
        default=None,
        help="Override OpenCV CAP_PROP_WB_TEMPERATURE.",
    )
    parser.add_argument(
        "--auto-exposure",
        choices=("auto", "manual"),
        default=None,
        help=(
            "Override OpenCV CAP_PROP_AUTO_EXPOSURE. "
            "The DSHOW mapping is used because that is the recommended W1.4 backend."
        ),
    )
    parser.add_argument(
        "--exposure",
        type=float,
        default=None,
        help="Raw OpenCV CAP_PROP_EXPOSURE override.",
    )
    parser.add_argument(
        "--autofocus",
        choices=("on", "off"),
        default=None,
        help="Override OpenCV CAP_PROP_AUTOFOCUS.",
    )
    parser.add_argument(
        "--focus",
        type=float,
        default=None,
        help="Raw OpenCV CAP_PROP_FOCUS override.",
    )


def apply_camera_controls(
    capture,
    cv2_module,
    args: argparse.Namespace,
    backend_label: str,
    emit: Callable[[str], None],
) -> None:
    requested_controls = _resolve_requested_controls(args, backend_label, emit)

    for control_name, value in requested_controls.items():
        spec = CONTROL_SPECS[control_name]
        prop_id = getattr(cv2_module, spec.prop_attr, None)
        if prop_id is None:
            emit(
                f"Camera control unavailable in this OpenCV build | {spec.label} "
                f"(missing {spec.prop_attr})"
            )
            continue

        ok = False
        error_text = ""
        try:
            ok = bool(capture.set(prop_id, float(value)))
        except Exception as exc:  # pragma: no cover - backend-dependent
            error_text = f" error={exc}"

        actual = _safe_get(capture, prop_id)
        emit(
            "Camera control | "
            f"{spec.label} requested={_format_value(value)} "
            f"set_ok={ok} readback={_format_value(actual)}{error_text}"
        )

    if getattr(args, "show_settings_dialog", False):
        _open_settings_dialog(capture, cv2_module, backend_label, emit)

    if requested_controls or getattr(args, "log_camera_controls", False):
        for line in camera_control_snapshot_lines(capture, cv2_module):
            emit(line)


def set_camera_control(
    capture,
    cv2_module,
    control_name: str,
    value: float,
) -> tuple[bool, float | None, str]:
    spec = CONTROL_SPECS.get(control_name)
    if spec is None:
        return False, None, f"unknown control '{control_name}'"

    prop_id = getattr(cv2_module, spec.prop_attr, None)
    if prop_id is None:
        return False, None, f"missing property {spec.prop_attr}"

    ok = False
    error_text = ""
    try:
        ok = bool(capture.set(prop_id, float(value)))
    except Exception as exc:  # pragma: no cover - backend-dependent
        error_text = str(exc)

    return ok, _safe_get(capture, prop_id), error_text


def get_camera_control_value(
    capture,
    cv2_module,
    control_name: str,
) -> float | None:
    spec = CONTROL_SPECS.get(control_name)
    if spec is None:
        return None

    prop_id = getattr(cv2_module, spec.prop_attr, None)
    if prop_id is None:
        return None

    return _safe_get(capture, prop_id)


def camera_control_snapshot_lines(capture, cv2_module) -> list[str]:
    lines = ["Camera control snapshot:"]
    for control_name in CONTROL_LOG_ORDER:
        spec = CONTROL_SPECS[control_name]
        prop_id = getattr(cv2_module, spec.prop_attr, None)
        if prop_id is None:
            lines.append(f"  - {spec.label}: unavailable")
            continue
        lines.append(
            f"  - {spec.label}: {_format_value(_safe_get(capture, prop_id))}"
        )
    return lines


def _resolve_requested_controls(
    args: argparse.Namespace,
    backend_label: str,
    emit: Callable[[str], None],
) -> dict[str, float]:
    controls: dict[str, float] = {}
    controls.update(_profile_controls(args.camera_profile, backend_label, emit))

    for option in ("brightness", "contrast", "saturation", "sharpness", "gain"):
        value = getattr(args, option, None)
        if value is not None:
            controls[option] = float(value)

    auto_wb = getattr(args, "auto_wb", None)
    if auto_wb is not None:
        controls["auto_wb"] = 1.0 if auto_wb == "on" else 0.0

    wb_temperature = getattr(args, "wb_temperature", None)
    if wb_temperature is not None:
        controls["wb_temperature"] = float(wb_temperature)

    auto_exposure = getattr(args, "auto_exposure", None)
    if auto_exposure is not None:
        mapped = _map_auto_exposure_mode(auto_exposure, backend_label, emit)
        if mapped is not None:
            controls["auto_exposure"] = mapped

    exposure = getattr(args, "exposure", None)
    if exposure is not None:
        controls["exposure"] = float(exposure)

    autofocus = getattr(args, "autofocus", None)
    if autofocus is not None:
        controls["autofocus"] = 1.0 if autofocus == "on" else 0.0

    focus = getattr(args, "focus", None)
    if focus is not None:
        controls["focus"] = float(focus)

    return controls


def _profile_controls(
    profile_name: str,
    backend_label: str,
    emit: Callable[[str], None],
) -> dict[str, float]:
    if profile_name == "none":
        return {}

    if profile_name == "c922_freeze_auto":
        controls: dict[str, float] = {
            "auto_wb": 0.0,
            "wb_temperature": 4000.0,
            "autofocus": 0.0,
        }
        mapped = _map_auto_exposure_mode("manual", backend_label, emit)
        if mapped is not None:
            controls["auto_exposure"] = mapped
        return controls

    emit(f"Unknown camera profile '{profile_name}', ignoring it.")
    return {}


def _map_auto_exposure_mode(
    mode: str,
    backend_label: str,
    emit: Callable[[str], None],
) -> float | None:
    backend = backend_label.upper()
    if backend == "DSHOW":
        # DirectShow uses 0.25=manual and 0.75=auto in OpenCV.
        return 0.75 if mode == "auto" else 0.25

    emit(
        "Camera control note | "
        f"backend={backend} has no tuned CAP_PROP_AUTO_EXPOSURE mapping yet, "
        f"so auto_exposure={mode} was skipped."
    )
    return None


def _open_settings_dialog(capture, cv2_module, backend_label: str, emit) -> None:
    prop_id = getattr(cv2_module, "CAP_PROP_SETTINGS", None)
    if prop_id is None:
        emit("Camera settings dialog is unavailable in this OpenCV build.")
        return

    if backend_label.upper() != "DSHOW":
        emit(
            "Camera settings dialog is primarily supported on DSHOW. "
            f"Current backend={backend_label}; skipping dialog request."
        )
        return

    try:
        capture.set(prop_id, 0.0)
    except Exception as exc:  # pragma: no cover - backend-dependent
        emit(f"Failed to request native camera settings dialog: {exc}")
        return

    emit(
        "Requested native DirectShow camera settings dialog. "
        "After you finish tuning exposure / white balance / focus, restart the sender "
        "once so the readback log reflects the final locked values."
    )


def _safe_get(capture, prop_id) -> float | None:
    try:
        return float(capture.get(prop_id))
    except Exception:  # pragma: no cover - backend-dependent
        return None


def _format_value(value: float | None) -> str:
    if value is None:
        return "n/a"
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.3f}"
