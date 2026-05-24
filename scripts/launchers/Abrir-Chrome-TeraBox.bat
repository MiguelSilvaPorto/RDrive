@echo off
setlocal EnableExtensions
pushd "%~dp0..\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\launch_terabox_chrome.ps1"
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" pause
exit /b %RC%
