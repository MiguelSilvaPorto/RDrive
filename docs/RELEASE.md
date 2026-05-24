# Publicar releases no GitHub (RDrive)

## O que os utilizadores recebem hoje

| Asset | Conteúdo | Arranque |
|-------|----------|----------|
| **Source code (zip)** — automático do GitHub | Código na raiz `MiguelSilvaPorto-RDrive-<hash>/`, **sem** `.venv` | `Iniciar.bat` (1.ª vez: venv + pip + rclone; consola **visível** na 1.ª execução) |
| **`RDrive-<tag>-windows.zip`** — **recomendado**, gerado localmente | Pasta `RDrive-<tag>/` com `Iniciar.bat`, `src/`, `scripts/`, etc. | Igual |
| **`RDriveSetup.exe`** — opcional | Staging + Inno Setup | Atalhos → `Iniciar.bat` |

O zip automático **Source code** não inclui ambiente Python nem binários (`rclone-extra`, extensão cookies). O `Iniciar.bat` trata disso na primeira execução (2–5 minutos com Internet).

## Construir o zip para utilizadores

Na raiz do repositório (PowerShell):

```powershell
.\scripts\build\package_release.ps1 -Tag v0.2.2-semi-stable
```

`package_release.ps1` invoca `validate_release.ps1` no staging e no zip final — **falha** se existirem `rclone.conf`, `cookies.txt`, `drives.enc`, perfis `terabox-browser` / `chrome-rdrive-isolated-profile`, `.venv`, etc.

Saída: `dist\RDrive-0.2.0-semi-stable-windows.zip`

## Publicar no GitHub

1. Criar tag (ex.: `v0.2.0-semi-stable`) no ramo adequado (`semi-stable` / `main`).
2. Criar **pré-release** no GitHub Releases com notas.
3. **Anexar** `dist\RDrive-*-windows.zip` (e opcionalmente `dist\RDriveSetup.exe`).
4. Não assumir que o zip **Source code** sozinho substitui o asset Windows — o nome da pasta extraída confunde (`MiguelSilvaPorto-RDrive-…`).

```powershell
gh release create v0.2.1-semi-stable dist\RDrive-0.2.1-semi-stable-windows.zip `
  --prerelease --title "RDrive Semi-stable 0.2.1" --notes-file docs\release-notes-semi-stable.md
```

(Adaptar ficheiro de notas conforme o canal.)

## Instalador `.exe`

```powershell
.\scripts\build\build_installer.ps1
```

Requer [Inno Setup 6](https://jrsoftware.org/isdl.php). Ver `docs/INSTALLER.md`.

## Comportamento do launcher (release)

- **1.ª execução** (sem `.venv`): consola do bootstrap **visível** (`log_launcher.ps1`).
- **Execuções seguintes**: consola oculta; app via `pythonw`.
- **Falha de bootstrap**: caixa de diálogo + `logs\launcher.log` + `logs\.launcher-exit-code` (`1` = falha).
- Variáveis: `RDRIVE_LAUNCHER_VISIBLE=1` (sempre consola), `RDRIVE_LAUNCHER_QUIET=1` (sempre oculto), `RDRIVE_LAUNCHER_DEBUG=1` (pausa em erro no `.bat`).
- **Teste isolado** (sem `%LOCALAPPDATA%\RDrive\` do PC): `Iniciar-Isolado.bat` ou:

```powershell
.\scripts\test\isolated_launch_test.ps1 -ReleaseRoot "C:\caminho\RDrive-0.2.3-semi-stable" -Reset
```

Relatório em `_isolated_test\report\`. Com `-Reset` apaga `.venv` e dados de teste na pasta da release.

### Falhas comuns no bootstrap

| Sintoma em `launcher.log` | Causa | Correção |
|---------------------------|-------|----------|
| `No module named pip` | `.venv` criado a meio (vários `Iniciar.bat` em paralelo) ou venv corrompido | Apagar `.venv`, executar **uma** vez `Iniciar.bat`; 0.2.3+ repõe pip com `ensurepip` |
| `bootstrap em curso noutro processo` | Segundo clique durante a 1.ª instalação | Aguardar; o launcher serializa com lock em `.venv\.launcher-bootstrap.lock` |

## Privacidade (obrigatório)

- Os dados do utilizador ficam em **`%LOCALAPPDATA%\RDrive\`** — **nunca** devem entrar no zip de release.
- Extrair o zip numa pasta **nova** não copia a sessão TeraBox; ver a mesma conta no mesmo PC é normal se `%LOCALAPPDATA%\RDrive` já tinha credenciais.
- Antes de publicar: `.\scripts\build\validate_release.ps1 -Path dist\<zip>` (também corre automaticamente em `package_release.ps1`).

## Checklist antes de publicar

- [ ] `.\scripts\build\package_release.ps1 -Tag <tag>` (inclui validação de segredos)
- [ ] Extrair zip numa pasta limpa → `Iniciar.bat` → confirmar `logs\launcher.log` exit 0 e app na bandeja/janela
- [ ] Asset `*-windows.zip` anexado à release
- [ ] README: link para o asset correto (não só «Source code»)
