#Requires -Version 5.1
<#
.SYNOPSIS
  Prepara dist\installer-staging\ e compila dist\RDriveSetup.exe com Inno Setup (ISCC).

.DESCRIPTION
  Copia o layout de release do RDrive (sem .venv, .git, logs, segredos, caches).
  Não inclui binários grandes de tools/ — apenas .gitkeep e NOTICE; o bootstrap
  em Iniciar.bat descarrega/instala rclone, extensão cookies, etc. na 1.ª execução.

.PARAMETER SkipCompile
  Apenas gera o staging; nao invoca ISCC.

.PARAMETER InnoSetupPath
  Caminho para ISCC.exe (opcional). Se omitido, procura no PATH e em locais habituais.

.EXAMPLE
  .\scripts\build\build_installer.ps1
#>
[CmdletBinding()]
param(
    [switch] $SkipCompile,
    [string] $InnoSetupPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$StagingRoot = Join-Path $RepoRoot 'dist\installer-staging'
$DistDir = Join-Path $RepoRoot 'dist'
$IssFile = Join-Path $RepoRoot 'installer\RDriveSetup.iss'
$IconSrc = Join-Path $RepoRoot 'src\rdrive\assets\branding\rdrive.ico'
$IconDst = Join-Path $RepoRoot 'installer\rdrive.ico'

function Get-VersionInfoQuad {
    param([string] $Version)
    $parts = @($Version -split '\.')
    while ($parts.Count -lt 4) { $parts += '0' }
    return ($parts[0..3] -join '.')
}

function Get-AppVersion {
    $pyproject = Join-Path $RepoRoot 'pyproject.toml'
    if (-not (Test-Path -LiteralPath $pyproject)) {
        return '0.1.0'
    }
    $line = Get-Content -LiteralPath $pyproject -Encoding UTF8 |
        Where-Object { $_ -match '^\s*version\s*=\s*"' } |
        Select-Object -First 1
    if ($line -match 'version\s*=\s*"([^"]+)"') {
        return $Matches[1]
    }
    return '0.1.0'
}

function Test-ExcludedPath {
    param([string] $RelativePath)
    $rel = $RelativePath -replace '\\', '/'
    $name = Split-Path -Leaf $RelativePath

    $dirExcludes = @(
        '.git', '.venv', 'venv', 'ENV', 'env',
        '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.hypothesis',
        'node_modules', '.cursor', '.idea', 'build', 'dist',
        'logs', 'tempo', 'users', 'session', 'cache', 'mounts', 'webui', 'state',
        'stripe_wal', 'stripe_assembly', 'provider_icons', 'terabox-browser',
        'chrome-rdrive-isolated-profile', 'extensions',
        '.tox', '.nox', 'htmlcov', 'coverage', '.eggs'
    )
    foreach ($d in $dirExcludes) {
        if ($rel -eq $d -or $rel -like "$d/*") { return $true }
    }

    if ($rel -like 'tests/*' -or $rel -eq 'tests') { return $true }
    if ($rel -like 'installer/*' -or $rel -eq 'installer') { return $true }
    if ($rel -like 'scripts/build/*') { return $true }

    $fileExcludes = @(
        '.env', '.env.local', 'rclone.conf', '.rclone.conf',
        'cookies.txt', 'remembered_vault.blob', 'restarting.flag',
        'drives.json', 'drives.enc', 'settings.json', 'settings.enc',
        'recent.json', 'recovery_profile.json', 'recovery_token.json'
    )
    if ($fileExcludes -contains $name) { return $true }

    if ($name -match '\.(pyc|pyo|pem|key|enc|log|tmp|temp|bak|cache|swp|swo|blob)$') { return $true }
    if ($name -eq 'Cookies' -or $name -eq 'Cookies-journal') { return $true }
    if ($rel -like '*/Network/Cookies*') { return $true }
    if ($rel -like 'tools/rclone-extra/*' -and $name -notin @('.gitkeep', 'NOTICE')) { return $true }
    if ($rel -like 'tools/get-cookies-txt-locally/*' -and $name -notin @('.gitkeep', 'NOTICE')) { return $true }

    return $false
}

function Copy-ReleaseTree {
    param(
        [string] $Source,
        [string] $Dest,
        [string] $RelativeBase = ''
    )
    Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
        $rel = if ($RelativeBase) { "$RelativeBase/$($_.Name)" } else { $_.Name }
        $rel = $rel.TrimStart('/')

        if (Test-ExcludedPath -RelativePath $rel) {
            return
        }

        $target = Join-Path $Dest $_.Name
        if ($_.PSIsContainer) {
            if (-not (Test-Path -LiteralPath $target)) {
                New-Item -ItemType Directory -Path $target -Force | Out-Null
            }
            Copy-ReleaseTree -Source $_.FullName -Dest $target -RelativeBase $rel
        }
        else {
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
    }
}

function Find-ISCC {
    param([string] $Explicit)
    if ($Explicit -and (Test-Path -LiteralPath $Explicit)) {
        return (Resolve-Path -LiteralPath $Explicit).Path
    }
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:LocalAppData}\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    return $null
}

