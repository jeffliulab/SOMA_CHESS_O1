#!/usr/bin/env python3
"""Generate and merge W1.8 reachability validation results."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src" / "arm_perception"))

from arm_perception.calibration_artifacts import (  # noqa: E402
    CALIBRATION_DIR,
    load_yaml,
    save_yaml,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        default=str(CALIBRATION_DIR / "workspace.yaml"),
        help="Shared workspace calibration YAML.",
    )
    parser.add_argument(
        "--template-output",
        default=str(CALIBRATION_DIR / "reachability_results.yaml"),
        help="YAML file where the manual test checklist is written.",
    )
    parser.add_argument(
        "--apply-results",
        default="",
        help="Existing results YAML to merge back into workspace.yaml.",
    )
    parser.add_argument(
        "--default-trials-per-point",
        type=int,
        default=5,
        help="Expected number of trials per test point.",
    )
    parser.add_argument(
        "--failure-radius-m",
        type=float,
        default=0.025,
        help="Radius used when converting a failed point into a simple no-go square.",
    )
    return parser.parse_args()


def _point_id(index: int) -> str:
    return f"probe_{index + 1:02d}"


def _square_region(center_x: float, center_y: float, radius: float) -> list[list[float]]:
    return [
        [center_x - radius, center_y - radius],
        [center_x + radius, center_y - radius],
        [center_x + radius, center_y + radius],
        [center_x - radius, center_y + radius],
    ]


def main() -> int:
    args = _parse_args()
    workspace_path = Path(args.workspace).expanduser()
    workspace = load_yaml(workspace_path)
    if not workspace:
        raise SystemExit(f"workspace YAML not found or empty: {workspace_path}")

    points = workspace.get("reachable_test_points_xy_m") or []
    if not points:
        raise SystemExit(
            "workspace.yaml does not contain reachable_test_points_xy_m. Run solve_workspace_calibration.py first."
        )

    template_payload = {
        "status": "pending_manual_validation",
        "world_frame": str(workspace.get("world_frame", "roarm_base_link")),
        "default_trials_per_point": int(args.default_trials_per_point),
        "instructions": [
            "For each point, attempt the same approach 5 times with the real arm.",
            "Mark reached=true only if there was no collision, no obvious stall, and the target was consistently reachable.",
            "Add brief notes for edge cases such as cable drag, near-singularity, or container wall contact.",
        ],
        "points": [
            {
                "id": _point_id(index),
                "xy_m": [float(point[0]), float(point[1])],
                "trials": int(args.default_trials_per_point),
                "reached": None,
                "notes": "",
            }
            for index, point in enumerate(points)
        ],
    }

    template_path = Path(args.template_output).expanduser()
    save_yaml(template_path, template_payload)
    print(f"[reachability] wrote template {template_path}")

    if not args.apply_results:
        return 0

    results_path = Path(args.apply_results).expanduser()
    results = load_yaml(results_path)
    result_points = results.get("points") or []
    if not result_points:
        raise SystemExit(f"no point results found in {results_path}")

    successes = []
    failures = []
    merged_results = []
    for result in result_points:
        xy = result.get("xy_m") or [0.0, 0.0]
        reached = result.get("reached")
        point_record = {
            "id": str(result.get("id", "")),
            "xy_m": [float(xy[0]), float(xy[1])],
            "trials": int(result.get("trials", args.default_trials_per_point)),
            "reached": None if reached is None else bool(reached),
            "notes": str(result.get("notes", "")),
        }
        merged_results.append(point_record)
        if reached is True:
            successes.append(point_record["xy_m"])
        elif reached is False:
            failures.append(point_record["xy_m"])

    workspace["reachable_test_points_xy_m"] = [list(map(float, point)) for point in successes]
    workspace["validation_probe_points_xy_m"] = [
        list(map(float, point.get("xy_m", [0.0, 0.0]))) for point in merged_results
    ]
    workspace["reachability_results"] = merged_results
    workspace["no_go_regions_xy_m"] = [
        _square_region(float(point[0]), float(point[1]), float(args.failure_radius_m))
        for point in failures
    ]
    workspace["validation_summary"] = {
        "total_points": len(merged_results),
        "successful_points": len(successes),
        "failed_points": len(failures),
        "source_results_yaml": str(results_path.relative_to(REPO_ROOT)) if results_path.is_relative_to(REPO_ROOT) else str(results_path),
    }
    if failures:
        workspace["status"] = "geometry_calibrated_partial_reachability"
    else:
        workspace["status"] = "geometry_and_reachability_validated"

    save_yaml(workspace_path, workspace)
    print(f"[reachability] merged results into {workspace_path}")
    print(
        "  success_points="
        f"{len(successes)} failure_points={len(failures)} status={workspace['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
