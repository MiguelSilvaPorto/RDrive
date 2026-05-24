# RDrive launcher logger — streams batch stdout/stderr to launcher.log in real time
param(
    [Parameter(Mandatory = $true)]
    [string]$BatPath
)

$ErrorActionPreference = 'Continue'

function Get-ProjectRoot {
    if ($env:RDRIVE_PROJECT_ROOT) {
        $fromEnv = $env:RDRIVE_PROJECT_ROOT.Trim()
        if ($fromEnv -and (Test-Path -LiteralPath $fromEnv)) {
            return (Resolve-Path -LiteralPath $fromEnv).Path
        }
    }
    return (Split-Path -Parent $BatPath)
}

$projectRoot = Get-ProjectRoot
$logDir = Join-Path $projectRoot 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir 'launcher.log'

function Write-LauncherLog {
    param([string]$Message)
    if ([string]::IsNullOrWhiteSpace($Message)) { return }
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $logFile -Value "[$ts] $Message" -Encoding UTF8
}

function Emit-LauncherLines {
    param(
        [string[]]$Lines
    )
    foreach ($line in $Lines) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        Write-Host $line
        Write-LauncherLog $line
    }
}

function Read-NewFileLines {
    param(
        [string]$Path,
        [ref]$Offset
    )
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try {
        if ($Offset.Value -gt $stream.Length) { $Offset.Value = 0 }
        $stream.Seek($Offset.Value, [System.IO.SeekOrigin]::Begin) | Out-Null
        $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8, $true)
        $chunk = $reader.ReadToEnd()
        $Offset.Value = $stream.Length
    }
    finally {
        $stream.Dispose()
    }
    if ([string]::IsNullOrEmpty($chunk)) { return @() }
  return ($chunk -split "`r?`n")
}

Write-LauncherLog '==== RDrive launcher session start ===='
Write-LauncherLog "launcher cwd: $(Get-Location)"
Write-LauncherLog "PYTHONPATH env: $env:PYTHONPATH"

if (-not (Test-Path -LiteralPath $BatPath)) {
    Write-LauncherLog "ERROR bat not found: $BatPath"
    Write-Host "[ERRO] Script launcher nao encontrado: $BatPath"
    exit 1
}

$batDir = Split-Path -Parent $BatPath
$venvPythonw = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$firstRun = -not (Test-Path -LiteralPath $venvPythonw)
$forceQuiet = ($env:RDRIVE_LAUNCHER_QUIET -eq '1')
$forceVisible = ($env:RDRIVE_LAUNCHER_VISIBLE -eq '1')
if ($forceQuiet) {
    $cmdWindowStyle = 'Hidden'
} elseif ($forceVisible -or $firstRun) {
    $cmdWindowStyle = 'Normal'
    if ($firstRun) {
        Write-LauncherLog 'first run — launcher console visible (bootstrap may take several minutes)'
        Write-Host '[RDrive] Primeira execucao: aguarde o bootstrap (venv, pip, rclone)...'
    }
} else {
    $cmdWindowStyle = 'Hidden'
}

$transcript = Join-Path $env:TEMP "rdrive-launcher-$PID.out"
$stderrFile = Join-Path $env:TEMP "rdrive-launcher-$PID.err"
$exitCode = 1
$stdoutOffset = 0
$stderrOffset = 0

Remove-Item -LiteralPath $transcript, $stderrFile -Force -ErrorAction SilentlyContinue

Push-Location $batDir
$previousWrapped = $env:RDRIVE_LAUNCHER_WRAPPED
$env:RDRIVE_LAUNCHER_WRAPPED = '1'
try {
    # Redirect cmd output to files (not live pipes) so pythonw does not block the launcher.
    # Tail files while cmd runs so launcher.log updates during long winget/bootstrap steps.
    $proc = Start-Process -FilePath 'cmd.exe' `
        -ArgumentList '/c', "`"$BatPath`"" `
        -WorkingDirectory $batDir `
        -WindowStyle $cmdWindowStyle -PassThru `
        -RedirectStandardOutput $transcript `
        -RedirectStandardError $stderrFile

    while (-not $proc.HasExited) {
        Emit-LauncherLines (Read-NewFileLines -Path $transcript -Offset ([ref]$stdoutOffset))
        Emit-LauncherLines (Read-NewFileLines -Path $stderrFile -Offset ([ref]$stderrOffset))
        Start-Sleep -Milliseconds 250
    }

    $proc.WaitForExit() | Out-Null
    $rawExit = $proc.ExitCode
    if ($null -eq $rawExit) {
        $exitCode = 0
    } else {
        $exitCode = [int]$rawExit
    }

    Emit-LauncherLines (Read-NewFileLines -Path $transcript -Offset ([ref]$stdoutOffset))
    Emit-LauncherLines (Read-NewFileLines -Path $stderrFile -Offset ([ref]$stderrOffset))
}
catch {
    Write-LauncherLog "ERROR launcher exception: $_"
    Write-Host "[ERRO] Excecao no launcher: $_"
    $exitCode = 1
}
finally {
    if ($null -eq $previousWrapped) {
        Remove-Item Env:RDRIVE_LAUNCHER_WRAPPED -ErrorAction SilentlyContinue
    } else {
        $env:RDRIVE_LAUNCHER_WRAPPED = $previousWrapped
    }
    Pop-Location
    Remove-Item -LiteralPath $transcript, $stderrFile -Force -ErrorAction SilentlyContinue
}

Write-LauncherLog "==== RDrive launcher exit code: $exitCode ===="

if ($exitCode -ne 0) {
    $hint = "Bootstrap falhou (codigo $exitCode). Ver logs\launcher.log em:`n$projectRoot"
    Write-Host "[ERRO] $hint"
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        [System.Windows.Forms.MessageBox]::Show(
            $hint,
            'RDrive — erro ao iniciar',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
    } catch {
        Write-LauncherLog "ERROR could not show failure dialog: $_"
    }
}

exit $exitCode
