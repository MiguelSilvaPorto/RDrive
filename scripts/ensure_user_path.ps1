# Persist a directory on the user PATH if missing (used by Iniciar.bat).
param(
    [Parameter(Mandatory = $true)]
    [string]$TargetDir
)

$target = $TargetDir.Trim().TrimEnd('\')
if (-not $target) {
    exit 1
}

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$parts = @()
if ($userPath) {
    $parts = $userPath -split ';' | Where-Object { $_ -and $_.Trim() -ne '' }
}

foreach ($p in $parts) {
    if ($p.TrimEnd('\') -ieq $target) {
        Write-Output 'EXISTS'
        exit 0
    }
}

$new = if ([string]::IsNullOrWhiteSpace($userPath)) { $target } else { $userPath.TrimEnd(';') + ';' + $target }
[Environment]::SetEnvironmentVariable('Path', $new, 'User')
Write-Output 'ADDED'
