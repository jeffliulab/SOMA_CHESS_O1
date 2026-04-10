@echo off
REM ================================================================
REM SOMA Chess O1 - Windows bridge fallback attach via usbipd-win
REM
REM Use this only when you intentionally keep the PDP Xbox controller on
REM Windows and run scripts\bridge方案\bridge_gui.py. In this mode, only the RoArm
REM (and optionally the C922 camera) are attached to WSL.
REM ================================================================

set ROARM_BUSID=1-4
set C922_BUSID=

echo Listing current usbipd state:
usbipd list
echo.

echo Attaching RoArm-M2-S (busid=%ROARM_BUSID%) to WSL...
usbipd attach --wsl --busid %ROARM_BUSID%

if not "%C922_BUSID%"=="" (
echo Attaching Logitech C922 (busid=%C922_BUSID%) to WSL...
usbipd attach --wsl --busid %C922_BUSID%
)

echo.
echo Done. In bridge fallback mode, keep the PDP controller on Windows and
echo launch scripts\bridge方案\bridge_gui.py there.
echo.
pause
