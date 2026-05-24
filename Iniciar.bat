@echo off
setlocal EnableExtensions EnableDelayedExpansion
if not defined RDRIVE_LAUNCHER_WRAPPED (
    rem Double-click: delegate to log_launcher.ps1 without blocking this console
    rem (avoids two visible cmd windows — bootstrap console is owned by log_launcher).
    pushd "%~dp0"
    start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0scripts\maintenance\log_launcher.ps1" -BatPath "%~f0"
    popd
    exit /b 0
)
pushd "%~dp0"
set "RDRIVE_PROJECT_ROOT=%CD%"

rem UI por defeito: CustomTkinter (ver src\rdrive\ui\ctk).
rem RDRIVE_UI=ctk | web (Static/HTML legado) | native (PyQt antigo, RDRIVE_WEBUI=0)
rem WebUI legado (Static/) controlado por RDRIVE_WEBUI quando RDRIVE_UI=web.
rem Dev live reload da WebUI legado: scripts\launchers\DevStatic-Live.bat (RDRIVE_STATIC_LIVE=1)
rem WebEngine GPU (opcional): RDRIVE_WEBENGINE_GPU=1 | legado sem GPU: RDRIVE_WEBENGINE_DISABLE_GPU=1
rem Diagnostico timers: RDRIVE_PERF_DEBUG=1
if not defined RDRIVE_UI set "RDRIVE_UI=ctk"
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

call :ensure_edge_ready
rem Edge bootstrap is non-blocking — TeraBox/OAuth isolado usa exclusivamente Edge
ver >nul

if not exist "%VENV_PY%" (
    echo [RDrive] Criando ambiente virtual local...
    "%PYTHON_EXE%" -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Falha ao criar .venv
        goto :fail
    )
)

call :ensure_venv_pip_ready
if errorlevel 1 goto :fail

rem ── Smart pip skip ────────────────────────────────────────────────────
rem  Calcula hash de requirements.txt e compara com stamp em .venv\.pip-stamp.
rem  Pula `pip install` quando o hash bate (tipico 5-12s economizados por arranque).
rem  Force reinstall: defina RDRIVE_FORCE_PIP=1 antes de Iniciar.bat.
set "PIP_STAMP=%CD%\.venv\.pip-stamp"
set "PIP_NEED_INSTALL=1"
set "REQ_HASH="
for /f "usebackq tokens=1 delims= " %%H in (`powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA1 '%CD%\requirements.txt').Hash"`) do set "REQ_HASH=%%H"
if /I "%RDRIVE_FORCE_PIP%"=="1" goto :pip_install_block
if not defined REQ_HASH goto :pip_install_block
if not exist "%PIP_STAMP%" goto :pip_install_block
set "STAMP_HASH="
for /f "usebackq delims=" %%L in ("%PIP_STAMP%") do (
    if not defined STAMP_HASH set "STAMP_HASH=%%L"
)
if /I "%STAMP_HASH%"=="%REQ_HASH%" (
    set "PIP_NEED_INSTALL=0"
    echo [RDrive] Dependencias ja sincronizadas ^(hash requirements.txt^).
)

:pip_install_block
if "%PIP_NEED_INSTALL%"=="1" (
    echo [RDrive] Atualizando pip...
    "%VENV_PY%" -m pip install --upgrade pip --quiet --disable-pip-version-check
    if errorlevel 1 (
        echo [ERRO] Falha ao atualizar pip.
        goto :fail
    )
    echo [RDrive] Instalando dependencias...
    "%VENV_PY%" -m pip install -r requirements.txt --disable-pip-version-check
    if errorlevel 1 (
        echo [ERRO] Falha ao instalar requirements.txt.
        goto :fail
    )
    if defined REQ_HASH (
        > "%PIP_STAMP%" echo %REQ_HASH%
    )
)

rem Instala o pacote rdrive em editable (além de PYTHONPATH) — necessário em zip de release.
echo [RDrive] A sincronizar pacote rdrive ^(pip install -e .^)...
"%VENV_PY%" -m pip install -e . --disable-pip-version-check --quiet
if errorlevel 1 (
    echo [ERRO] Falha ao instalar o pacote rdrive ^(pip install -e .^).
    goto :fail
)

