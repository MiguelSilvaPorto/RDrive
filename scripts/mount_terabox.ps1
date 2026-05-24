#Requires -Version 5.1
<#
.SYNOPSIS
  Monta TeraBox manualmente via rclone-extra (cookie de sessao).

.DESCRIPTION
  1. Valida rclone-extra + backend terabox + WinFsp
  2. Cookie: variavel TERABOX_COOKIE, remote existente, ou Read-Host interativo
  3. Cria/atualiza remote, testa lsd, monta numa letra livre

  NOTA: nao e possivel ler cookies do Chrome a partir de outro processo.
  Use o navegador integrado RDrive (Adicionar -> TeraBox) ou cole cookie exportado.

.PARAMETER RemoteName
  Nome do remote rclone (predefinido: terabox_pessoal).

.PARAMETER Letter
  Letra de montagem (ex.: T). Se omitido, escolhe a primeira livre (A-Z).

.PARAMETER SkipMount
  Apenas configura remote e testa lsd (nao monta).

.EXAMPLE
  $env:TERABOX_COOKIE = 'ndus=...; outros=...'
  .\scripts\mount_terabox.ps1

.EXAMPLE
  .\scripts\mount_terabox.ps1 -Letter T
#>
[CmdletBinding()]
param(
    [string] $RemoteName = 'terabox_pessoal',
    [ValidatePattern('^[A-Za-z]$')]
    [string] $Letter = '',
    [switch] $SkipMount
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Rclone = if ($env:RDRIVE_RCLONE_EXE -and (Test-Path $env:RDRIVE_RCLONE_EXE)) {
    $env:RDRIVE_RCLONE_EXE
} else {
    Join-Path $ProjectRoot 'tools\rclone-extra\rclone.exe'
}

function Write-Step([string]$Text, [string]$Color = 'Cyan') {
    Write-Host ''
    Write-Host $Text -ForegroundColor $Color
}

function Test-WinFspInstalled {
    foreach ($key in @('HKLM:\SOFTWARE\WinFsp', 'HKLM:\SOFTWARE\WOW6432Node\WinFsp')) {
        if (Test-Path $key) { return $true }
    }
    $dll = Join-Path ${env:ProgramFiles(x86)} 'WinFsp\bin\winfsp-x64.dll'
    if (Test-Path $dll) { return $true }
    return $false
}

function Get-FreeDriveLetter {
    param([string[]] $Prefer = @('T', 'U', 'V', 'W', 'X', 'Y', 'Z'))
    $used = @(Get-PSDrive -PSProvider FileSystem | ForEach-Object { $_.Name.ToUpperInvariant() })
    foreach ($candidate in $Prefer) {
        if ($candidate -notin $used) { return $candidate }
    }
    foreach ($ch in ([char[]]([char]'A'..[char]'Z'))) {
        $name = [string]$ch
        if ($name -notin $used) { return $name }
    }
    throw 'Nenhuma letra de unidade livre (A-Z).'
}

function Get-RemoteExists([string]$Name) {
    $conf = Join-Path $env:APPDATA 'rclone\rclone.conf'
    if (-not (Test-Path $conf)) { return $false }
    return (Select-String -Path $conf -Pattern "^\[$([regex]::Escape($Name))\]\s*$" -Quiet)
}

Write-Host '=== RDrive - Montar TeraBox (manual) ===' -ForegroundColor Yellow

if (-not (Test-Path $Rclone)) {
    Write-Host '[ERRO] rclone-extra nao encontrado.' -ForegroundColor Red
    Write-Host "  Esperado: $Rclone" -ForegroundColor DarkGray
    Write-Host '  Veja README secao Instalar rclone com TeraBox.' -ForegroundColor Yellow
    exit 2
}

Write-Step "rclone: $Rclone"
& $Rclone version | Select-Object -First 1

$backends = & $Rclone help backends 2>&1
if (-not ($backends | Select-String -Pattern '^\s*terabox\s' -Quiet)) {
    Write-Host '[ERRO] Backend terabox ausente neste rclone.exe.' -ForegroundColor Red
    exit 3
}
Write-Host '  OK - backend terabox disponivel.' -ForegroundColor Green

if (-not $SkipMount -and -not (Test-WinFspInstalled)) {
    Write-Host '[ERRO] WinFsp nao instalado - necessario para rclone mount no Windows.' -ForegroundColor Red
    Write-Host '  Instale: winget install --id WinFsp.WinFsp -e' -ForegroundColor Yellow
    Write-Host '  https://winfsp.dev/rel/' -ForegroundColor DarkGray
    exit 4
}

$cookie = ''
if ($env:TERABOX_COOKIE) { $cookie = $env:TERABOX_COOKIE.Trim() }
if ($cookie -match '^\s*cookie\s*:\s*(.+)$') { $cookie = $Matches[1].Trim() }

$remoteExists = Get-RemoteExists $RemoteName

if (-not $cookie -and -not $remoteExists) {
    Write-Step 'Cookie TeraBox necessario' 'Yellow'
    Write-Host 'Nao e possivel ler cookies do Chrome a partir de outro processo (isolamento do browser).'
    Write-Host ''
    Write-Host 'Opcoes:' -ForegroundColor Cyan
    Write-Host '  A) RDrive -> Adicionar -> TeraBox -> «Login e capturar cookie» (recomendado)'
    Write-Host '  B) Execute scripts\launchers\Configurar-TeraBox.bat e cole cookie exportado (sem F12 no TeraBox)'
    Write-Host '  C) Defina TERABOX_COOKIE com cookie exportado de extensao noutro browser'
    Write-Host '     (NAO use F12 no terabox.com — o site bloqueia DevTools)'
    Write-Host ''
    Write-Host 'Para este script: defina TERABOX_COOKIE ou cole abaixo.' -ForegroundColor DarkGray
    if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        try {
            $cookie = Read-Host 'Cole o Cookie (Enter para sair)'
        } catch {
            Write-Host '[ERRO] TERABOX_COOKIE nao definido e terminal nao interativo.' -ForegroundColor Red
            exit 5
        }
        if ([string]::IsNullOrWhiteSpace($cookie)) {
            Write-Host 'Cancelado - montagem nao iniciada.' -ForegroundColor DarkYellow
            exit 0
        }
        $cookie = $cookie.Trim()
        if ($cookie -match '^\s*cookie\s*:\s*(.+)$') { $cookie = $Matches[1].Trim() }
    } else {
        Write-Host '[ERRO] TERABOX_COOKIE nao definido e terminal nao interativo.' -ForegroundColor Red
        exit 5
    }
}

