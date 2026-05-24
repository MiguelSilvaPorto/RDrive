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
.\scripts\build\validate_installer.ps1
.\scripts\build\package_release.ps1 -Tag v0.2.1-semi-stable
```

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
- **Falha de bootstrap**: caixa de diálogo + `logs\launcher.log`.
- Variáveis: `RDRIVE_LAUNCHER_VISIBLE=1` (sempre consola), `RDRIVE_LAUNCHER_QUIET=1` (sempre oculto), `RDRIVE_LAUNCHER_DEBUG=1` (pausa em erro no `.bat`).

## Checklist antes de publicar

- [ ] `.\scripts\build\validate_installer.ps1`
- [ ] `.\scripts\build\package_release.ps1 -Tag <tag>`
- [ ] Extrair zip numa pasta limpa → `Iniciar.bat` → confirmar `logs\launcher.log` exit 0 e app na bandeja/janela
- [ ] Asset `*-windows.zip` anexado à release
- [ ] README: link para o asset correto (não só «Source code»)
