@echo off
setlocal EnableExtensions
pushd "%~dp0"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
set "RDRIVE_RCLONE_EXE=%CD%\tools\rclone-extra\rclone.exe"

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

echo [RDrive] A abrir navegador integrado TeraBox para capturar cookie...
echo Nao use F12 no site — o TeraBox bloqueia DevTools.
echo.
"%PY%" "%CD%\scripts\capture_terabox_cookie_gui.py"
set "RC=%ERRORLEVEL%"
popd
pause
exit /b %RC%
