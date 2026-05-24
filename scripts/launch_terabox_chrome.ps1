#Requires -Version 5.1
<#
.SYNOPSIS
  Abre Chrome/Edge com perfil dedicado RDrive para login e exportação cookies TeraBox.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$LoginUrl = 'https://www.terabox.com/login'
$ProfileDir = Join-Path $env:LOCALAPPDATA 'RDrive\chrome-terabox-profile'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ExtDir = Join-Path $ProjectRoot 'tools\get-cookies-txt-locally'
$LegacyExtDir = Join-Path $ProjectRoot 'tools\cookies-txt-extension'
$WebStoreUrl = 'https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc'

function Find-Browser {
    $candidates = @(
        "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe"
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) { return $path }
    }
    foreach ($name in @('chrome', 'msedge')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function Resolve-ExtensionDir {
    if (Test-Path -LiteralPath (Join-Path $ExtDir 'manifest.json')) { return $ExtDir }
    if (Test-Path -LiteralPath (Join-Path $LegacyExtDir 'manifest.json')) { return $LegacyExtDir }
    $bootstrap = Join-Path $ProjectRoot 'scripts\bootstrap_cookies_extension.ps1'
    if (Test-Path -LiteralPath $bootstrap) {
        & $bootstrap | Out-Null
    }
    if (Test-Path -LiteralPath (Join-Path $ExtDir 'manifest.json')) { return $ExtDir }
    return $null
}

$browser = Find-Browser
if (-not $browser) {
    Write-Host '[ERRO] Chrome ou Edge nao encontrado.' -ForegroundColor Red
    Write-Host 'Instale o Google Chrome ou exporte cookies.txt noutro browser.' -ForegroundColor Yellow
    exit 2
}

if (-not (Test-Path -LiteralPath $ProfileDir)) {
    New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null
}

$resolvedExt = Resolve-ExtensionDir
$args = @(
    "--user-data-dir=$ProfileDir",
    '--new-window',
    $LoginUrl
)
if ($resolvedExt) {
    $args = @("--load-extension=$resolvedExt") + $args
}

Write-Host '[RDrive] A abrir browser dedicado TeraBox...' -ForegroundColor Cyan
Write-Host "  Executavel: $browser"
Write-Host "  Perfil:     $ProfileDir"
if ($resolvedExt) {
    Write-Host "  Extensao:   Get cookies.txt LOCALLY (carregada automaticamente)" -ForegroundColor Green
} else {
    Write-Host "  Extensao:   indisponivel — execute scripts\bootstrap_cookies_extension.ps1" -ForegroundColor Yellow
    Write-Host "  Web Store:  $WebStoreUrl" -ForegroundColor DarkGray
}
Write-Host ''
Write-Host 'Passos:' -ForegroundColor Yellow
Write-Host '  1. Faca login em terabox.com.'
Write-Host '  2. Exporte cookies.txt com a extensao (icone na barra do browser).'
Write-Host '  3. No RDrive: Importar cookies.txt ou Abrir pasta Downloads.'
Write-Host ''

Start-Process -FilePath $browser -ArgumentList $args | Out-Null
exit 0
