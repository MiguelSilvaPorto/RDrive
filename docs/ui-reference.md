# UI Reference (RDrive)

This document tracks the target UX inspired by RaiDrive while preserving
RDrive-specific safety/experimental controls.

> A partir desta revisão o projeto suporta **duas camadas de UI**:
>
> - **WebUI premium** (HTML/CSS/JS) embutida via `QWebEngineView` —
>   padrão com `RDRIVE_WEBUI=1` (ou omitida). Fonte única:
>   [Static/](../Static/) (`index.html`, `css/`, `script.js`).
>   Dev live reload: `scripts\launchers\DevStatic-Live.bat` (`RDRIVE_STATIC_LIVE=1`).
> - **UI nativa PyQt6** (legada) — `RDRIVE_WEBUI=0` ou fallback se
>   `Static/` indisponível / WebEngine ausente.

## WebUI — lista pós-adição de unidade (referência visual)

A tela principal, depois de adicionar pelo menos uma unidade, deve ficar
visualmente idêntica à imagem alvo:

- Chrome único `drive-list-chrome` (gradiente dark, borda translúcida,
  cantos arredondados) com header interno e sparkle no canto inferior
  direito.
- Header e linhas usando o mesmo `grid-template-columns`:
  `minmax(172px, 1.4fr) minmax(118px, 1fr) minmax(84px, 0.7fr) minmax(156px, 1.2fr) minmax(124px, 1fr) minmax(252px, 1.8fr)`.
- Padding horizontal idêntico via token `--col-pad-x: 10px`.
- Colunas: **Provedor**, **Nome**, **Ponto**, **Estado**, **Integridade**, **Ações**.
- Pill `Estado`: superfície escura, ícone power neutro, texto com elide
  (`Desligar`, `A conectar…`, etc.) e variantes por `data-state` na
  `.drive-row` (`connected`, `connecting`, `disconnecting`, `error`).
- Pill `Integridade`: gradiente verde com glow real (`var(--glow-success)`)
  para `data-level="ok"`; âmbar para `warning`; vermelho para `error`.
- Ações: bloco esquerdo com dois `slide-switch` (Montar unidade, Iniciar
  com o Windows), bolinha que desliza esquerda/direita; bloco direito com
  links inline `Editar · Excluir` (lápis e lixeira).
- Breakpoints: < 980px reduz coluna Provedor; < 820px esconde Ponto e
  mostra a letra como subtítulo do Nome.

Regras transversais:

- Animações limitadas a `transform/opacity` (160–360 ms).
- Nenhuma cor hardcoded em regras de linha — apenas tokens.
- Acessibilidade: `aria-checked` nos switches, `aria-label` nos pills.

## Main Window

- **Single-window navigation:** `MainWindow` uses a central `QStackedWidget` with four pages — lista de unidades, adicionar, definições e editar. Toolbar actions switch pages instead of opening modal dialogs. Secondary pages show a **← Unidades** back control; the window title updates per page (`RDrive — Adicionar unidade`, etc.).
- **Infinite border chrome (Windows):** frameless shell with animated conical gradient
  perimeter (`--primary` blue tones), rounded corners, custom title bar (drag + min/max/close),
  and native resize hit-testing via `WM_NCHITTEST`. Implemented via `InfiniteBorderFrame` in
  `window_chrome.py` — `InfiniteBorderMainWindow` for the shell window; `InfiniteBorderDialog`
  for modal top-level dialogs.
- **Linux fallback:** native window decorations with a subtle static border (same tokens as main window).
- **Dialogs with infinite border:** `UnlockVaultDialog`, `RemoteSetupDialog`, `TransferJobsDialog`,
  `PasswordResetDialog`. Still use native/`DarkTitleBarMixin` chrome: legacy modal wrappers
  (`SettingsDialog`, `NewDriveDialog`, `EditDriveDialog`) and all `QMessageBox` prompts.
- **Embedded stack pages** (Adicionar, Definições, Editar): no extra outer margins on the central
  stack — content fills the inner chrome area; animated border only on `MainWindow` contour.
- Top toolbar:
  - `Adicionar`
  - `Definições`
- Drive table columns:
  - Provider
  - Name
  - Mountpoint
  - **Estado** — `StatusPill` (chip colorido; ver secção abaixo)
  - Integridade
  - **Ações** — `GhostActionButton` + `MinimalToggleSwitch` (sem botões ON/OFF)
- Toolbar principal mantém `SmoothButton` (sombra suave); ações de linha **não** usam `SmoothButton`.
- **Painel Atividade (drawer):** feed de eventos do watchdog e resumo «Para você» ficam num painel lateral direito (`ActivityPanel`, 320px), fechado por defeito. Abrir via botão ghost **Atividade** na toolbar ou clique no chip de stats («Watchdog: ativo …»). A página lista fica só com título, chip de estado e tabela em altura total.

## Painel Atividade

Componente: `ui/widgets/activity_panel.py` (`#activityPanel` em `ui/chrome/theme.py`).

