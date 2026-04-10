@echo off
:: Gamepad bridge launcher — captures stderr, auto-restarts on crash.
:: Run this instead of running bridge方案\gamepad_bridge.py directly.

set SCRIPT=\\wsl$\Ubuntu-22.04\home\jeffliu\SOMA\SOMA_CHESS_O1\scripts\bridge方案\gamepad_bridge.py
set ERRLOG=%TEMP%\gamepad_bridge_stderr.log

echo ============================================================
echo  Gamepad Bridge Launcher
echo  Log: %ERRLOG%
echo  Ctrl+C to stop
echo ============================================================

:loop
echo [%time%] Starting bridge...
python %SCRIPT% 2>>%ERRLOG%
set CODE=%ERRORLEVEL%
echo [%time%] Bridge exited (code %CODE%).
if %CODE% equ 0 goto done
echo [%time%] Crash detected — check %ERRLOG%
echo [%time%] Restarting in 3 seconds...
timeout /t 3 /nobreak > nul
goto loop

:done
echo [%time%] Normal exit. Press any key to close.
pause > nul