rem ── Playwright (Edge / channel=msedge) ─────────────────────────────────
rem  Necessario para «Ligar conta TeraBox» e OAuth no browser isolado.
rem  Usa Microsoft Edge do sistema (channel=msedge) — nao instala Chrome.
rem  Force: RDRIVE_FORCE_PLAYWRIGHT_INSTALL=1
set "PLAYWRIGHT_STAMP=%CD%\.venv\.playwright-stamp"
set "PLAYWRIGHT_NEED_INSTALL=0"
if /I "%RDRIVE_FORCE_PLAYWRIGHT_INSTALL%"=="1" set "PLAYWRIGHT_NEED_INSTALL=1"
if "%PIP_NEED_INSTALL%"=="1" set "PLAYWRIGHT_NEED_INSTALL=1"
if not exist "%PLAYWRIGHT_STAMP%" set "PLAYWRIGHT_NEED_INSTALL=1"
if "%PLAYWRIGHT_NEED_INSTALL%"=="1" (
    echo [RDrive] Playwright — a verificar Edge para TeraBox/OAuth...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap\bootstrap_playwright.ps1" -Quiet
    if errorlevel 1 (
        echo [AVISO] Playwright/Edge incompleto — «Ligar conta TeraBox» pode falhar.
        echo [INFO] Instale Edge: winget install --id Microsoft.Edge -e --scope user
    )
)

rem ── WebEngine verify cache ───────────────────────────────────────────
rem  verify_webengine.ps1 inicia uma QApplication (5-8s). Cacheamos o ultimo OK
rem  por 7 dias e quando o mtime de .venv\Lib\site-packages\PyQt6 nao mudou.
rem  Force re-check: defina RDRIVE_FORCE_WEBENGINE_VERIFY=1.
set "WEBENGINE_STAMP=%CD%\.venv\.webengine-stamp"
set "WEBENGINE_NEED_VERIFY=1"
if /I "%RDRIVE_FORCE_WEBENGINE_VERIFY%"=="1" goto :webengine_verify_block
if not exist "%WEBENGINE_STAMP%" goto :webengine_verify_block
for /f "usebackq delims=" %%R in (`powershell -NoProfile -Command "$s='%WEBENGINE_STAMP%'; $p='%CD%\.venv\Lib\site-packages\PyQt6'; if(!(Test-Path $s) -or !(Test-Path $p)){'STALE'; exit}; $stamp=(Get-Item $s).LastWriteTime; $age=(Get-Date)-$stamp; if($age.TotalDays -gt 7){'STALE'; exit}; $pkg=(Get-Item $p).LastWriteTime; if($pkg -gt $stamp){'STALE'; exit}; 'FRESH'"`) do set "WEBENGINE_CACHE=%%R"
if /I "%WEBENGINE_CACHE%"=="FRESH" (
    set "WEBENGINE_NEED_VERIFY=0"
    echo [RDrive] WebEngine verificado recentemente ^(cache OK^).
)

:webengine_verify_block
if "%WEBENGINE_NEED_VERIFY%"=="1" (
    echo [RDrive] Verificando PyQt6-WebEngine...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap\verify_webengine.ps1" -Quiet -SkipNetwork
    if errorlevel 1 (
        echo [AVISO] PyQt6-WebEngine incompleto — navegador TeraBox integrado pode ficar em branco.
        echo [INFO] Repare com: scripts\bootstrap\verify_webengine.ps1
    ) else (
        > "%WEBENGINE_STAMP%" echo ok
    )
)

rem ── Cookies extension bootstrap (modo leve) ──────────────────────────
rem  Pulado por omissao para acelerar o arranque (~3-5s economizados em
rem  maquinas lentas: spawn powershell + verificacao de filesystem).
rem  A extensao cookies.txt e instalada sob demanda quando o utilizador
rem  abre o Edge dedicado para TeraBox (chrome_cookie_browser.ensure_cookies_extension).
rem  Force bootstrap eager: defina RDRIVE_BOOTSTRAP_COOKIES_EAGER=1.
if /I "%RDRIVE_BOOTSTRAP_COOKIES_EAGER%"=="1" (
    echo [RDrive] Extensao cookies TeraBox ^(bootstrap eager solicitado^)...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap\bootstrap_cookies_extension.ps1"
)

if exist "%CD%\tools\rclone-extra\rclone.exe" (
    set "RDRIVE_RCLONE_EXE=%CD%\tools\rclone-extra\rclone.exe"
    echo [RDrive] rclone TeraBox: %RDRIVE_RCLONE_EXE%
) else (
    set "RDRIVE_RCLONE_EXE="
)

