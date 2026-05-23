@echo off
setlocal
pushd "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0reset_vault.ps1" %*
set ERR=%ERRORLEVEL%
popd
exit /b %ERR%
