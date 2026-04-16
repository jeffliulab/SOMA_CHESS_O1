@echo off
setlocal

REM ================================================================
REM SOMA Arm - Windows camera bridge sender
REM
REM Keep the C922 on native Windows, capture there, and send frames over
REM TCP to the WSL ROS 2 receiver.
REM ================================================================

pushd "%~dp0"
if errorlevel 1 (
  echo ERROR: Failed to enter the script directory:
  echo   %~dp0
  exit /b 1
)

set "SCRIPT=%CD%\windows_camera_bridge.py"
set "PYTHON_EXE="

if defined SOMA_WINDOWS_BRIDGE_PYTHON (
  if exist "%SOMA_WINDOWS_BRIDGE_PYTHON%" (
    set "PYTHON_EXE=%SOMA_WINDOWS_BRIDGE_PYTHON%"
  )
)

if not defined PYTHON_EXE (
  if exist "%LOCALAPPDATA%\SOMA\windows_envs\camera_bridge\Scripts\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\SOMA\windows_envs\camera_bridge\Scripts\python.exe"
  )
)

if not defined PYTHON_EXE (
  set "PYTHON_EXE=py"
)

echo ============================================================
echo  Windows Camera Bridge
echo  Script=%SCRIPT%
echo  Python=%PYTHON_EXE%
echo ============================================================
echo.

"%PYTHON_EXE%" "%SCRIPT%" %*
set "CODE=%ERRORLEVEL%"
popd
exit /b %CODE%
