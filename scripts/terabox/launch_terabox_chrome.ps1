#Requires -Version 5.1
<#
.SYNOPSIS
  Abre Microsoft Edge com perfil dedicado RDrive para login e exportação cookies TeraBox.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$LoginUrl = 'https://www.terabox.com/login'
$ProfileDir = Join-Path $env:LOCALAPPDATA 'RDrive\chrome-rdrive-isolated-profile'
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ExtDir = Join-Path $ProjectRoot 'tools\get-cookies-txt-locally'
$LegacyExtDir = Join-Path $ProjectRoot 'tools\cookies-txt-extension'
$WebStoreUrl = 'https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc'
$ExtensionsUrl = 'edge://extensions'

function Find-Edge {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe",
        "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) { return $path }
    }
    $cmd = Get-Command msedge -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Resolve-ExtensionDir {
    if (Test-Path -LiteralPath (Join-Path $ExtDir 'manifest.json')) {
        return (Resolve-Path -LiteralPath $ExtDir).Path
    }
    if (Test-Path -LiteralPath (Join-Path $LegacyExtDir 'manifest.json')) {
        return (Resolve-Path -LiteralPath $LegacyExtDir).Path
    }
    $bootstrap = Join-Path $ProjectRoot 'scripts\bootstrap\bootstrap_cookies_extension.ps1'
    if (Test-Path -LiteralPath $bootstrap) {
        & $bootstrap | Out-Null
    }
    if (Test-Path -LiteralPath (Join-Path $ExtDir 'manifest.json')) {
        return (Resolve-Path -LiteralPath $ExtDir).Path
    }
    return $null
}

$browser = Find-Edge
if (-not $browser) {
    Write-Host '[ERRO] Microsoft Edge nao encontrado.' -ForegroundColor Red
    Write-Host 'Instale o Microsoft Edge: https://www.microsoft.com/edge' -ForegroundColor Yellow
    Write-Host 'Ou: winget install --id Microsoft.Edge -e --scope user' -ForegroundColor Yellow
    exit 2
}

if (-not (Test-Path -LiteralPath $ProfileDir)) {
    New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null
}

$resolvedExt = Resolve-ExtensionDir
$profileResolved = (Resolve-Path -LiteralPath $ProfileDir).Path
$args = @(
    "--user-data-dir=$profileResolved",
    '--new-window',
    $LoginUrl
)
if ($resolvedExt) {
    $args = @("--load-extension=$resolvedExt") + $args + @($ExtensionsUrl)
}

Write-Host '[RDrive] A abrir Microsoft Edge dedicado TeraBox...' -ForegroundColor Cyan
Write-Host "  Executavel: $browser"
Write-Host "  Perfil:     $profileResolved"
if ($resolvedExt) {
    Write-Host "  Extensao:   $resolvedExt" -ForegroundColor Green
    Write-Host "  Verificacao: $ExtensionsUrl (segundo separador)" -ForegroundColor DarkGray
} else {
    Write-Host "  Extensao:   indisponivel — execute scripts\bootstrap\bootstrap_cookies_extension.ps1" -ForegroundColor Yellow
    Write-Host "  Pasta:      $ExtDir" -ForegroundColor DarkGray
    Write-Host "  Web Store:  $WebStoreUrl" -ForegroundColor DarkGray
}
Write-Host ''
Write-Host 'Use o Edge aberto por este script — nao o Edge diario.' -ForegroundColor Yellow
Write-Host ''
Write-Host 'Passos:' -ForegroundColor Yellow
Write-Host '  1. Faca login em terabox.com.'
Write-Host '  2. Exporte cookies.txt com a extensao (icone na barra do browser).'
Write-Host '  3. No RDrive: Importar cookies.txt ou Abrir pasta Downloads.'
Write-Host ''

Start-Process -FilePath $browser -ArgumentList $args | Out-Null
exit 0
