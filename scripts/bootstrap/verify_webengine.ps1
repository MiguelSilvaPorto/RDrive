#Requires -Version 5.1
param(
    [switch]$Quiet,
    [switch]$SkipNetwork
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
$VenvPy = Join-Path $Root '.venv\Scripts\python.exe'
$ExitCode = 0

function Write-Step([string]$Text, [string]$Level = 'INFO') {
    if ($Quiet) { return }
    $prefix = switch ($Level) {
        'OK' { '[OK] ' }
        'WARN' { '[AVISO] ' }
        'ERR' { '[ERRO] ' }
        default { '[INFO] ' }
    }
    Write-Host ($prefix + $Text)
}

function Write-Fail([string]$Text) {
    Write-Step $Text 'ERR'
    $script:ExitCode = 1
}

if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Fail "Ambiente virtual nao encontrado: $VenvPy"
    Write-Step 'Crie o venv: python -m venv .venv' 'WARN'
    exit 1
}

Write-Step 'RDrive - verificacao PyQt6-WebEngine'
Write-Step "Python: $VenvPy"

$importOut = & $VenvPy -c "from PyQt6.QtWebEngineWidgets import QWebEngineView; print('import ok')" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail 'Import PyQt6-WebEngine falhou.'
    if (-not $Quiet) { Write-Host $importOut }
    Write-Step 'Reinstale: .venv\Scripts\python.exe -m pip install --upgrade PyQt6-WebEngine>=6.6.0' 'WARN'
    exit 1
}
Write-Step 'Import PyQt6-WebEngine' 'OK'

$binScript = Join-Path $Root 'scripts\bootstrap\_webengine_check_binaries.py'
if (-not (Test-Path -LiteralPath $binScript)) {
    Write-Fail "Script de binarios em falta: $binScript"
}
else {
    $binOut = & $VenvPy $binScript 2>&1 | Out-String
    $processCount = 0
    $pakCount = 0
    $processPath = ''
    foreach ($line in ($binOut -split "`n")) {
        if ($line -match '^process\s+(\d+)') { $processCount = [int]$Matches[1] }
        if ($line -match '^pak\s+(\d+)') { $pakCount = [int]$Matches[1] }
        if ($line -match '^process_path\s+(.+)') { $processPath = $Matches[1].Trim() }
    }
    if ($processCount -lt 1) {
        Write-Fail 'QtWebEngineProcess.exe nao encontrado no pacote PyQt6.'
    }
    else {
        Write-Step "QtWebEngineProcess.exe ($processPath)" 'OK'
    }
    if ($pakCount -lt 1) {
        Write-Fail 'qtwebengine_resources.pak em falta - instalacao incompleta.'
    }
    else {
        Write-Step 'Recursos WebEngine (.pak)' 'OK'
    }
}

$setHtmlScript = Join-Path $Root 'scripts\bootstrap\_webengine_sethtml_test.py'
if (Test-Path -LiteralPath $setHtmlScript) {
    $renderLocal = & $VenvPy $setHtmlScript 2>&1 | Out-String
    if ($renderLocal -notmatch 'RESULT:\s*0') {
        Write-Fail 'Renderizacao local (setHtml) falhou - WebEngine incompleto ou GPU bloqueada.'
        if (-not $Quiet) { Write-Host ($renderLocal.Trim()) }
    }
    else {
        Write-Step 'Renderizacao local (setHtml)' 'OK'
    }
}

if (-not $SkipNetwork) {
    $probeScript = Join-Path $Root 'scripts\bootstrap\_webengine_probe_test.py'
    if (Test-Path -LiteralPath $probeScript) {
        $renderNet = & $VenvPy $probeScript 'https://www.google.com/' 2>&1 | Out-String
        if ($renderNet -match 'RESULT:\s*0') {
            Write-Step 'Renderizacao HTTPS (google.com)' 'OK'
        }
        elseif ($renderNet -match 'RESULT:\s*4') {
            Write-Step 'HTTPS demorou demasiado (rede/firewall?) - import/binarios OK.' 'WARN'
        }
        else {
            Write-Step 'HTTPS nao renderizou - UI file:// pode funcionar; sites externos podem falhar.' 'WARN'
            if (-not $Quiet) { Write-Host ($renderNet.Trim()) }
        }
    }
}

if ($ExitCode -ne 0) {
    Write-Step '=== Recuperacao (pt-BR) ===' 'WARN'
    Write-Step '1. Feche o RDrive completamente (bandeja + Gestor de tarefas).' 'WARN'
    Write-Step '2. Na pasta do projeto:' 'WARN'
    Write-Step '   .venv\Scripts\python.exe -m pip uninstall -y PyQt6 PyQt6-WebEngine PyQt6-Qt6 PyQt6-sip' 'WARN'
    Write-Step '   .venv\Scripts\python.exe -m pip install --upgrade pip' 'WARN'
    Write-Step '   .venv\Scripts\python.exe -m pip install -r requirements.txt' 'WARN'
    Write-Step '3. Execute novamente: .\scripts\bootstrap\verify_webengine.ps1' 'WARN'
    Write-Step '4. Reinicie com Iniciar.bat' 'WARN'
}
elseif (-not $Quiet) {
    Write-Step 'Verificacao concluida - PyQt6-WebEngine operacional.'
}

exit $ExitCode
