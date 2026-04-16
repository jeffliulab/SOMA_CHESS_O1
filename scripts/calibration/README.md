## Week 1 Calibration Workflow

These scripts turn `config/calibration/` from placeholders into shared geometry artifacts for `W1.6` and `W1.8`.

Recommended order:

1. Capture a folder of ChArUco frames from `/camera/image_raw`.
2. Run `calibrate_camera_charuco.py` to write `camera_intrinsics.yaml`.
3. Capture one clean reference image with the board fully visible.
4. Run `solve_workspace_calibration.py` to write:
   - `eye_to_hand.yaml`
   - `workspace.yaml`
5. Run `validate_workspace_reachability.py` to create a manual W1.8 checklist.
6. After real-arm probing, edit the results YAML and rerun the same script with `--apply-results`.

All scripts are meant to be run from a shell that already sourced the repo `.venv` and ROS overlay.
