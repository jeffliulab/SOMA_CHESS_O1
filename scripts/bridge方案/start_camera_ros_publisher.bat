@echo off
setlocal

REM ================================================================
REM SOMA Arm - Windows native camera ROS publisher
REM
REM Recommended camera workflow after 2026-04-10:
REM   - keep the C922 on native Windows
REM   - run this launcher on Windows
REM   - keep subscribing from WSL over ROS 2 DDS
REM ================================================================

REM Map the UNC script directory to a temporary drive letter first.
pushd "%~dp0"
if errorlevel 1 (
  echo ERROR: Failed to enter the script directory:
  echo   %~dp0
  exit /b 1
)

set "ROS_SETUP="
if defined ROS_HUMBLE_ROOT (
  if exist "%ROS_HUMBLE_ROOT%\local_setup.bat" (
    set "ROS_SETUP=%ROS_HUMBLE_ROOT%\local_setup.bat"
  ) else if exist "%ROS_HUMBLE_ROOT%\install\local_setup.bat" (
    set "ROS_SETUP=%ROS_HUMBLE_ROOT%\install\local_setup.bat"
  )
)

if not defined ROS_SETUP (
  if exist "C:\dev\ros2_humble\local_setup.bat" (
    set "ROS_HUMBLE_ROOT=C:\dev\ros2_humble"
    set "ROS_SETUP=%ROS_HUMBLE_ROOT%\local_setup.bat"
  ) else if exist "C:\dev\ros2_humble\install\local_setup.bat" (
    set "ROS_HUMBLE_ROOT=C:\dev\ros2_humble"
    set "ROS_SETUP=%ROS_HUMBLE_ROOT%\install\local_setup.bat"
  ) else if exist "C:\ros2_humble\local_setup.bat" (
    set "ROS_HUMBLE_ROOT=C:\ros2_humble"
    set "ROS_SETUP=%ROS_HUMBLE_ROOT%\local_setup.bat"
  ) else if exist "C:\ros2_humble\install\local_setup.bat" (
    set "ROS_HUMBLE_ROOT=C:\ros2_humble"
    set "ROS_SETUP=%ROS_HUMBLE_ROOT%\install\local_setup.bat"
  ) else if exist "C:\opt\ros\humble\x64\local_setup.bat" (
    set "ROS_HUMBLE_ROOT=C:\opt\ros\humble\x64"
    set "ROS_SETUP=%ROS_HUMBLE_ROOT%\local_setup.bat"
  ) else if exist "C:\opt\ros\humble\x64\install\local_setup.bat" (
    set "ROS_HUMBLE_ROOT=C:\opt\ros\humble\x64"
    set "ROS_SETUP=%ROS_HUMBLE_ROOT%\install\local_setup.bat"
  )
)

if not exist "%ROS_SETUP%" (
  echo ERROR: Could not find ROS 2 setup file:
  echo   %ROS_SETUP%
  echo.
  echo Set ROS_HUMBLE_ROOT first, for example:
  echo   set ROS_HUMBLE_ROOT=C:\dev\ros2_humble
  echo Or point it at a source workspace root that contains install\local_setup.bat.
  popd
  exit /b 1
)

call "%ROS_SETUP%"
if errorlevel 1 (
  echo ERROR: Failed to source Windows ROS 2 environment.
  popd
  exit /b 1
)

if not defined ROS_DOMAIN_ID (
  set "ROS_DOMAIN_ID=0"
)
set "RMW_IMPLEMENTATION=rmw_fastrtps_cpp"
set "ROS_LOCALHOST_ONLY="

set "SCRIPT=%CD%\windows_camera_ros_publisher.py"

echo ============================================================
echo  Windows Camera ROS Publisher
echo  ROS_HUMBLE_ROOT=%ROS_HUMBLE_ROOT%
echo  ROS_DOMAIN_ID=%ROS_DOMAIN_ID%
echo  RMW_IMPLEMENTATION=%RMW_IMPLEMENTATION%
echo  Script=%SCRIPT%
echo ============================================================
echo.

py "%SCRIPT%" %*
set "CODE=%ERRORLEVEL%"
popd
exit /b %CODE%