function Ensure-EmptyLogsDir {
    $logs = Join-Path $StagingRoot 'logs'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $keep = Join-Path $logs '.gitkeep'
    if (-not (Test-Path -LiteralPath $keep)) {
        Set-Content -LiteralPath $keep -Value '' -Encoding UTF8
    }
}

# --- main ---
if (-not (Test-Path -LiteralPath $IssFile)) {
    throw "Ficheiro Inno Setup em falta: $IssFile"
}

$version = Get-AppVersion
$versionInfo = Get-VersionInfoQuad -Version $version
Write-Host "[RDrive] Versao: $version ($versionInfo)"
Write-Host "[RDrive] Staging: $StagingRoot"

if (Test-Path -LiteralPath $StagingRoot) {
    Remove-Item -LiteralPath $StagingRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $StagingRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $DistDir)) {
    New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
}

$rootFiles = @(
    'Iniciar.bat', 'README.md', 'pyproject.toml', 'requirements.txt', 'ARCHITECTURE.md'
)
foreach ($f in $rootFiles) {
    $src = Join-Path $RepoRoot $f
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $StagingRoot $f) -Force
    }
}

foreach ($dir in @('src', 'Static', 'scripts', 'docs')) {
    $srcDir = Join-Path $RepoRoot $dir
    if (-not (Test-Path -LiteralPath $srcDir)) { continue }
    $dstDir = Join-Path $StagingRoot $dir
    New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
    Copy-ReleaseTree -Source $srcDir -Dest $dstDir -RelativeBase $dir
}

foreach ($toolSub in @('rclone-extra', 'get-cookies-txt-locally')) {
    $toolDir = Join-Path $RepoRoot "tools\$toolSub"
    if (-not (Test-Path -LiteralPath $toolDir)) { continue }
    $dstTool = Join-Path $StagingRoot "tools\$toolSub"
    New-Item -ItemType Directory -Path $dstTool -Force | Out-Null
    Get-ChildItem -LiteralPath $toolDir -File -Force |
        Where-Object { $_.Name -in @('.gitkeep', 'NOTICE') } |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $dstTool $_.Name) -Force }
}

Ensure-EmptyLogsDir

if (-not (Test-Path -LiteralPath (Join-Path $StagingRoot 'Iniciar.bat'))) {
    throw 'Staging invalido: Iniciar.bat em falta.'
}

if (Test-Path -LiteralPath $IconSrc) {
    Copy-Item -LiteralPath $IconSrc -Destination $IconDst -Force
    Write-Host "[RDrive] Icone do instalador: $IconDst"
}
else {
    Write-Warning "[RDrive] rdrive.ico nao encontrado em $IconSrc - SetupIconFile pode falhar."
}

$fileCount = @(Get-ChildItem -LiteralPath $StagingRoot -Recurse -File).Count
Write-Host ('[RDrive] Staging concluido ({0} ficheiros).' -f $fileCount)

& (Join-Path $PSScriptRoot 'validate_release.ps1') -Path $StagingRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Staging rejeitado por validate_release.ps1 (dados de utilizador ou segredos).'
}

if ($SkipCompile) {
    Write-Host '[RDrive] SkipCompile: nao foi invocado ISCC.'
    Write-Host "Compile manualmente: ISCC.exe /DMyAppVersion=$version /DMyAppVersionInfo=$versionInfo `"$IssFile`""
    exit 0
}

$iscc = Find-ISCC -Explicit $InnoSetupPath
if (-not $iscc) {
    Write-Host ''
    Write-Host '[AVISO] Inno Setup (ISCC.exe) nao encontrado.'
    Write-Host '  1. Instale Inno Setup 6: https://jrsoftware.org/isdl.php'
    Write-Host "  2. Compile: `"<pasta Inno>\ISCC.exe`" /DMyAppVersion=$version /DMyAppVersionInfo=$versionInfo `"$IssFile`""
    Write-Host '  Ou: .\scripts\build\build_installer.ps1 -InnoSetupPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"'
    Write-Host ''
    Write-Host "Staging pronto em: $StagingRoot"
    exit 2
}

Write-Host "[RDrive] ISCC: $iscc"
& $iscc "/DMyAppVersion=$version" "/DMyAppVersionInfo=$versionInfo" $IssFile
if ($LASTEXITCODE -ne 0) {
    throw "ISCC falhou com codigo $LASTEXITCODE"
}

$outExe = Join-Path $DistDir 'RDriveSetup.exe'
if (Test-Path -LiteralPath $outExe) {
    $sizeMb = [math]::Round((Get-Item -LiteralPath $outExe).Length / 1MB, 2)
    Write-Host ('[RDrive] Instalador gerado: {0} ({1} MB)' -f $outExe, $sizeMb)
}
else {
    throw "ISCC terminou mas $outExe nao existe."
}

exit 0
