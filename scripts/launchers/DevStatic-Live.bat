@echo off
rem Desenvolvimento da UI em Static/ com recarregamento automatico no RDrive.
rem A pasta Static/ fica excluida do watchdog do projecto (menos ruido no feed).
setlocal
pushd "%~dp0..\.."
set "RDRIVE_STATIC_LIVE=1"
set "RDRIVE_STATIC_DIR=%CD%\Static"
set "RDRIVE_WEBUI=1"
set "RDRIVE_PROJECT_ROOT=%CD%"
echo [RDrive] Modo live: edite Static\ e guarde — a janela recarrega em ~0,4s.
call "%CD%\Iniciar.bat"
popd
