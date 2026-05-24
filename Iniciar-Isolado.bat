@echo off
setlocal EnableExtensions
rem Teste com AppData limpo — nao usa %%LOCALAPPDATA%%\RDrive\ do PC.
rem Dados: pasta _isolated_test\ junto a esta release.
pushd "%~dp0"
if not defined RDRIVE_ISOLATED_ROOT set "RDRIVE_ISOLATED_ROOT=%~dp0_isolated_test"
set "RDRIVE_ISOLATED=1"
set "RDRIVE_LAUNCHER_VISIBLE=1"
set "RDRIVE_DATA_DIR=%RDRIVE_ISOLATED_ROOT%\RDrive"
set "LOCALAPPDATA=%RDRIVE_ISOLATED_ROOT%\LocalAppData"
set "APPDATA=%RDRIVE_ISOLATED_ROOT%\Roaming"
if not exist "%LOCALAPPDATA%" mkdir "%LOCALAPPDATA%" 2>nul
if not exist "%APPDATA%" mkdir "%APPDATA%" 2>nul
if not exist "%RDRIVE_DATA_DIR%" mkdir "%RDRIVE_DATA_DIR%" 2>nul
echo [RDrive] Modo isolado — dados em %RDRIVE_ISOLATED_ROOT%
echo [RDrive] RDRIVE_DATA_DIR=%RDRIVE_DATA_DIR%
call "%~dp0Iniciar.bat" %*
set "ISOL_EXIT=%ERRORLEVEL%"
popd
endlocal & exit /b %ISOL_EXIT%
