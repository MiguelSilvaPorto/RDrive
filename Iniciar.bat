@echo off
setlocal EnableExtensions EnableDelayedExpansion
if not defined RDRIVE_LAUNCHER_WRAPPED (
    set "RDRIVE_LAUNCHER_WRAPPED=1"
    pushd "%~dp0"
    powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0scripts\log_launcher.ps1" -BatPath "%~f0"
    set "RDRIVE_EXIT=!ERRORLEVEL!"
    popd
    if not defined RDRIVE_EXIT set "RDRIVE_EXIT=1"
    exit /b !RDRIVE_EXIT!
)
pushd "%~dp0"
set "RDRIVE_PROJECT_ROOT=%CD%"

rem WebUI (Static/) ativa por padrao. UI nativa PyQt: RDRIVE_WEBUI=0
rem Dev live reload: DevStatic-Live.bat (RDRIVE_STATIC_LIVE=1)
if not defined RDRIVE_WEBUI set "RDRIVE_WEBUI=1"
if not defined RDRIVE_STATIC_DIR set "RDRIVE_STATIC_DIR=%CD%\Static"

set "PYTHON_EXE="
set "VENV_PY=.venv\Scripts\python.exe"
set "VENV_PYW=.venv\Scripts\pythonw.exe"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
set "RCLONE_EXE="
set "RCLONE_DIR="

call :resolve_python_global
if not defined PYTHON_EXE (
    echo [RDrive] Python nao encontrado. Tentando instalar com winget...
    call :install_python_winget
    call :resolve_python_global
)

if not defined PYTHON_EXE (
    echo.
    echo [ERRO] Python 3 nao esta disponivel.
    echo [INFO] Instale manualmente o Python 3.11+ e execute novamente.
    echo [INFO] Link oficial: https://www.python.org/downloads/windows/
    goto :fail
)

call :ensure_rclone_ready
if errorlevel 1 goto :fail
echo [RDrive] rclone validado com sucesso.

call :ensure_winfsp_ready
rem WinFsp bootstrap is non-blocking — clear stale errorlevel from detect/winget helpers
ver >nul

if not exist "%VENV_PY%" (
    echo [RDrive] Criando ambiente virtual local...
    "%PYTHON_EXE%" -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Falha ao criar .venv
        goto :fail
    )
)

echo [RDrive] Atualizando pip...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERRO] Falha ao atualizar pip.
    goto :fail
)

echo [RDrive] Instalando dependencias...
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar requirements.txt.
    goto :fail
)

echo [RDrive] Verificando PyQt6-WebEngine...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\verify_webengine.ps1" -Quiet
if errorlevel 1 (
    echo [AVISO] PyQt6-WebEngine incompleto — navegador TeraBox integrado pode ficar em branco.
    echo [INFO] Repare com: scripts\verify_webengine.ps1
)

if exist "%CD%\tools\rclone-extra\rclone.exe" (
    set "RDRIVE_RCLONE_EXE=%CD%\tools\rclone-extra\rclone.exe"
    echo [RDrive] rclone TeraBox: %RDRIVE_RCLONE_EXE%
) else (
    set "RDRIVE_RCLONE_EXE="
)

echo [RDrive] Iniciando aplicativo...
echo [RDrive] PYTHONPATH=%PYTHONPATH%
if exist "%VENV_PYW%" (
    echo [RDrive] starting pythonw: %VENV_PYW%
    start "" "%VENV_PYW%" -m rdrive
) else (
    echo [ERRO] pythonw.exe nao encontrado em %VENV_PYW%
    echo [INFO] Recrie o ambiente virtual: "%VENV_PY%" -m venv .venv
    goto :fail
)

goto :success

:fail
echo.
echo [RDrive] Encerrado com falha. Detalhes em logs\launcher.log
if /I "%RDRIVE_LAUNCHER_DEBUG%"=="1" (
    pause
) else (
    echo [INFO] Defina RDrive_LAUNCHER_DEBUG=1 para manter esta janela aberta.
)
set "RDRIVE_LAUNCH_EXIT=1"
goto :launcher_exit

:success
set "RDRIVE_LAUNCH_EXIT=0"
goto :launcher_exit

goto :main_end

:validate_rclone_command
if not defined RCLONE_EXE goto :validate_rclone_generic
"%RCLONE_EXE%" version >nul 2>&1
goto :validate_rclone_check
:validate_rclone_generic
rclone version >nul 2>&1
:validate_rclone_check
if errorlevel 1 exit /b 1
exit /b 0

