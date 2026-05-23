# RDrive — repor cofre encriptado (.enc) sem apagar JSON legado (por defeito).
# Uso: .\scripts\reset_vault.ps1
#      .\scripts\reset_vault.ps1 -WipeAll
#      .\scripts\reset_vault.ps1 -Confirm "RESET"

param(
    [switch]$WipeAll,
    [string]$Confirm = ""
)

$ErrorActionPreference = 'Stop'

function Get-ProjectRoot {
    if ($env:RDRIVE_PROJECT_ROOT) {
        $fromEnv = $env:RDRIVE_PROJECT_ROOT.Trim()
        if ($fromEnv -and (Test-Path -LiteralPath $fromEnv)) {
            return (Resolve-Path -LiteralPath $fromEnv).Path
        }
    }
    $here = $PSScriptRoot
    if ($here) {
        return (Resolve-Path -LiteralPath (Join-Path $here '..')).Path
    }
    return (Get-Location).Path
}

function Write-ResetLog {
    param([string]$Message)
    if ([string]::IsNullOrWhiteSpace($Message)) { return }
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $script:LogFile -Value "[$ts] $Message" -Encoding UTF8
}

function Get-RDriveDataRoot {
    $local = $env:LOCALAPPDATA
    if (-not $local) {
        throw 'LOCALAPPDATA nao definido.'
    }
    return (Join-Path $local 'RDrive\RDrive')
}

function Get-StateDirs {
    param([string]$DataRoot)
    $dirs = @((Join-Path $DataRoot 'state'))
    $usersRoot = Join-Path $DataRoot 'users'
    if (Test-Path -LiteralPath $usersRoot) {
        Get-ChildItem -LiteralPath $usersRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $userState = Join-Path $_.FullName 'state'
            if (Test-Path -LiteralPath $userState) {
                $dirs += $userState
            }
        }
    }
    return $dirs | Select-Object -Unique
}

function Get-RecoveryTokenPaths {
    param([string]$DataRoot)
    $paths = @((Join-Path $DataRoot 'recovery_token.json'))
    foreach ($stateDir in (Get-StateDirs -DataRoot $DataRoot)) {
        $inState = Join-Path $stateDir 'recovery_token.json'
        if ($paths -notcontains $inState) {
            $paths += $inState
        }
    }
    return $paths
}

$projectRoot = Get-ProjectRoot
$logDir = Join-Path $projectRoot 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$script:LogFile = Join-Path $logDir 'reset_vault.log'

Write-ResetLog '==== reset_vault session start ===='
Write-ResetLog "project_root: $projectRoot"
Write-ResetLog "WipeAll: $WipeAll"

if ($Confirm -ne 'RESET') {
    Write-Host ''
    Write-Host 'RDrive — repor cofre encriptado' -ForegroundColor Cyan
    Write-Host 'Isto remove drives.enc, settings.enc e recovery_token.json.'
    if ($WipeAll) {
        Write-Host 'Modo -WipeAll: apaga tambem drives.json, settings.json e a pasta users/.' -ForegroundColor Yellow
    } else {
        Write-Host 'Ficheiros drives.json / settings.json legados sao preservados.' -ForegroundColor Green
    }
    Write-Host ''
    $typed = Read-Host 'Digite RESET para confirmar'
    if ($typed -ne 'RESET') {
        Write-ResetLog 'ABORTED: confirmation mismatch'
        Write-Host 'Operacao cancelada (confirmacao incorreta).' -ForegroundColor Yellow
        exit 1
    }
    Write-ResetLog 'confirmation: RESET'
}

$dataRoot = Get-RDriveDataRoot
Write-ResetLog "data_root: $dataRoot"

if (-not (Test-Path -LiteralPath $dataRoot)) {
    Write-ResetLog 'data_root missing — nothing to remove'
    Write-Host "Nada encontrado em $dataRoot"
    exit 0
}

$vaultEnc = @('drives.enc', 'settings.enc')
$plainJson = @('drives.json', 'settings.json')
$removed = [System.Collections.Generic.List[string]]::new()

Write-Host ''
Write-Host "Estado antes do reset ($dataRoot):" -ForegroundColor Cyan
foreach ($stateDir in (Get-StateDirs -DataRoot $dataRoot)) {
    Write-Host "  [$stateDir]"
    if (-not (Test-Path -LiteralPath $stateDir)) {
        Write-Host '    (pasta inexistente)'
        continue
    }
    Get-ChildItem -LiteralPath $stateDir -Force -ErrorAction SilentlyContinue |
        Sort-Object Name |
        ForEach-Object {
            Write-Host ('    {0,-20} {1,8} bytes' -f $_.Name, $_.Length)
            Write-ResetLog "before: $stateDir\$($_.Name) $($_.Length) bytes"
        }
}
foreach ($tokenPath in (Get-RecoveryTokenPaths -DataRoot $dataRoot)) {
    if (Test-Path -LiteralPath $tokenPath) {
        $item = Get-Item -LiteralPath $tokenPath
        Write-Host ('  [token] {0,-20} {1,8} bytes' -f $item.FullName, $item.Length)
        Write-ResetLog "before: $($item.FullName) $($item.Length) bytes"
    }
}

Write-Host ''
Write-Host 'A remover...' -ForegroundColor Cyan

foreach ($stateDir in (Get-StateDirs -DataRoot $dataRoot)) {
    foreach ($name in $vaultEnc) {
        $path = Join-Path $stateDir $name
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
            $removed.Add($path)
            Write-ResetLog "removed: $path"
            Write-Host "  removido: $path" -ForegroundColor Green
        }
    }
    if ($WipeAll) {
        foreach ($name in $plainJson) {
            $path = Join-Path $stateDir $name
            if (Test-Path -LiteralPath $path) {
                Remove-Item -LiteralPath $path -Force
                $removed.Add($path)
                Write-ResetLog "removed: $path"
                Write-Host "  removido: $path" -ForegroundColor Yellow
            }
        }
    }
}

foreach ($tokenPath in (Get-RecoveryTokenPaths -DataRoot $dataRoot)) {
    if (Test-Path -LiteralPath $tokenPath) {
        Remove-Item -LiteralPath $tokenPath -Force
        $removed.Add($tokenPath)
        Write-ResetLog "removed: $tokenPath"
        Write-Host "  removido: $tokenPath" -ForegroundColor Green
    }
}

if ($WipeAll) {
    $usersRoot = Join-Path $dataRoot 'users'
    if (Test-Path -LiteralPath $usersRoot) {
        Remove-Item -LiteralPath $usersRoot -Recurse -Force
        $removed.Add($usersRoot)
        Write-ResetLog "removed: $usersRoot (tree)"
        Write-Host "  removido: $usersRoot" -ForegroundColor Yellow
    }
}

if ($removed.Count -eq 0) {
    Write-ResetLog 'nothing removed'
    Write-Host 'Nenhum ficheiro de cofre encontrado para apagar.' -ForegroundColor Yellow
} else {
    Write-ResetLog "removed_count: $($removed.Count)"
    foreach ($p in $removed) {
        Write-ResetLog "deleted: $p"
    }
}

Write-Host ''
Write-Host 'Proximo passo:' -ForegroundColor Cyan
Write-Host '  1. Feche o RDrive se estiver aberto.'
Write-Host '  2. Execute Iniciar.bat na raiz do projeto.'
Write-Host '  3. No arranque, defina email de recuperacao e nova senha mestra.'
if (-not $WipeAll) {
    Write-Host '  (drives.json / settings.json legados serao migrados para o novo cofre.)' -ForegroundColor Green
}

Write-ResetLog '==== reset_vault session end ===='
exit 0
