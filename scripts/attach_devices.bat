@echo off
setlocal

set "ROARM_BUSID=1-8"
set "PDP_BUSID=1-3"

echo Listing current usbipd state...
usbipd list
echo.

call :ensure_attached "%ROARM_BUSID%" "RoArm serial bridge"
if errorlevel 1 goto :fail

call :ensure_attached "%PDP_BUSID%" "PDP Xbox gamepad"
if errorlevel 1 goto :fail

echo.
echo Done.
echo In WSL you should now see /dev/ttyUSB* and /dev/input/event*
echo Launch teleop with:
echo   scripts/start_teleop_wsl_gamepad.sh
echo.
echo Keep Logitech C922 on native Windows.
pause
exit /b 0

:ensure_attached
set "BUSID=%~1"
set "LABEL=%~2"

usbipd list | findstr /R /C:"^%BUSID% .*Attached" >nul
if not errorlevel 1 (
    echo %LABEL% is already attached to WSL. busid=%BUSID%
    exit /b 0
)

echo Attaching %LABEL% to WSL. busid=%BUSID%
usbipd attach --wsl --busid %BUSID%
if errorlevel 1 exit /b 1
exit /b 0

:fail
echo.
echo usbipd attach failed. Check the busid values above with usbipd list.
pause
exit /b 1
