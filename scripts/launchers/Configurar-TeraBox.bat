@echo off
setlocal
pushd "%~dp0..\.."
set "RDRIVE_RCLONE_EXE=%CD%\tools\rclone-extra\rclone.exe"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\configurar_terabox.ps1" %*
set "RC=%ERRORLEVEL%"
popd
pause
exit /b %RC%
