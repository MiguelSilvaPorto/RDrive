#Requires -Version 5.1
<#
.SYNOPSIS
    Remove stale Windows mappings for a drive letter (RDrive / rclone / WNet ghosts).

.PARAMETER Letter
    Drive letter without colon (A-Z). Example: -Letter A

.EXAMPLE
    .\scripts\cleanup_drive_letter.ps1 -Letter A
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z]$')]
    [string] $Letter
)

$ErrorActionPreference = 'Continue'
$Letter = $Letter.ToUpperInvariant()
$Local = "${Letter}:"

Write-Host "RDrive cleanup: letter $Local" -ForegroundColor Cyan

function Invoke-Quiet {
    param([string[]] $Command)
    $label = ($Command -join ' ')
    Write-Host ">> $label"
    & $Command[0] @($Command[1..($Command.Length - 1)])
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
        Write-Host "   exit=$LASTEXITCODE" -ForegroundColor DarkYellow
    }
}

# Orphan rclone mount for this letter
Get-CimInstance Win32_Process -Filter "Name='rclone.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match ' mount ' -and $_.CommandLine -like "*${Local}*" } |
    ForEach-Object {
        Write-Host ">> taskkill /PID $($_.ProcessId) /T /F (rclone orphan)"
        taskkill /PID $_.ProcessId /T /F 2>$null
    }

Invoke-Quiet @('net', 'use', $Local, '/delete', '/y')

$regPath = "HKCU:\Network\$Letter"
if (Test-Path -LiteralPath $regPath) {
    $remote = (Get-ItemProperty -LiteralPath $regPath -Name RemotePath -ErrorAction SilentlyContinue).RemotePath
    if ($remote) {
        Write-Host "Registry RemotePath: $remote"
        Invoke-Quiet @('net', 'use', $remote, '/delete', '/y')
    }
    Write-Host ">> Remove-Item $regPath (HKCU Network profile)"
    Remove-Item -LiteralPath $regPath -Force -ErrorAction SilentlyContinue
}

Invoke-Quiet @('subst', $Local, '/D')

Write-Host "Done. If Explorer still shows a ghost entry, restart Explorer or log off." -ForegroundColor Green
