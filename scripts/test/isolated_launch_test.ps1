#Requires -Version 5.1
<#
.SYNOPSIS
  Harness de teste isolado para releases RDrive (venv + AppData limpos).

.DESCRIPTION
  Nao usa %%LOCALAPPDATA%%\RDrive\ do PC. Cria .venv apenas na pasta da release
  e grava um relatorio com timestamps em _isolated_test\report\.

.PARAMETER ReleaseRoot
  Pasta extraida (ex.: C:\Users\...\RDrive-0.2.2-semi-stable).

.PARAMETER Reset
  Apaga _isolated_test\ e .venv antes de correr (reproducao limpa).

.PARAMETER SkipLaunch
  Apenas prepara ambiente e valida Python/pip; nao executa Iniciar.bat.

.EXAMPLE
  .\scripts\test\isolated_launch_test.ps1 -ReleaseRoot "C:\Users\migue\Documents\RDrive-0.2.2-semi-stable" -Reset
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseRoot,

    [switch]$Reset,
    [switch]$SkipLaunch
)

$ErrorActionPreference = 'Stop'

function Write-Step {
    param([string]$Message)
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'
    $line = "[$ts] $Message"
    Write-Host $line
    Add-Content -LiteralPath $script:ReportFile -Value $line -Encoding UTF8
}

$ReleaseRoot = (Resolve-Path -LiteralPath $ReleaseRoot).Path
$IsolatedRoot = Join-Path $ReleaseRoot '_isolated_test'

if (-not (Test-Path -LiteralPath (Join-Path $ReleaseRoot 'Iniciar.bat'))) {
    Write-Host 'ERROR Iniciar.bat not found in ReleaseRoot'
    exit 1
}

if ($Reset) {
    Write-Host 'Reset: removing _isolated_test and .venv'
    Remove-Item -LiteralPath $IsolatedRoot -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $ReleaseRoot '.venv') -Recurse -Force -ErrorAction SilentlyContinue
}

$ReportDir = Join-Path $IsolatedRoot 'report'
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
$script:ReportFile = Join-Path $ReportDir ("isolated-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))

Write-Step "==== RDrive isolated launch test ===="
Write-Step "ReleaseRoot: $ReleaseRoot"
Write-Step "IsolatedRoot: $IsolatedRoot"

$env:RDRIVE_ISOLATED = '1'
$env:RDRIVE_ISOLATED_ROOT = $IsolatedRoot
$env:RDRIVE_DATA_DIR = Join-Path $IsolatedRoot 'RDrive'
$env:LOCALAPPDATA = Join-Path $IsolatedRoot 'LocalAppData'
$env:APPDATA = Join-Path $IsolatedRoot 'Roaming'
$env:RDRIVE_LAUNCHER_VISIBLE = '1'
$env:RDRIVE_PROJECT_ROOT = $ReleaseRoot
New-Item -ItemType Directory -Force -Path $env:LOCALAPPDATA, $env:APPDATA, $env:RDRIVE_DATA_DIR | Out-Null
Write-Step "LOCALAPPDATA=$($env:LOCALAPPDATA)"
Write-Step "RDRIVE_DATA_DIR=$($env:RDRIVE_DATA_DIR)"

$pyGlobal = $null
foreach ($cmd in @('py -3', 'python')) {
    try {
        $pyGlobal = & cmd /c "$cmd -c `"import sys;print(sys.executable)`"" 2>$null
        if ($pyGlobal) { break }
    } catch { }
}
if (-not $pyGlobal) {
    Write-Step 'ERROR Python 3 not found on PATH'
    exit 1
}
Write-Step "Global Python: $pyGlobal"

if ($SkipLaunch) {
    Write-Step 'SkipLaunch - environment prepared only'
    exit 0
}

$batPath = Join-Path $ReleaseRoot 'Iniciar.bat'
$logLauncher = Join-Path $ReleaseRoot 'logs\launcher.log'
$exitMarker = Join-Path $ReleaseRoot 'logs\.launcher-exit-code'

Write-Step 'Launching log_launcher.ps1 (wrapped Iniciar.bat)...'
$launcherPs1 = Join-Path $ReleaseRoot 'scripts\maintenance\log_launcher.ps1'
if (-not (Test-Path -LiteralPath $launcherPs1)) {
    Write-Step "ERROR missing $launcherPs1"
    exit 1
}

Push-Location $ReleaseRoot
try {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $launcherPs1 -BatPath $batPath
    $launcherExit = $LASTEXITCODE
}
finally {
    Pop-Location
}

Write-Step "log_launcher.ps1 exit: $launcherExit"

if (Test-Path -LiteralPath $exitMarker) {
    Write-Step "logs/.launcher-exit-code: $((Get-Content -LiteralPath $exitMarker -Raw).Trim())"
}

foreach ($name in @('launcher.log', 'human.log', 'rdrive.log')) {
    $path = Join-Path $ReleaseRoot "logs\$name"
    if (Test-Path -LiteralPath $path) {
        $info = Get-Item -LiteralPath $path
        Write-Step ('log ' + $name + ' - ' + $info.Length + ' bytes, tail:')
        Get-Content -LiteralPath $path -Tail 15 -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Step ('  | ' + $_)
        }
    } else {
        Write-Step ('log ' + $name + ' - (missing)')
    }
}

$venvPy = Join-Path $ReleaseRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPy) {
    $pipVer = & $venvPy -m pip --version 2>&1
    Write-Step "venv pip: $pipVer"
} else {
    Write-Step 'venv python.exe - (missing)'
}

if ($launcherExit -ne 0) {
    Write-Step 'RESULT: FAIL (launcher exit non-zero)'
    exit $launcherExit
}

if (Test-Path -LiteralPath $logLauncher) {
    $tail = (Get-Content -LiteralPath $logLauncher -Tail 30) -join "`n"
    if ($tail -match '\[ERRO\]') {
        Write-Step 'RESULT: FAIL ([ERRO] in launcher.log)'
        exit 1
    }
}

Write-Step 'RESULT: OK (bootstrap finished; check tray/window manually)'
Write-Step "Report: $script:ReportFile"
exit 0
