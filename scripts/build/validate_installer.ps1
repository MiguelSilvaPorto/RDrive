#Requires -Version 5.1
<#
.SYNOPSIS
  Validação estática do instalador RDrive (sem compilar).
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$IssFile = Join-Path $RepoRoot 'installer\RDriveSetup.iss'
$BuildScript = Join-Path $RepoRoot 'scripts\build\build_installer.ps1'
$Docs = Join-Path $RepoRoot 'docs\INSTALLER.md'
$errors = [System.Collections.Generic.List[string]]::new()

function Add-Err([string] $Msg) { $errors.Add($Msg) | Out-Null }

if (-not (Test-Path -LiteralPath $IssFile)) {
    Add-Err "Em falta: installer\RDriveSetup.iss"
}
else {
    $iss = Get-Content -LiteralPath $IssFile -Raw -Encoding UTF8
    foreach ($needle in @('[Setup]', '[Files]', '[Icons]', '[Languages]', 'AppId=')) {
        if ($iss -notmatch [regex]::Escape($needle)) {
            Add-Err "RDriveSetup.iss sem secção/marca: $needle"
        }
    }
    if ($iss -notmatch 'BrazilianPortuguese') {
        Add-Err 'RDriveSetup.iss deve referenciar BrazilianPortuguese.isl'
    }
}

if (-not (Test-Path -LiteralPath $BuildScript)) {
    Add-Err 'Em falta: scripts\build\build_installer.ps1'
}

if (-not (Test-Path -LiteralPath $Docs)) {
    Add-Err 'Em falta: docs\INSTALLER.md'
}

if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot 'Iniciar.bat'))) {
    Add-Err 'Em falta: Iniciar.bat na raiz'
}

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    Write-Warning 'ISCC.exe não está no PATH (compilação manual ou instalar Inno Setup 6).'
}
else {
    Write-Host "ISCC encontrado: $($iscc.Source)"
}

if ($errors.Count -gt 0) {
    Write-Host '[FALHA] Validação do instalador:'
    $errors | ForEach-Object { Write-Host "  - $_" }
    exit 1
}

Write-Host '[OK] Estrutura do instalador válida.'
exit 0
