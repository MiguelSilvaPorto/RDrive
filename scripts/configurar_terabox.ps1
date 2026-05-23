#Requires -Version 5.1
<#
.SYNOPSIS
  Configura remote TeraBox e testa ligação (rclone-extra com backend terabox).

.DESCRIPTION
  1. Indica como obter cookie via RDrive (navegador integrado — sem F12)
  2. Pede cookie colado (exportado do RDrive ou extensão noutro browser)
  3. Cria remote rclone e lista ficheiros na raiz
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Rclone = Join-Path $ProjectRoot 'tools\rclone-extra\rclone.exe'
if (-not (Test-Path $Rclone)) {
    Write-Host '[ERRO] rclone-extra nao encontrado. Execute:' -ForegroundColor Red
    Write-Host "  powershell -File `"$ProjectRoot\scripts\install_rclone_terabox.ps1`"" -ForegroundColor Yellow
    exit 2
}

$RemoteName = 'terabox_pessoal'
if ($args.Count -ge 1 -and $args[0]) { $RemoteName = $args[0].Trim() }

Write-Host '=== RDrive — Configurar TeraBox ===' -ForegroundColor Cyan
Write-Host "rclone: $Rclone"
& $Rclone version | Select-Object -First 1

Write-Host ''
Write-Host 'Como obter o cookie (sem F12 — o site TeraBox bloqueia DevTools):' -ForegroundColor Cyan
Write-Host '  RECOMENDADO: RDrive -> Adicionar unidade -> TeraBox -> «Login e capturar cookie»'
Write-Host '    (navegador integrado; sessao guardada; captura automatica em /main)'
Write-Host ''
Write-Host '  Alternativa: exporte o cookie de outro browser (extensao de exportacao)'
Write-Host '    e cole abaixo. NAO use F12 no terabox.com — o site fecha e bloqueia.'
Write-Host ''

$cookie = Read-Host 'Cole aqui o Cookie (Enter para cancelar)'
if ([string]::IsNullOrWhiteSpace($cookie)) {
    Write-Host 'Cancelado.' -ForegroundColor DarkYellow
    exit 0
}

$cookie = $cookie.Trim()
if ($cookie -match '^\s*cookie\s*:\s*(.+)$') { $cookie = $Matches[1].Trim() }

if ($cookie -notmatch 'ndus=') {
    Write-Host '[AVISO] O cookie nao parece conter ndus=. Pode falhar.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host "A criar remote «$RemoteName»..." -ForegroundColor Cyan
$createArgs = @(
    'config', 'create', $RemoteName, 'terabox',
    'cookie', $cookie,
    '--non-interactive', '--obscure'
)
& $Rclone @createArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERRO] rclone config create falhou.' -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ''
Write-Host 'A testar ligacao (rclone lsd)...' -ForegroundColor Cyan
& $Rclone lsd "${RemoteName}:" --timeout 2m
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERRO] Teste falhou. Cookie pode ter expirado — repita apos novo login.' -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ''
Write-Host '[OK] TeraBox ligado. Remote:' "${RemoteName}:" -ForegroundColor Green
Write-Host ''
Write-Host 'Proximo passo no RDrive:' -ForegroundColor Cyan
Write-Host '  1. Feche o RDrive se estiver aberto e reinicie com Iniciar.bat'
Write-Host "  2. Adicionar unidade -> TeraBox -> remote: $RemoteName"
Write-Host '  3. Ative Montar na lista de unidades'
Write-Host ''
Write-Host 'Montagem manual (teste rapido, letra T:):' -ForegroundColor DarkGray
Write-Host "  & `"$Rclone`" mount ${RemoteName}: T: --vfs-cache-mode full"

exit 0
