@echo off
setlocal
pushd "%~dp0..\.."
set "RDRIVE_RCLONE_EXE=%CD%\tools\rclone-extra\rclone.exe"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\terabox\mount_terabox.ps1" %*
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" pause
exit /b %RC%
