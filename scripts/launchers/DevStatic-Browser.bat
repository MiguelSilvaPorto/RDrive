@echo off
rem Preview rapido no browser (sem PyQt, sem watchdog, sem bridge).
rem Ideal para CSS/HTML; use scripts\launchers\DevStatic-Live.bat para QWebChannel.
setlocal
pushd "%~dp0..\.."
set "RDRIVE_STATIC_DIR=%CD%\Static"
if not defined RDRIVE_WEBUI set "RDRIVE_WEBUI=1"
if exist ".venv\Scripts\python.exe" (
  set "PY_EXE=.venv\Scripts\python.exe"
) else (
  set "PY_EXE=python"
)
"%PY_EXE%" "%~dp0..\..\dev\sync_static_providers.py"
if errorlevel 1 (
  echo [RDrive] Aviso: falha ao sincronizar providers — icons podem faltar.
)
pushd "%CD%\Static"
set "PORT=8765"
echo [RDrive] Browser: http://127.0.0.1:%PORT%/
start "" "http://127.0.0.1:%PORT%/"
"%PY_EXE%" -m http.server %PORT%
popd
popd
