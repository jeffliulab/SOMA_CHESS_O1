# Calibration Config

This directory is the shared home for calibration and workspace geometry artifacts.

Files in this folder are intended to become the single source of truth for:

- camera intrinsics consumed by `/camera/camera_info`
- eye-to-hand extrinsics consumed by perception and motion planning
- workspace geometry and reachability masks shared by perception, primitives, and validators

Current convention:

- `camera_intrinsics.yaml`: camera matrix and distortion coefficients for the Windows bridge workflow
- `eye_to_hand.yaml`: transform from camera optical frame to robot/world frame
- `workspace.yaml`: tabletop polygon, bin region, reachable anchors, and no-go zones

Status:

- The files are checked in now so `V1.01` has a stable path convention.
- They are placeholders until `W1.6` and `W1.8` are completed on the real workstation.
