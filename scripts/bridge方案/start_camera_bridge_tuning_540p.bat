@echo off
setlocal

call "%~dp0start_camera_bridge.bat" ^
  --device-index 1 ^
  --backend dshow ^
  --width 960 ^
  --height 540 ^
  --jpeg-quality 70 ^
  --drop-stale-grabs 4 ^
  --camera-profile c922_freeze_auto ^
  --show-settings-dialog ^
  --log-camera-controls ^
  %*

exit /b %ERRORLEVEL%