| Elemento | Função |
|----------|--------|
| Botão toolbar **Atividade** | `#ghostToolbarButton` — toggle do drawer; estado activo com property `active=true` |
| Chip stats (topo) | `#statsChipButton` — clique abre o drawer |
| Feed watchdog | `#watchdogFeed` — eventos técnicos do watchdog |
| Checkbox **Para você** | Alterna para `#humanEventsFeed` (human.log) |
| **Reiniciar app agora** | `#activityRestartButton` — visível quando hot-reload exige reinício |

Navegação: lista (stack 0) → **Atividade** ou chip stats → drawer lateral; **×** ou segundo clique em **Atividade** fecha.

## Controles de estado

Componentes em `ui/widgets/status_widgets.py`, estilos em `ui/chrome/theme.py` (`#statusPill`, `#minimalSwitch`, `#ghostActionButton`).

| Componente | Uso | Notas |
|------------|-----|--------|
| `StatusPill` | Coluna **Estado** da tabela de unidades | Variantes: `connected` (verde), `connecting` / `disconnecting` (âmbar, animação suave), `disconnected` (cinza), `error` (vermelho). Textos PT: «Conectado», «A conectar…», etc. |
| `GhostActionButton` | **Conectar** / **Desconectar**, **Editar**, **Excluir** na tabela | Link-style; estado transitório só no pill, não no rótulo do botão. |
| `MinimalToggleSwitch` | «Conectar agora» em novo drive; modo sessão em editar; checkboxes das definições | Track iOS-like (`#minimalSwitch`). |

**Antes:** botões `SmoothButton` com texto mutável («Conectando…», estados ON/OFF) — pesados e redundantes com o estado real.

**Depois:** pill na coluna Estado + ação mínima na coluna Ações + switch para preferências booleanas.

Altura de linha da tabela: **56px** (`_TABLE_ROW_MIN_HEIGHT`). Grade de provedores inalterada.

## Provider icons

- SVGs em `src/rdrive/assets/providers/` por **tipo de backend** (não espelha abas Pessoal/Empresarial da UI):

  | Subpasta | Conteúdo |
  |----------|----------|
  | `cloud/` | SaaS — Drive, Dropbox, OneDrive, Box, Mega, pCloud, SharePoint, … |
  | `storage/` | Object storage — S3, B2, GCS, Azure Blob, … |
  | `protocol/` | WebDAV, SFTP, FTP, SMB, HDFS, … |
  | `local/` | Local, alias, mount |
  | `_fallback/` | `generic.svg` quando não há ícone específico |

- Cores de marca aproximadas (não-oficiais). Resolução em `ui/widgets/provider_icons.py`: `_ICON_STEMS` (slug rclone → stem do ficheiro) + índice recursivo das subpastas via `importlib.resources`.
- Aparecem na grade (`provider_grid`), chip «Provedor selecionado» (`new_drive_dialog`) e coluna Provedor da tabela principal.

### Categorias da grade (chips)

- Filtros **Pessoal**, **Empresarial**, **Local** e **Protocolo** em `ui/widgets/provider_grid.py` (`categories_for_backend`).
- Um backend pode pertencer a **várias** categorias (união, não exclusivo): ex. `onedrive` e `drive` aparecem em Pessoal **e** Empresarial; `s3` em Empresarial **e** Protocolo.
- «Mais usados» na aba Empresarial usa `POPULAR_BUSINESS_SLUGS` (OneDrive, SharePoint, Google Drive, Azure Blob, S3, Box).
- Nome amigável OneDrive: «OneDrive (Pessoal e Empresas)» em `remote_setup.display_name_for_backend`.

### Como adicionar um ícone

1. Escolher a subpasta (`cloud`, `storage`, `protocol` ou `local`).
2. Criar `{stem}.svg` — o `stem` deve coincidir com o slug rclone ou com o valor em `_ICON_STEMS`.
3. Se o slug tiver alias (ex.: `googledrive` → `drive`), adicionar entrada em `_ICON_STEMS`; se o stem for igual ao slug normalizado, o índice descobre o ficheiro sozinho.
4. Reinstalar em editable (`pip install -e .`) ou rebuild para empacotar os novos SVGs (`pyproject.toml` → `package-data` com `**/*.svg`).

## New Drive (embedded page)

- Same content as former `NewDriveDialog`, embedded as `NewDrivePanel` on stack page 1.

## Settings

- Embedded as `SettingsPanel` on stack page 2 (sidebar + stack unchanged).
- Geral
- Segurança
- Privacidade
- Avançado
- Armazenamento local
- Por sua conta e risco
- Sobre

## Risk Tab

- Master experimental switch
- Union pool toggle
- Stripe toggle (`fill_by_quota`)
- Pre-allocation toggle
- Auto-resume toggle
- Retry config
- Risk acceptance checkbox

## Storage Cleanup Panel

- Analyze residuals
- Check-list candidates
- Confirm cleanup dialog
- Report freed space
