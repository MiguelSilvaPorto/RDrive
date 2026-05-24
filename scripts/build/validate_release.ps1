#Requires -Version 5.1
<#
.SYNOPSIS
  Falha se um staging ou zip de release contiver dados de utilizador / segredos.

.DESCRIPTION
  Usar antes de anexar assets ao GitHub. Nunca imprime valores de segredos.

.PARAMETER Path
  Pasta de staging (ex. dist\installer-staging) ou ficheiro .zip.

.EXAMPLE
  .\scripts\build\validate_release.ps1 -Path dist\installer-staging
  .\scripts\build\validate_release.ps1 -Path dist\RDrive-0.2.2-semi-stable-windows.zip
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$SensitiveFileNames = @(
    'rclone.conf', '.rclone.conf', 'cookies.txt', 'remembered_vault.blob',
    'drives.json', 'drives.enc', 'settings.json', 'settings.enc',
    'recovery_token.json', 'recovery_profile.json', 'recent.json', '.env'
)

$ForbiddenDirNames = @(
    '.venv', 'venv', 'ENV', 'env', '.git',
    'users', 'session', 'cache', 'mounts', 'webui', 'state',
    'stripe_wal', 'stripe_assembly', 'provider_icons',
    'terabox-browser', 'chrome-rdrive-isolated-profile', 'extensions'
)

# Padrões de conteúdo (não documentação)
$ContentPatterns = @(
    @{ Name = 'ndus_cookie'; Regex = 'ndus=[A-Za-z0-9%+/=_-]{12,}' }
    @{ Name = 'rclone_terabox_section'; Regex = '(?ms)\[[^\]]*terabox[^\]]*\]\s*\r?\n\s*type\s*=\s*terabox' }
    @{ Name = 'rclone_pass'; Regex = '(?m)^pass\s*=\s*\S{4,}' }
    @{ Name = 'netscape_cookies_file'; Regex = '(?m)^\.?[\w.-]+\s+TRUE\s+/\s+FALSE\s+\d+\s+\S+\s+\S+' }
)

$DocPathRe = '(^|[\\/])(docs|tests)([\\/]|$)|README|ARCHITECTURE|\.md$|\.mdc$'

function Test-IsDocPath {
    param([string] $RelativePath)
    return ($RelativePath -replace '\\', '/') -match $DocPathRe
}

function Get-ScanRoots {
    param([string] $TargetPath)
    $resolved = Resolve-Path -LiteralPath $TargetPath
    if ((Get-Item -LiteralPath $resolved).PSIsContainer) {
        return @($resolved.Path)
    }
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("rdrive-validate-" + [guid]::NewGuid().ToString('N'))
    Expand-Archive -LiteralPath $resolved.Path -DestinationPath $temp -Force
    $inner = Get-ChildItem -LiteralPath $temp -Directory | Select-Object -First 1
    if ($inner) { return @($inner.FullName) }
    return @($temp)
}

function Test-ForbiddenNames {
    param([string] $Root)
    $issues = [System.Collections.Generic.List[string]]::new()
    Get-ChildItem -LiteralPath $Root -Recurse -Force | ForEach-Object {
        $rel = $_.FullName.Substring($Root.Length).TrimStart('\', '/')
        $parts = $rel -split '[\\/]'
        foreach ($part in $parts) {
            if ($ForbiddenDirNames -contains $part) {
                $issues.Add("FORBIDDEN_DIR: $rel")
                return
            }
        }
        if (-not $_.PSIsContainer -and ($SensitiveFileNames -contains $_.Name)) {
            $issues.Add("FORBIDDEN_FILE: $rel")
        }
        if (-not $_.PSIsContainer -and $_.Name -eq 'Cookies' -and $rel -match 'terabox-browser|chrome-rdrive|Network') {
            $issues.Add("FORBIDDEN_BROWSER_COOKIE: $rel")
        }
    }
    return $issues
}

function Test-ForbiddenContent {
    param([string] $Root)
    $issues = [System.Collections.Generic.List[string]]::new()
    Get-ChildItem -LiteralPath $Root -Recurse -File -Force | ForEach-Object {
        if ($_.Length -gt 8MB) { return }
        $rel = $_.FullName.Substring($Root.Length).TrimStart('\', '/')
        if (Test-IsDocPath -RelativePath $rel) { return }
        $ext = $_.Extension.ToLower()
        if ($ext -in @('.svg', '.ico', '.png', '.jpg', '.jpeg', '.woff', '.woff2', '.pyc', '.exe', '.dll', '.pyd')) {
            return
        }
        try {
            $text = [IO.File]::ReadAllText($_.FullName)
        }
        catch {
            return
        }
        foreach ($pat in $ContentPatterns) {
            if ($text -match $pat.Regex) {
                $issues.Add("FORBIDDEN_CONTENT[$($pat.Name)]: $rel")
                return
            }
        }
    }
    return $issues
}

$scanRoots = Get-ScanRoots -TargetPath $Path
$allIssues = [System.Collections.Generic.List[string]]::new()
foreach ($root in $scanRoots) {
    (Test-ForbiddenNames -Root $root) | ForEach-Object { $allIssues.Add($_) }
    (Test-ForbiddenContent -Root $root) | ForEach-Object { $allIssues.Add($_) }
}

if ($allIssues.Count -gt 0) {
    Write-Error "[validate_release] FAIL: $($allIssues.Count) privacy/secret issue(s):"
    $allIssues | Select-Object -First 40 | ForEach-Object { Write-Host "  $_" }
    if ($allIssues.Count -gt 40) {
        Write-Host "  ... and $($allIssues.Count - 40) more"
    }
    exit 1
}

Write-Host "[validate_release] OK: no sensitive files/patterns in: $Path"
exit 0
