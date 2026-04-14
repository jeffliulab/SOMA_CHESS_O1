@echo off
setlocal

set "ROARM_BUSID=1-8"

echo Listing current usbipd state...
usbipd list
echo.

call :ensure_attached "%ROARM_BUSID%" "RoArm serial bridge"
if errorlevel 1 goto :fail

echo.
echo Done.
echo In bridge fallback mode, keep the PDP controller on Windows.
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
echo usbipd attach failed. Check the busid value above with usbipd list.
pause
exit /b 1
