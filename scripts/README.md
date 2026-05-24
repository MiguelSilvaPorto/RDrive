# Scripts RDrive

Automação Windows (PowerShell) e utilitários Python **fora** do runtime do app.
O launcher mestre continua na raiz: **`Iniciar.bat`**.

## Pastas

| Pasta | Propósito |
|-------|-----------|
| **`launchers/`** | Atalhos `.bat` de duplo-clique (TeraBox, DevStatic, …). Um `.bat` por fluxo; delegam para `.ps1`/`.py` nas subpastas. |
| **`bootstrap/`** | Arranque: verificação PyQt6-WebEngine, instalação da extensão cookies «Get cookies.txt LOCALLY» (Edge). Chamado por `Iniciar.bat` e pelo fluxo TeraBox. |
| **`terabox/`** | rclone-extra (build PR #8508), Chrome dedicado, montagem manual, assistente de cookie, GUI de importação. |
| **`maintenance/`** | Log do launcher, reinício assíncrono, PATH do utilizador, libertar letra de unidade, repor cofre `.enc`. |
| **`dev/`** | Branding (`build_app_icons`), SVGs de provedores (`fetch_provider_icons`, `sync_static_providers`). |

## Entradas frequentes

| Objetivo | Comando |
|----------|---------|
| Iniciar app | `Iniciar.bat` (raiz) |
| Dev WebUI + live reload | `scripts\launchers\DevStatic-Live.bat` |
| Preview Static no browser | `scripts\launchers\DevStatic-Browser.bat` |
| Verificar WebEngine | `.\scripts\bootstrap\verify_webengine.ps1` |
| Instalar rclone TeraBox | `.\scripts\terabox\install_rclone_terabox.ps1` |
| Repor cofre | `scripts\maintenance\reset_vault.bat` |
| Espelhar ícones → Static | `python scripts\dev\sync_static_providers.py` |

Mapa completo de pastas do repo: `docs/ESTRUTURA.md` §4–5.
