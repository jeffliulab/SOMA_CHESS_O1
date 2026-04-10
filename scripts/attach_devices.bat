@echo off
REM ================================================================
REM SOMA Chess O1 - WSL-direct USB attach via usbipd-win
REM
REM Run this in Windows PowerShell (as Administrator) every time you
REM reboot Windows. It attaches the RoArm-M2-S serial bridge and the
REM PDP Xbox gamepad directly into WSL so ROS 2 can see them as
REM /dev/ttyUSB* and /dev/input/event*.
REM
REM IMPORTANT:
REM   - This is the recommended long-term workflow.
REM   - Your WSL kernel must have EVDEV + JOYDEV + XPAD enabled, otherwise the
REM     controller may appear in lsusb but /dev/input/event0 may not show up.
REM   - While the controller is attached to WSL, Windows can no longer use it.
REM
REM First-time setup only (once per Windows install):
REM     usbipd list
REM     usbipd bind --busid <ROARM_BUSID>
REM     usbipd bind --busid <PDP_BUSID>
REM     usbipd bind --busid <C922_BUSID>   (optional)
REM
REM Every reboot:
REM     attach_devices.bat
REM ================================================================

REM === EDIT THESE TWO BUSIDs after the first `usbipd list` ===
set ROARM_BUSID=1-4
set PDP_BUSID=1-3
set C922_BUSID=
REM ===========================================================

echo Listing current usbipd state:
usbipd list
echo.

echo Attaching RoArm-M2-S (busid=%ROARM_BUSID%) to WSL...
usbipd attach --wsl --busid %ROARM_BUSID%

echo Attaching PDP Xbox gamepad (busid=%PDP_BUSID%) to WSL...
usbipd attach --wsl --busid %PDP_BUSID%

if not "%C922_BUSID%"=="" (
echo Attaching Logitech C922 (busid=%C922_BUSID%) to WSL...
usbipd attach --wsl --busid %C922_BUSID%
)

echo.
echo Done. Inside WSL you should now see:
echo   /dev/ttyUSB*      (RoArm-M2-S; current node may be ttyUSB0 or ttyUSB1)
echo   /dev/input/event0 (PDP Xbox gamepad; default teleop path)
echo   /dev/input/js0    (optional legacy joydev node)
if not "%C922_BUSID%"=="" echo   /dev/video0    (Logitech C922)
echo.
echo If /dev/input/event0 does not appear, verify your custom WSL kernel
echo enables CONFIG_INPUT_EVDEV and CONFIG_JOYSTICK_XPAD.
echo.
echo Preferred launch inside WSL:
echo   scripts/start_teleop_wsl_gamepad.sh
echo.
pause
