#Requires -Version 5.1
<#
.SYNOPSIS
  Diagnostico e instrucoes para rclone com backend TeraBox (Windows).

.DESCRIPTION
  O rclone oficial nao inclui terabox. Este script NAO descarrega binarios.
  Ver README.md secao Instalar rclone com TeraBox.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$PrUrl = 'https://github.com/rclone/rclone/pull/8508'
$ReadmeSection = 'Instalar rclone com TeraBox'

function Write-Step([string]$Text) {
    Write-Host ''
    Write-Host $Text -ForegroundColor Cyan
}

Write-Host '=== RDrive - rclone + backend TeraBox ===' -ForegroundColor Yellow
Write-Host "PR comunitario: $PrUrl"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Bundled = Join-Path $ProjectRoot 'tools\rclone-extra\rclone.exe'
if (Test-Path $Bundled) {
    Write-Host "Binario local: $Bundled" -ForegroundColor DarkGray
} else {
    Write-Host 'Binario local ausente: tools\rclone-extra\rclone.exe (copie do release TeraBox).' -ForegroundColor DarkYellow
}

$rcloneCmd = Get-Command rclone -ErrorAction SilentlyContinue
if (-not $rcloneCmd) {
    Write-Step 'rclone nao encontrado no PATH.'
    Write-Host 'Instale rclone e depois substitua rclone.exe por um build com TeraBox.'
    Write-Host "README: secao $ReadmeSection"
    exit 2
}

Write-Step "rclone no PATH: $($rcloneCmd.Source)"
try {
    & rclone version 2>&1 | ForEach-Object { Write-Host "  $_" }
}
catch {
    Write-Host "  (nao foi possivel obter versao: $_)" -ForegroundColor DarkYellow
}

Write-Step 'Backends disponiveis (procura terabox):'
$backendsRaw = & rclone help backends 2>&1
$teraboxLine = $backendsRaw | Select-String -Pattern '^\s*terabox\s' -CaseSensitive:$false
if ($null -ne $teraboxLine) {
    Write-Host "  OK - $($teraboxLine.Line.Trim())" -ForegroundColor Green
    Write-Host ''
    Write-Host 'Backend TeraBox detetado. Pode usar Adicionar unidade - TeraBox no RDrive.'
    exit 0
}

Write-Host '  Backend terabox NAO encontrado.' -ForegroundColor Red
Write-Host ''
Write-Host 'Passos manuais (Windows):' -ForegroundColor Yellow
Write-Host '  1. Abra o PR comunitario e escolha um fork/release com backend terabox:'
Write-Host "     $PrUrl"
Write-Host '  2. Descarregue o ZIP Windows amd64 do release (ex.: rclone-extra-fork).'
Write-Host '  3. Feche o RDrive. Faca backup do rclone.exe atual:'
Write-Host "     Copy-Item '$($rcloneCmd.Source)' '$($rcloneCmd.Source).bak'"
Write-Host '  4. Copie o rclone.exe do ZIP para a mesma pasta do passo 3.'
Write-Host '  5. Confirme: rclone help backends | findstr /i terabox'
Write-Host '  6. Reinicie o RDrive.'
Write-Host ''
Write-Host 'Nao existe pacote winget/chocolatey fiavel com TeraBox - substituicao manual do .exe.'
Write-Host "Detalhes: README.md secao $ReadmeSection"
exit 1
