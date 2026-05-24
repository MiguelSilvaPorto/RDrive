#Requires -Version 5.1
<#
.SYNOPSIS
  Garante extensão «Get cookies.txt LOCALLY» descompactada em tools/get-cookies-txt-locally/.
.DESCRIPTION
  Descarrega o release Chrome v0.7.2 do GitHub se manifest.json faltar.
  Chamado por Iniciar.bat (após venv) e implicitamente ao abrir Chrome TeraBox.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ExtDir = Join-Path $ProjectRoot 'tools\get-cookies-txt-locally'
$Manifest = Join-Path $ExtDir 'manifest.json'

if (Test-Path -LiteralPath $Manifest) {
    Write-Host '[RDrive] Extensao cookies.txt ja presente.' -ForegroundColor DarkGray
    exit 0
}

$VenvPy = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$BootstrapPy = Join-Path $ProjectRoot 'scripts\bootstrap_cookies_extension.py'
if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Host '[RDrive] venv ausente — extensao sera instalada no primeiro Chrome TeraBox.' -ForegroundColor DarkGray
    exit 0
}

$env:PYTHONPATH = "$(Join-Path $ProjectRoot 'src');$env:PYTHONPATH"
Write-Host '[RDrive] A preparar extensao Get cookies.txt LOCALLY...' -ForegroundColor Cyan

$resultJson = & $VenvPy $BootstrapPy 2>&1 | Out-String
try {
    $result = $resultJson.Trim() | ConvertFrom-Json
} catch {
    Write-Host '[AVISO] Bootstrap extensao: resposta invalida' -ForegroundColor Yellow
    Write-Host $resultJson
    exit 0
}

if ($result.ok) {
    if ($result.downloaded) {
        Write-Host "[RDrive] Extensao instalada em $ExtDir" -ForegroundColor Green
    }
    exit 0
}

Write-Host "[AVISO] $($result.error)" -ForegroundColor Yellow
if ($result.web_store_url) {
    Write-Host "  Web Store (opcional): $($result.web_store_url)" -ForegroundColor DarkGray
}
exit 0