:resolve_python_global
set "PYTHON_EXE="
for /f "usebackq delims=" %%I in (`py -3 -c "import sys;print(sys.executable)" 2^>nul`) do set "PYTHON_EXE=%%I"
if defined PYTHON_EXE goto :eof
for /f "usebackq delims=" %%I in (`python -c "import sys;print(sys.executable)" 2^>nul`) do set "PYTHON_EXE=%%I"
if defined PYTHON_EXE goto :eof
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if defined PYTHON_EXE goto :eof
if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python311\python.exe"
goto :eof

:install_python_winget
where winget >nul 2>&1
if errorlevel 1 (
    echo [ERRO] winget nao encontrado nesta maquina.
    echo [INFO] Atualize/App Installer da Microsoft Store ou instale Python manualmente.
    goto :eof
)

set "WINGET_CLI=install --id Python.Python.3.12 -e --scope user --disable-interactivity --accept-package-agreements --accept-source-agreements"
set "WINGET_TIMEOUT_SEC=300"
call :run_winget_timed
if errorlevel 1 (
    echo [ERRO] Falha ao instalar Python com winget.
    echo [INFO] Tente manualmente: winget install --id Python.Python.3.12 -e --scope user
)
goto :eof

:resolve_rclone_global
set "RCLONE_EXE="
for /f "usebackq delims=" %%I in (`where rclone 2^>nul`) do (
    set "RCLONE_EXE=%%I"
    goto :eof
)
goto :eof

:install_rclone_winget
where winget >nul 2>&1
if errorlevel 1 (
    echo [AVISO] winget nao encontrado nesta maquina.
    echo [INFO] Instale o App Installer da Microsoft Store ou faca a instalacao manual do rclone.
    echo [INFO] Link oficial: https://rclone.org/downloads/
    goto :eof
)

set "RCLONE_INSTALL_OK="
call :try_install_rclone_winget_id "Rclone.Rclone"
if not errorlevel 1 set "RCLONE_INSTALL_OK=1"
if defined RCLONE_INSTALL_OK goto :install_rclone_winget_done
call :try_install_rclone_winget_id "rclone.rclone"
if not errorlevel 1 set "RCLONE_INSTALL_OK=1"
:install_rclone_winget_done

if not defined RCLONE_INSTALL_OK (
    echo [ERRO] Falha ao instalar rclone com winget.
    echo [INFO] Tente manualmente: winget install --id Rclone.Rclone -e --scope user
    echo [INFO] Link oficial: https://rclone.org/downloads/
)
goto :eof

:try_install_rclone_winget_id
set "RCLONE_WINGET_ID=%~1"
echo [RDrive] Tentando instalar rclone via winget (%RCLONE_WINGET_ID%)...
set "WINGET_CLI=install --id %RCLONE_WINGET_ID% -e --scope user --disable-interactivity --accept-package-agreements --accept-source-agreements"
set "WINGET_TIMEOUT_SEC=300"
call :run_winget_timed
if errorlevel 1 (
    echo [AVISO] winget falhou para id %RCLONE_WINGET_ID%.
    exit /b 1
)
exit /b 0

:ensure_rclone_ready
call :resolve_rclone_global
if defined RCLONE_EXE goto :ensure_rclone_after_resolve
echo [RDrive] rclone nao encontrado no PATH. Tentando instalar com winget...
call :install_rclone_winget
call :resolve_rclone_global

:ensure_rclone_after_resolve
if defined RCLONE_EXE goto :ensure_rclone_validate
echo [RDrive] Tentando localizar rclone.exe em caminhos comuns...
call :locate_rclone_candidate
if not defined RCLONE_EXE goto :ensure_rclone_validate
call :ensure_rclone_dir_in_path "%RCLONE_EXE%"

:ensure_rclone_validate
set "RCLONE_VALID=0"
call :validate_rclone_command
if not errorlevel 1 set "RCLONE_VALID=1"
if not "%RCLONE_VALID%"=="0" goto :ensure_rclone_success

echo [RDrive] rclone ainda nao responde no PATH. Tentando ajustar PATH automaticamente...
call :locate_rclone_candidate
if defined RCLONE_EXE call :ensure_rclone_dir_in_path "%RCLONE_EXE%"
call :validate_rclone_command
if not errorlevel 1 set "RCLONE_VALID=1"
if not "%RCLONE_VALID%"=="0" goto :ensure_rclone_success

