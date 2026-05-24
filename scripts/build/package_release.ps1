# Build a Windows-friendly release zip for GitHub (not the auto source-code zip).
# Usage (repo root): .\scripts\build\package_release.ps1 [-Tag v0.2.0-semi-stable]
param(
    [string]$Tag = '',
    [string]$OutputDir = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$pyproject = Join-Path $repoRoot 'pyproject.toml'
$version = '0.1.0'
if (Test-Path -LiteralPath $pyproject) {
    $line = Get-Content -LiteralPath $pyproject -Encoding UTF8 |
        Where-Object { $_ -match '^\s*version\s*=\s*"' } |
        Select-Object -First 1
    if ($line -match 'version\s*=\s*"([^"]+)"') { $version = $Matches[1] }
}
if (-not $Tag) { $Tag = "v$version" }
$tagSlug = $Tag.TrimStart('v')
$folderName = "RDrive-$tagSlug"

if (-not $OutputDir) { $OutputDir = Join-Path $repoRoot 'dist' }
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# Reuse installer staging (same excludes as RDriveSetup.exe).
& (Join-Path $PSScriptRoot 'build_installer.ps1') -SkipCompile | Out-Host
$staging = Join-Path $repoRoot 'dist\installer-staging'
if (-not (Test-Path -LiteralPath $staging)) {
    throw 'installer-staging missing after build_installer.ps1 -SkipCompile'
}

$zipPath = Join-Path $OutputDir "$folderName-windows.zip"
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

$zipTemp = Join-Path $OutputDir "_ziproot"
if (Test-Path -LiteralPath $zipTemp) {
    Remove-Item -LiteralPath $zipTemp -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $zipTemp | Out-Null
$inner = Join-Path $zipTemp $folderName
Copy-Item -LiteralPath $staging -Destination $inner -Recurse -Force
Compress-Archive -LiteralPath $inner -DestinationPath $zipPath -CompressionLevel Optimal
Remove-Item -LiteralPath $zipTemp -Recurse -Force

Write-Host "[OK] Release zip: $zipPath"
Write-Host "[INFO] Upload as release asset (do not rely on GitHub Source code zip alone)."
Write-Host "[INFO] End users: extract, open $folderName, run Iniciar.bat (first run 2-5 min, console visible)."
