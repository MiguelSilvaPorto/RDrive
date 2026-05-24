#Requires -Version 5.1
<#
.SYNOPSIS
  Prepara Playwright para o agente TeraBox / OAuth isolado (channel=msedge).
#>
param(
    [switch]$Quiet
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$VenvPy = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$StampPath = Join-Path $ProjectRoot '.venv\.playwright-stamp'

function Write-Step([string]$Message, [string]$Level = 'INFO') {
    if ($Quiet) { return }
    $color = switch ($Level) {
        'WARN' { 'Yellow' }
        'ERR'  { 'Red' }
        default { 'Cyan' }
    }
    Write-Host "[RDrive/Playwright] $Message" -ForegroundColor $color
}

if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Step 'venv nao encontrado — execute Iniciar.bat primeiro.' 'WARN'
    exit 1
}

try {
    & $VenvPy -c "import playwright" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Step 'Pacote playwright nao instalado.' 'WARN'
        exit 1
    }
} catch {
    Write-Step 'Pacote playwright nao instalado.' 'WARN'
    exit 1
}

Write-Step 'A verificar Microsoft Edge (Playwright channel=msedge)…'
$edgeOk = $false
$edgeCandidates = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe"
)
foreach ($path in $edgeCandidates) {
    if ($path -and (Test-Path -LiteralPath $path)) {
        $edgeOk = $true
        break
    }
}
if (-not $edgeOk) {
    $cmd = Get-Command msedge -ErrorAction SilentlyContinue
    if ($cmd) { $edgeOk = $true }
}
if (-not $edgeOk) {
    Write-Step 'Microsoft Edge nao encontrado — TeraBox/OAuth isolado podem falhar.' 'WARN'
    Write-Step 'Instale: winget install --id Microsoft.Edge -e --scope user' 'WARN'
    exit 1
}

Set-Content -LiteralPath $StampPath -Value (Get-Date -Format 'o') -Encoding UTF8
Write-Step 'Playwright pronto (usa Edge do sistema via channel=msedge).'
exit 0