echo.
echo [ERRO] rclone nao ficou disponivel no PATH apos instalacao/ajuste automatico.
echo [INFO] Instale manualmente e confirme no terminal: rclone version
echo [INFO] Comando sugerido: winget install --id Rclone.Rclone -e --scope user
echo [INFO] Link oficial: https://rclone.org/downloads/
exit /b 1

:ensure_rclone_success
call :resolve_rclone_global
if not defined RCLONE_EXE set "RCLONE_EXE=rclone"
echo [RDrive] rclone detectado em: %RCLONE_EXE%
exit /b 0

:locate_rclone_candidate
set "RCLONE_EXE="
if exist "%LocalAppData%\Microsoft\WinGet\Links\rclone.exe" set "RCLONE_EXE=%LocalAppData%\Microsoft\WinGet\Links\rclone.exe"
if defined RCLONE_EXE goto :eof
if exist "%LocalAppData%\Programs\rclone\rclone.exe" set "RCLONE_EXE=%LocalAppData%\Programs\rclone\rclone.exe"
if defined RCLONE_EXE goto :eof
if exist "%ProgramFiles%\rclone\rclone.exe" set "RCLONE_EXE=%ProgramFiles%\rclone\rclone.exe"
if defined RCLONE_EXE goto :eof
if exist "%UserProfile%\scoop\apps\rclone\current\rclone.exe" set "RCLONE_EXE=%UserProfile%\scoop\apps\rclone\current\rclone.exe"
if defined RCLONE_EXE goto :eof
for /d %%D in ("%LocalAppData%\Microsoft\WinGet\Packages\Rclone.Rclone_*") do (
    if exist "%%~fD\rclone.exe" (
        set "RCLONE_EXE=%%~fD\rclone.exe"
        goto :eof
    )
)
goto :eof

:ensure_rclone_dir_in_path
set "RCLONE_EXE_INPUT=%~1"
if not exist "%RCLONE_EXE_INPUT%" exit /b 1
for %%I in ("%RCLONE_EXE_INPUT%") do set "RCLONE_DIR=%%~dpI"
if "%RCLONE_DIR:~-1%"=="\" set "RCLONE_DIR=%RCLONE_DIR:~0,-1%"
if not defined RCLONE_DIR exit /b 1
call :ensure_session_path_contains "%RCLONE_DIR%"
call :ensure_user_path_contains "%RCLONE_DIR%"
exit /b 0

:detect_winfsp_installed
set "WINFSP_INSTALLED="
reg query "HKLM\SOFTWARE\WinFsp" >nul 2>&1
if not errorlevel 1 set "WINFSP_INSTALLED=1"
if defined WINFSP_INSTALLED goto :eof
reg query "HKLM\SOFTWARE\WOW6432Node\WinFsp" >nul 2>&1
if not errorlevel 1 set "WINFSP_INSTALLED=1"
if defined WINFSP_INSTALLED goto :eof
if exist "%ProgramFiles(x86)%\WinFsp\bin\winfsp-x64.dll" set "WINFSP_INSTALLED=1"
if defined WINFSP_INSTALLED goto :eof
if exist "%ProgramFiles%\WinFsp\bin\winfsp-x64.dll" set "WINFSP_INSTALLED=1"
if defined WINFSP_INSTALLED goto :eof
for /f "usebackq delims=" %%I in (`where winfsp-x64 2^>nul`) do (
    set "WINFSP_INSTALLED=1"
    goto :eof
)
sc query WinFsp.Launcher 2>nul | findstr /I "STATE" >nul
if not errorlevel 1 set "WINFSP_INSTALLED=1"
goto :eof

:install_winfsp_winget
where winget >nul 2>&1
if errorlevel 1 (
    echo [AVISO] winget nao encontrado nesta maquina.
    echo [INFO] Instale o WinFsp manualmente: https://winfsp.dev/rel/
    goto :eof
)