if ($cookie) {
    if ($cookie -notmatch 'ndus=') {
        Write-Host '[AVISO] Cookie sem ndus= - a ligacao pode falhar.' -ForegroundColor Yellow
    }
    Write-Step "A criar/atualizar remote '$RemoteName'..."
    if ($remoteExists) {
        & $Rclone config delete $RemoteName --non-interactive 2>$null
    }
    & $Rclone config create $RemoteName terabox cookie $cookie --non-interactive --obscure
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[ERRO] rclone config create falhou.' -ForegroundColor Red
        exit $LASTEXITCODE
    }
} elseif (-not $remoteExists) {
    Write-Host "[ERRO] Remote '$RemoteName' nao existe e nenhum cookie foi fornecido." -ForegroundColor Red
    exit 6
} else {
    Write-Host "A usar remote existente '$RemoteName' (sem alterar cookie)." -ForegroundColor DarkGray
}

Write-Step 'A testar ligacao (rclone lsd)...'
& $Rclone lsd "${RemoteName}:" --timeout 2m
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERRO] Teste falhou - cookie expirado ou rede instavel.' -ForegroundColor Red
    Write-Host 'Obtenha cookie novo no navegador integrado RDrive ou exporte de outro browser.' -ForegroundColor Yellow
    exit $LASTEXITCODE
}
Write-Host '[OK] Ligacao TeraBox confirmada.' -ForegroundColor Green

if ($SkipMount) {
    Write-Host ''
    Write-Host "Remote pronto: ${RemoteName}: - montagem ignorada (-SkipMount)." -ForegroundColor Green
    exit 0
}

if (-not $Letter) {
    $Letter = Get-FreeDriveLetter
} else {
    $Letter = $Letter.ToUpperInvariant()
}

$MountPoint = "${Letter}:"
Write-Step "A montar ${RemoteName}: em $MountPoint (Ctrl+C para desmontar)..."

$mountArgs = @(
    'mount', "${RemoteName}:", $MountPoint,
    '--vfs-cache-mode', 'full',
    '--dir-cache-time', '12h',
    '--poll-interval', '1m'
)
Write-Host "Comando: $Rclone $($mountArgs -join ' ')" -ForegroundColor DarkGray
& $Rclone @mountArgs