echo [RDrive] Iniciando aplicativo...
echo [RDrive] UI=%RDRIVE_UI% RDRIVE_WEBUI=%RDRIVE_WEBUI%
echo [RDrive] PYTHONPATH=%PYTHONPATH%
if exist "%VENV_PYW%" (
    echo [RDrive] starting pythonw: %VENV_PYW%
    set "RDRIVE_PROJECT_ROOT=%CD%"
    start "" /D "%CD%" "%VENV_PYW%" -m rdrive
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
    echo [INFO] Defina RDRIVE_LAUNCHER_DEBUG=1 para manter esta janela aberta.
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

:detect_edge_installed
set "EDGE_INSTALLED="
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "EDGE_INSTALLED=1"
if defined EDGE_INSTALLED goto :eof
if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "EDGE_INSTALLED=1"
if defined EDGE_INSTALLED goto :eof
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe" >nul 2>&1
if not errorlevel 1 set "EDGE_INSTALLED=1"
if defined EDGE_INSTALLED goto :eof
reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe" >nul 2>&1
if not errorlevel 1 set "EDGE_INSTALLED=1"
if defined EDGE_INSTALLED goto :eof
for /f "usebackq delims=" %%I in (`where msedge 2^>nul`) do (
    set "EDGE_INSTALLED=1"
    goto :eof
)
goto :eof

:install_edge_winget
where winget >nul 2>&1
if errorlevel 1 (
    echo [AVISO] winget nao encontrado nesta maquina.
    echo [INFO] Instale o Microsoft Edge manualmente: https://www.microsoft.com/edge
    goto :eof
)

echo [RDrive] Tentando instalar Microsoft Edge via winget ^(Microsoft.Edge, scope user^)...
set "WINGET_CLI=install --id Microsoft.Edge -e --scope user --disable-interactivity --accept-package-agreements --accept-source-agreements"
set "WINGET_TIMEOUT_SEC=300"
call :run_winget_timed
if errorlevel 1 (
    echo [AVISO] Falha ao instalar Microsoft Edge com winget ^(nao bloqueia o arranque^).
    echo [INFO] Tente manualmente: winget install --id Microsoft.Edge -e --scope user
    echo [INFO] Link oficial: https://www.microsoft.com/edge
)
goto :eof

:ensure_edge_ready
call :detect_edge_installed
if defined EDGE_INSTALLED (
    echo [RDrive] Microsoft Edge detectado.
    exit /b 0
)

echo [RDrive] Microsoft Edge nao encontrado. Tentando instalar com winget...
call :install_edge_winget
call :detect_edge_installed
if defined EDGE_INSTALLED (
    echo [RDrive] Microsoft Edge instalado e detectado com sucesso.
    exit /b 0
)

echo [AVISO] Microsoft Edge ainda nao esta disponivel apos tentativa automatica.
echo [INFO] O sideload da extensao cookies TeraBox prefere o Edge no Windows.
echo [INFO] Instale manualmente: winget install --id Microsoft.Edge -e --scope user
echo [INFO] Link oficial: https://www.microsoft.com/edge
echo [INFO] O RDrive vai iniciar; o fluxo TeraBox tentara instalar o Edge novamente.
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
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\maintenance\ensure_user_path.ps1" -TargetDir "%TARGET_DIR_ESC%"`) do (
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

:ensure_venv_pip_ready
if not exist "%VENV_PY%" (
    echo [ERRO] python do venv nao encontrado: %VENV_PY%
    exit /b 1
)
"%VENV_PY%" -m pip --version >nul 2>&1
if not errorlevel 1 exit /b 0
echo [RDrive] pip ausente no venv — a reparar com ensurepip...
"%VENV_PY%" -m ensurepip --upgrade --default-pip
if errorlevel 1 (
    "%PYTHON_EXE%" -m ensurepip --upgrade --default-pip
)
"%VENV_PY%" -m pip --version >nul 2>&1
if not errorlevel 1 exit /b 0
echo [RDrive] venv irrecuperavel ^(pip em falta^) — a recriar ambiente virtual...
if exist ".venv" rd /s /q ".venv"
echo [RDrive] Criando ambiente virtual local...
"%PYTHON_EXE%" -m venv .venv
if errorlevel 1 (
    echo [ERRO] Falha ao recriar .venv
    exit /b 1
)
"%VENV_PY%" -m ensurepip --upgrade --default-pip
if errorlevel 1 (
    echo [ERRO] pip indisponivel apos recriar venv.
    exit /b 1
)
exit /b 0

:launcher_exit
if not exist "%CD%\logs" mkdir "%CD%\logs" 2>nul
if not defined RDRIVE_LAUNCH_EXIT set "RDRIVE_LAUNCH_EXIT=0"
> "%CD%\logs\.launcher-exit-code" echo %RDRIVE_LAUNCH_EXIT%
popd
endlocal & set "RDRIVE_LAUNCH_EXIT=%RDRIVE_LAUNCH_EXIT%"
if "%RDRIVE_LAUNCH_EXIT%"=="1" exit /b 1
exit /b 0

:main_end