echo [RDrive] Tentando instalar WinFsp via winget (WinFsp.WinFsp)...
if /I "%RDRIVE_LAUNCHER_WRAPPED%"=="1" (
    echo [AVISO] Instalacao WinFsp via winget ignorada em launcher oculto ^(UAC nao aparece^).
    echo [INFO] Instale manualmente: winget install --id WinFsp.WinFsp -e
    echo [INFO] Link oficial: https://winfsp.dev/rel/
    goto :eof
)
set "WINGET_CLI=install --id WinFsp.WinFsp -e --disable-interactivity --accept-package-agreements --accept-source-agreements"
set "WINGET_TIMEOUT_SEC=120"
call :run_winget_timed
if errorlevel 1 (
    echo [AVISO] Falha ao instalar WinFsp com winget ^(nao bloqueia o arranque^).
    echo [INFO] Tente manualmente: winget install --id WinFsp.WinFsp -e
    echo [INFO] Link oficial: https://winfsp.dev/rel/
)
goto :eof

:ensure_winfsp_ready
call :detect_winfsp_installed
if defined WINFSP_INSTALLED (
    echo [RDrive] WinFsp detectado.
    exit /b 0
)

echo [RDrive] WinFsp nao encontrado. Tentando instalar com winget...
call :install_winfsp_winget
call :detect_winfsp_installed
if defined WINFSP_INSTALLED (
    echo [RDrive] WinFsp instalado e detectado com sucesso.
    exit /b 0
)

echo [AVISO] WinFsp ainda nao esta disponivel apos tentativa automatica.
echo [INFO] O rclone mount no Windows precisa do WinFsp para montar unidades.
echo [INFO] Instale manualmente: winget install --id WinFsp.WinFsp -e
echo [INFO] Link oficial: https://winfsp.dev/rel/
echo [INFO] O RDrive vai iniciar; montagens serao bloqueadas ate instalar o WinFsp.
exit /b 0

:run_winget_timed
rem Requires WINGET_CLI and optional WINGET_TIMEOUT_SEC (default 180). Returns 99 on timeout.
if not defined WINGET_CLI exit /b 1
if not defined WINGET_TIMEOUT_SEC set "WINGET_TIMEOUT_SEC=180"
echo [RDrive] winget ^(%WINGET_TIMEOUT_SEC%s timeout^): %WINGET_CLI%
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$cli=$env:WINGET_CLI; $sec=[int]$env:WINGET_TIMEOUT_SEC; $psi=New-Object System.Diagnostics.ProcessStartInfo; $psi.FileName='winget'; $psi.Arguments=$cli; $psi.UseShellExecute=$false; $psi.RedirectStandardOutput=$true; $psi.RedirectStandardError=$true; $psi.CreateNoWindow=$true; $p=[Diagnostics.Process]::Start($psi); $exited=$p.WaitForExit($sec*1000); if(-not $exited){ try{$p.Kill()}catch{}; Write-Host ('[AVISO] winget timeout apos ' + $sec + 's'); exit 99 }; $out=$p.StandardOutput.ReadToEnd(); $err=$p.StandardError.ReadToEnd(); if($out){ Write-Host $out.TrimEnd() }; if($err){ Write-Host $err.TrimEnd() }; exit $p.ExitCode"
set "WINGET_RC=%ERRORLEVEL%"
exit /b %WINGET_RC%

:ensure_session_path_contains
set "TARGET_DIR=%~1"
if not defined TARGET_DIR exit /b 1
echo ;%PATH%; | findstr /I /C:";%TARGET_DIR%;" >nul
if errorlevel 1 (
    set "PATH=%TARGET_DIR%;%PATH%"
    echo [RDrive] PATH da sessao atualizado com: %TARGET_DIR%
)
exit /b 0

:ensure_user_path_contains
set "TARGET_DIR=%~1"
if not defined TARGET_DIR exit /b 1
set "TARGET_DIR_ESC=%TARGET_DIR:'=''%"
set "PATH_UPDATE_STATUS="
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\ensure_user_path.ps1" -TargetDir "%TARGET_DIR_ESC%"`) do (
    set "PATH_UPDATE_STATUS=%%I"
)
if /I "%PATH_UPDATE_STATUS%"=="ADDED" (
    echo [RDrive] PATH do usuario persistido com: %TARGET_DIR%
) else if /I "%PATH_UPDATE_STATUS%"=="EXISTS" (
    echo [RDrive] PATH do usuario ja continha: %TARGET_DIR%
) else (
    echo [AVISO] Nao foi possivel confirmar atualizacao persistente do PATH do usuario.
)
exit /b 0

:launcher_exit
popd
endlocal & set "RDRIVE_LAUNCH_EXIT=%RDRIVE_LAUNCH_EXIT%"
if "%RDRIVE_LAUNCH_EXIT%"=="1" exit /b 1
exit /b 0

:main_end
