# Detached RDrive restart — same layout as Iniciar.bat (Start-Process pythonw).
param(
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"

function Write-RestartLog {
    param([string]$Message)
    if (-not $script:LogPath) { return }
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    try {
        Add-Content -LiteralPath $script:LogPath -Value $line -Encoding UTF8
    } catch { }
}

function Resolve-ProjectRoot {
    param([string]$Hint)
    if ($Hint -and (Test-Path -LiteralPath $Hint)) {
        return (Resolve-Path -LiteralPath $Hint).Path
    }
    $dir = $PSScriptRoot
    while ($dir) {
        if (Test-Path -LiteralPath (Join-Path $dir "Iniciar.bat")) {
            return (Resolve-Path -LiteralPath $dir).Path
        }
        $parent = Split-Path -Parent $dir
        if (-not $parent -or $parent -eq $dir) { break }
        $dir = $parent
    }
    throw "RDrive project root not found"
}

try {
    $root = Resolve-ProjectRoot -Hint $ProjectRoot
    $script:LogPath = Join-Path $root "logs\restart.log"
    $logDir = Split-Path -Parent $script:LogPath
    if (-not (Test-Path -LiteralPath $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }

    Write-RestartLog "restart_rdrive.ps1 begin root=$root"

    $pyw = Join-Path $root ".venv\Scripts\pythonw.exe"
    $env:RDRIVE_PROJECT_ROOT = $root
    if (-not $env:RDRIVE_UI) {
        $env:RDRIVE_UI = "ctk"
    }
    $srcPath = Join-Path $root "src"
    if ($env:PYTHONPATH) {
        $env:PYTHONPATH = "$srcPath;$env:PYTHONPATH"
    } else {
        $env:PYTHONPATH = $srcPath
    }

    $pwdSet = if ($env:RDRIVE_MASTER_PASSWORD) { "yes" } else { "no" }
    Write-RestartLog "env PYTHONPATH set session_password=$pwdSet"

    if (-not (Test-Path -LiteralPath $pyw)) {
        Write-RestartLog "ERROR pythonw not found: $pyw"
        Write-Error "pythonw not found: $pyw"
        exit 1
    }

    $proc = Start-Process -FilePath $pyw -ArgumentList @("-m", "rdrive") -WorkingDirectory $root -WindowStyle Hidden -PassThru
    Write-RestartLog "Start-Process ok pid=$($proc.Id) pythonw=$pyw"
    Write-Output "pid=$($proc.Id)"
    exit 0
} catch {
    Write-RestartLog "ERROR $_"
    Write-Error $_
    exit 1
}
