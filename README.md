# RDrive

RDrive is a desktop app inspired by RaiDrive, built on top of Rclone.
It mounts cloud storage as a local drive with a GUI-first workflow.

## Current status

This repository currently contains an implementation bootstrap:

- PyQt6 desktop app scaffold
- Main window with drive list placeholder
- Settings dialog with:
  - General (incl. quota reservation / pre-allocation)
  - Security
  - Logs
  - **Testes** (diagnostics: system checks, remote connection, speed test, mount status)
  - Privacy
  - Advanced
  - Local Storage
  - "Por sua conta e risco" (experimental stripe, union, watchdog dev)
- Core service skeletons for:
  - Rclone command execution
  - Quota monitoring
  - Reservation ledger
  - Residual cleanup analysis
  - Stripe planning/manifest/assembly verification modules

## App icon

The RDrive window and taskbar icon is the metallic 3D button with cyan cloud sync branding, packaged under `src/rdrive/assets/branding/`:

| File | Purpose |
|------|---------|
| `rdrive_icon_source.png` | Master crop (256×256, transparent background) |
| `rdrive_icon_{16,24,32,48,64,128,256}.png` | Multi-size PNGs for Qt |
| `rdrive.ico` | Windows multi-size icon (optional external use) |

Runtime code loads icons via `importlib.resources` (`rdrive.ui.app_icon`):

- `QApplication.setWindowIcon` in `app.py` (taskbar / Alt+Tab)
- `MainWindow` and all `InfiniteBorderDialog` windows (`setWindowIcon`)
- 16×16 pixmap on the custom title bar (`CustomTitleBar`)
- **System tray** (`QSystemTrayIcon` in `rdrive.ui.system_tray`, wired from `app.py` after `MainWindow.show()`):
  - Uses `tray_icon()` — on Windows prefers `rdrive.ico` or `rdrive_icon_16.png` / `rdrive_icon_32.png` (notification area sizes differ from the taskbar icon)
  - Tooltip with live status; context menu **Abrir**, **Montar todas**, **Desmontar todas**, submenu **Abrir unidade** (letras montadas), **Estado**, **Sair**; left/double-click opens the window
  - Created when the app event loop is running (including `pythonw` / `Iniciar.bat` phantom launch)
  - If the OS has no tray (e.g. some Linux DEs without a status notifier), a warning is written to `human.log`

To regenerate assets from a new source image (requires **Pillow** in the venv, not a runtime dependency):

```bash
.venv\Scripts\python.exe scripts\build_app_icons.py [caminho\para\imagem.png]
```

Default source: `%USERPROFILE%\Downloads\Gemini_Generated_Image_6knqxo6knqxo6knq.png`. Optional `rembg` improves background removal; otherwise the script keys out the flat grey backdrop.

## Project docs

- Architecture: `ARCHITECTURE.md`
- UI reference: `docs/ui-reference.md`

## Requirements

- Python 3.11+
- Rclone installed and available in PATH
- **WinFsp** (Windows) — required for `rclone mount`; auto-detected/installed by `Iniciar.bat` via `winget` when possible
- FUSE3 (Linux) for mounts

## Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m rdrive
```

### WebUI (`Static/`)

By default the app loads the HTML/CSS/JS interface from **`Static/`** at the project root (set automatically by `Iniciar.bat` via `RDRIVE_STATIC_DIR`).

| Variable | Default | Purpose |
|----------|---------|---------|
| `RDRIVE_WEBUI` | `1` | `0` / `false` forces the legacy native PyQt drive list |
| `RDRIVE_STATIC_DIR` | `<project>/Static` | Folder containing `index.html` |
| `RDRIVE_STATIC_LIVE` | off | `1` serves `Static/` in-place with auto-reload (~0.4s) |
| `RDRIVE_PROJECT_ROOT` | set by `Iniciar.bat` | Used to locate `Static/` when cwd differs |

**Develop UI:** `DevStatic-Live.bat` (PyQt + QWebChannel + live reload) or `DevStatic-Browser.bat` (browser-only preview on port 8765). Provider SVGs: `python scripts/sync_static_providers.py` → `Static/providers/`.

### Agente de configuração (WebUI)

Em **Adicionar unidade**, o cartão **Assistente automático** (ativo por defeito) executa o `CloudSetupAgent` (`src/rdrive/core/cloud_setup_agent.py`). A grelha de provedores carrega o modo e os campos via `listProviders` (`remote_setup.py`).

#### Matriz de modos

| Modo | Provedores (exemplos) | O que o utilizador faz |
|------|------------------------|-------------------------|
| **OAuth automático** | Google Drive, OneDrive, Dropbox, Box, pCloud, Mega | «Configuração automática» → login no browser → remote criado e unidade guardada |
| **Guiado (formulário)** | S3, WebDAV, SFTP, FTP, HTTP, SMB/CIFS, TeraBox (experimental) | Preenche credenciais no passo 1 → **Testar ligação** (opcional) → **Ligar e guardar** |
| **Manual (terminal)** | HDFS, Azure Blob, GCS, backends raros sem formulário | «Modo técnico» ou assistente rclone (`rclone config`) |

Comandos bridge: `startCloudSetupAgent`, `cancelCloudSetupAgent`, `getCloudSetupState`, `testGuidedConnection`, `openProviderDocs`. Eventos: `cloud_setup_progress`, `cloud_setup_finished`.

#### Backends com formulário guiado

| Backend | Campos principais | Notas |
|---------|-------------------|--------|
| `s3` | endpoint, access key, secret, região, bucket (teste) | `pass` no rclone; teste com `rclone lsd remote:` ou `remote:bucket` |
| `webdav` | URL, utilizador, senha | |
| `sftp` | host, porta (22), utilizador, senha **ou** ficheiro de chave **ou** PEM | Porta por defeito 22 |
| `ftp` | host, porta (21), utilizador, senha, FTPS explícito | Dicas PT em falhas: firewall, FTP passivo, TLS |
| `http` | URL | Montagem só leitura |
| `smb` | host, partilha, domínio (opcional), utilizador, senha | Partilha = nome SMB, sem `\\` |
| `terabox` | cookie `ndus` | Requer rclone não oficial; OAuth/TeraBox inalterado |

#### Secções README por protocolo

- <a id="agente-configuracao"></a> Esta secção (índice)
- <a id="agente-oauth"></a> OAuth (Drive, OneDrive, …)
- <a id="agente-s3"></a> S3
- <a id="agente-webdav"></a> WebDAV
- <a id="agente-sftp"></a> SFTP
- <a id="agente-ftp"></a> FTP / FTPS
- <a id="agente-http"></a> HTTP
- <a id="agente-smb"></a> SMB / CIFS
- <a id="agente-terabox"></a> TeraBox (experimental)
- <a id="agente-manual"></a> Terminal (`rclone config`) — HDFS e outros

Na WebUI, os botões **README** e **Documentação rclone** abrem a secção local ou a página oficial do backend.

#### Ideias futuras (backlog)

- Importar sessão FileZilla (XML) ou WinSCP
- Descoberta de partilhas SMB na LAN
- Colar URI (`ftp://user@host/path`) e preencher o formulário automaticamente

### TeraBox (experimental)

- O **rclone oficial** (ex. v1.74) **não inclui** o backend `terabox` (`rclone help backends` não lista terabox).
- Suporte em PR comunitário [rclone#8508](https://github.com/rclone/rclone/pull/8508) e forks (ex. [rclone-extra](https://github.com/iam-eo/rclone-extra-fork)) — autenticação por **cookie de sessão** (cabeçalho completo ou valor `ndus=…`), não OAuth.
- No RDrive: **Adicionar unidade → TeraBox (experimental)** → cole o cookie → **Ligar com credenciais**.
- **Testar ligação** (após configurar o remote `terabox_pessoal` ou o nome que escolheu):

```powershell
rclone lsd terabox_pessoal: --timeout 2m
```

- Se falhar com SSL/timeout: TeraBox é instável — aguarde e tente de novo; renove o cookie se a sessão expirou.
- Credenciais ficam no ficheiro de config do rclone (e unidades no cofre RDrive); passwords/cookies **não** são escritos em `logs/`.

Desative o assistente no passo 1 para o fluxo manual em 3 passos (inalterado). OneDrive empresarial: use o modo manual e escolha «Empresarial» no passo 3.

### Mapear só uma pasta partilhada (WebUI)

No assistente **Adicionar unidade → Detalhes**, ative **«Mapear apenas pasta/link partilhado»** e indique o link ou ID da pasta. O remote rclone continua a ser a conta OAuth completa; a montagem limita a raiz com flags/paths do rclone:

| Provedor | O que colar | Comportamento rclone |
|----------|-------------|----------------------|
| Google Drive | URL `…/folders/ID` ou só o ID | `--drive-root-folder-id` (+ `resource_key` se o URL tiver) |
| Dropbox | Nome da pasta em Partilhados ou link `dropbox.com/sh/…` | `--dropbox-shared-folders` + `remote:NomeDaPasta` |
| OneDrive | URL com `?id=…` ou ID da pasta | `--onedrive-root-folder-id` |
| Outros | Subcaminho no remote | `remote:Subpasta/…` (sem flag extra) |

Campo **Subpasta** (opcional): caminho relativo dentro da raiz já limitada (ex.: `Projetos/2024`). Unidades antigas sem estes campos continuam a montar a conta inteira.

### Pontos de montagem (Windows): A–Z e AA+

O Windows expõe apenas **26 letras de unidade** (`A:` … `Z:`) no Explorador. O rclone suporta dezenas de remotes, por isso o RDrive aloca pontos assim:

| Faixa | Onde monta | No Explorador |
|-------|------------|---------------|
| `A:` … `Z:` | Letra WinFsp/rclone (como hoje) | Unidade em «Este PC» |
| `AA`, `AB`, … | Pasta `%LOCALAPPDATA%/RDrive/mounts/AA/` | Abrir via RDrive (coluna **Ponto** ou bandeja) — não é letra de disco |

Quando todas as letras livres estão ocupadas (sistema ou RDrive), a sugestão automática passa a `AA`, depois `AB`, etc. (sequência estilo Excel). Pastas AA+ são montagens WinFsp válidas, mas **não** aparecem como `AA:` no Explorador — use o atalho do RDrive ou navegue até `RDrive/mounts/`.

## Windows quick start (`Iniciar.bat`)

For Windows, you can start everything with one click by running `Iniciar.bat` in the project root.

What it does automatically:

- Detects Python 3.
- If Python is missing, tries to install with `winget` (user scope, no admin prompt by script).
- Detects `rclone` in PATH.
- If `rclone` is missing, tries to install with `winget` (`Rclone.Rclone`, user scope).
- If needed, tries to add the detected `rclone.exe` folder to user PATH automatically (without admin).
- Detects **WinFsp** (registry, `winfsp-x64.dll`, `where winfsp-x64`, or `WinFsp.Launcher` service).
- If WinFsp is missing, tries `winget install --id WinFsp.WinFsp -e` (non-blocking — app starts and shows a dialog on mount if still missing).
- Creates `.venv` if needed.
- Upgrades `pip`.
- Installs `requirements.txt`.
- Starts the app with `.venv\Scripts\pythonw.exe -m rdrive` (no console window).
- Closes the launcher CMD when bootstrap finishes; errors are in `logs\launcher.log` (set `RDRIVE_LAUNCHER_DEBUG=1` to keep the window open on failure).

Notes:

- First run can take longer because it prepares the environment.
- The first remote is configured inside the app flow (`Adicionar` > **Conectar conta**), not in terminal bootstrap.
- If `winget` is not available, the script shows guided fallback instructions for manual install.
- The script updates PATH for the current session too, so it can continue immediately after detecting `rclone`.
- If no remote exists yet, the app opens normally and guides the configuration before connecting a drive.
- The script expects internet access for package installation.
- All launcher output (including errors) is appended to `logs\launcher.log` at the project root via `scripts\log_launcher.ps1`.

## Logs and troubleshooting

Application and launcher logs live in **`logs/`** at the repository root (Git-style). The path is resolved from `RDRIVE_PROJECT_ROOT`, or by walking up from the package / cwd until `pyproject.toml` or `Iniciar.bat` is found. If no project root is detected (e.g. a bare wheel install), logs fall back to `%LOCALAPPDATA%\RDrive\logs\`.

| File | Source |
|------|--------|
| `logs/rdrive.log` | Python app — exceptions, rclone subprocess, mount/connect, watchdog errors |
| `logs/rdrive.log.1` … `.3` | Rotated backups (5 MB each, 3 generations) |
| `logs/launcher.log` | `Iniciar.bat` bootstrap (Python/rclone/WinFsp install, pip, startup errors) |

**View logs in the app:** Definições → **Logs** → *Atualizar* (tail), *Abrir pasta de logs*, or *Abrir launcher.log*.

**Diagnostics:** Definições → **Testes** — quick system check (rclone, WinFsp, single instance, logs folder), test a remote (`lsd` + `about`), optional 1 MB upload/download speed test under `RDrive_speedtest/`, per-drive mount checks, and a read-only feature ON/OFF checklist from current settings. Results are also written to `rdrive.log` and `human.log`.

**View logs manually** (replace with your clone path):

```text
<project>\logs\rdrive.log
<project>\logs\launcher.log
```

Log files are gitignored (`logs/*.log`); the `logs/` folder is created on first write.

If the app fails before the GUI opens, check `launcher.log` first — it captures `.bat` and PowerShell bootstrap errors that never reach the Python logger.

## Mount: local disk vs network location (Windows)

RDrive uses **rclone mount** with **WinFsp**. On Windows, rclone can expose the drive in two ways:

| Mode | rclone flag | Explorer |
|------|-------------|----------|
| **Local disk** (default, RaiDrive-like) | *(no `--network-mode`)* + `--volname` | **Este PC → Discos locais** (e.g. `GDrive Pessoal (G:)`) |
| **Network location** (legacy) | `--network-mode` | **Locais de rede** (e.g. `gdrive_pessoal (\\server) (G:)`) |

- **Definições → Geral →** *Montar como disco local (Este PC), estilo RaiDrive pago* — setting `mount_as_local_drive` (default **on**).
- Turn it **off** only if you need the old WNet / “network drive” behaviour.
- **RaiDrive (paid)** uses a proprietary kernel driver; rclone cannot replicate that exactly. The closest match is **WinFsp fixed disk** (default): no `--network-mode`, friendly `--volname` from the drive label.
- After changing this setting, **disconnect and reconnect** the drive so a new `rclone mount` process starts with the right flags. Check `logs/rdrive.log` for `[MOUNT] command:`.

### Entrada fantasma em «Locais de rede» (PT)

Se após **Desligar** ainda vir algo como `gdrive_pessoal (\\server) (A:)` com X vermelho em **Este PC → Locais de rede**:

| Sintoma | Causa habitual |
|--------|----------------|
| Aparece em **Locais de rede**, não em Discos locais | A unidade foi montada com `--network-mode` (definição *Montar como disco local* desligada ou sessão antiga). |
| `net use A: /delete` diz que não encontra a ligação | O WinFsp já libertou a letra, mas o perfil WNet (`HKCU\Network\A`) ou o atalho UNC ficou órfão. |
| X vermelho no Explorador | Processo `rclone` terminou sem desmontar o FUSE / mapeamento persistente. |

**O que fazer (por ordem):**

1. **Definições → Geral** — active *Montar como disco local* e **Guarde** as definições (o RDrive passa a gravar esta opção).
2. **Desligue** a unidade no RDrive e **volte a ligar** — confirme em `logs/rdrive.log` que o comando **não** inclui `--network-mode`.
3. **Definições → Testes → Limpar mapeamento da letra** — escolha a letra (ex. `A:`) e execute a limpeza forçada (WNet, `net use`, registo, órfãos `rclone`).
4. **Manual (cmd como utilizador):**
   ```bat
   net use A: /delete /y
   ```
   Se ainda aparecer o UNC `\\server\share`:
   ```bat
   net use \\server\share /delete /y
   ```
5. **Script opcional** (PowerShell, na pasta do projeto):
   ```powershell
   .\scripts\cleanup_drive_letter.ps1 -Letter A
   ```
6. Reinicie o Explorador (`taskkill /f /im explorer.exe` e `start explorer`) ou reinicie o PC se o atalho persistir.

`rclone cmount` is an alias of `rclone mount` on Windows (same WinFsp backend). Extra WinFsp tuning is possible via `rclone mount --fuse-flag` / `--option` if you experiment outside the app.

## Troubleshooting: WinFsp on Windows

WinFsp is the user-mode file system layer that lets rclone expose cloud storage as a drive letter. Without it, connect/mount fails with a **WinFsp necessario** dialog.

- **Automatic:** run `Iniciar.bat` — it tries `winget install --id WinFsp.WinFsp -e` when WinFsp is not detected.
- **Manual:** https://winfsp.dev/rel/ or `winget install --id WinFsp.WinFsp -e`
- **Verify:** `where winfsp-x64` or check `C:\Program Files (x86)\WinFsp\bin\winfsp-x64.dll`
- WinFsp installs machine-wide (may prompt UAC). If winget fails, install manually and restart RDrive.

## Troubleshooting: rclone on Windows

- If `rclone` is not recognized, install it manually:
  - `winget install --id Rclone.Rclone -e --scope user`
  - Official downloads: https://rclone.org/downloads/
- After installation, close and reopen the terminal.
- Configure your first remote in the app (`Adicionar` > **Conectar conta**) or manually in terminal:
  - `rclone config`
- Validate remotes in terminal:
  - `rclone listremotes`

### Optional encrypted state (cofre local)

Por defeito o RDrive usa **cofre encriptado** (`drives.enc` / `settings.enc`) com senha mestra. Pode desactivar em **Definições → Segurança → Usar cofre (encriptação local)**:

| Modo | Comportamento |
|------|----------------|
| **Cofre ON** (predefinição) | Senha mestra no arranque; dados encriptados localmente; recuperação por email OTP |
| **Cofre OFF** | Sem senha mestra; `drives.json` e `settings.json` em texto legível no perfil local |

Instalações existentes mantêm o cofre activo (`profile_meta.json` → `vault_enabled: true`). Ao desactivar, os dados encriptados são exportados para JSON e os ficheiros `.enc` removidos — a acção exige confirmação na UI.

**Aviso (modo simples):** qualquer utilizador com acesso à pasta de perfil (`%LOCALAPPDATA%\RDrive\…`) pode ler unidades e definições. Use apenas em ambientes de confiança.

Para activar cofre via variável de ambiente (legado / scripts):

```bash
set RDRIVE_MASTER_PASSWORD=your-strong-password
python -m rdrive
```

Quando o cofre está activo, RDrive ignora a variável se `vault_enabled` estiver OFF em `profile_meta.json`.

### Manter sessão iniciada (este PC)

No ecrã **Desbloquear cofre**, pode marcar **Manter sessão iniciada** para guardar a senha mestra encriptada neste computador (Windows DPAPI, ligada ao utilizador Windows atual). No arranque seguinte o RDrive tenta restaurar a sessão sem pedir a senha.

- Os dados ficam em `%LOCALAPPDATA%\RDrive\session\<profile_id>\remembered_vault.blob` — nunca em texto simples.
- Cada conta (email / `profile_id`) tem a sua própria sessão memorizada.
- Em **Definições → Segurança**, use **Terminar sessão neste dispositivo** para apagar a sessão memorizada.
- **Segurança:** só protege contra leitura casual no disco; quem usar a sua sessão Windows neste PC pode desbloquear o cofre. Não use em PCs partilhados ou não confiáveis.

### Password recovery (email OTP)

At unlock time, use **Esqueci a senha** to verify your recovery email with a 6-digit code (10 minutes, max 3 attempts).

Configure in **Definições → Segurança**:

- **Email de recuperação** — required for reset; stored in `recovery_profile.json` (readable before unlock).
- **SMTP avançado** (optional) — send codes via `smtplib` SSL (port 465). If SMTP is not set, dev mode writes codes to `logs/password_reset_otp.log` and shows them in a dialog.

#### Gmail app password (example)

1. Enable 2-Step Verification on your Google account.
2. Open [Google App passwords](https://myaccount.google.com/apppasswords) and create one for “Mail”.
3. In RDrive → Definições → Segurança → SMTP avançado:
   - Host: `smtp.gmail.com`
   - Port: `465`
   - User: your Gmail address
   - Password: the 16-character app password (not your normal Gmail password)
   - From: same Gmail address

#### Cryptographic limitation (.enc)

If `drives.enc` / `settings.enc` already exist and you **forgot** the master password, the encrypted data **cannot** be decrypted without the old password. After email verification, RDrive can only:

- **Wipe the vault** and create a new empty encrypted store (all saved drives/settings in `.enc` are lost), or
- Change password normally in settings if you still know the current password.

Plain JSON state (no `.enc`) can be migrated to a new master password after OTP without data loss.

### Repor senha / cofre perdido

Se a senha mestra foi perdida (por exemplo após alterações manuais em `drives.enc`), os dados encriptados **não** podem ser lidos sem a senha antiga. Para voltar a usar o RDrive com cofre novo:

1. **Feche** o RDrive (bandeja e processo).
2. Na raiz do projeto, execute `scripts\reset_vault.bat` (ou `powershell -File scripts\reset_vault.ps1`), digite **`RESET`** quando pedido, e confirme. Isto remove `drives.enc`, `settings.enc` e `recovery_token.json`, mas **mantém** `drives.json` / `settings.json` legados se existirem. Detalhes em `logs\reset_vault.log`. Para apagar também JSON e perfis multi-utilizador: `reset_vault.ps1 -WipeAll`.
3. **Reinicie** com `Iniciar.bat`. No primeiro ecrã, defina o **email de recuperação** e a **nova senha mestra** (fluxo de criação do cofre). JSON legado é migrado automaticamente na abertura.

Alternativa na app (com cofre já desbloqueado): **Definições → Segurança → Repor cofre (perder dados encriptados)** — confirmação dupla com texto `RESET`, depois reinicie com `Iniciar.bat`.

## Ligar uma nuvem (com e sem configuração automática)

A WebUI em `Static/` guia a ligação em três passos (**Escolha o provedor** → **Detalhes** → **Ligação**). Use **`Iniciar.bat`** para o RDrive completo (PyQt + bridge + montagem real). Para desenvolver só a interface, **`DevStatic-Live.bat`** arranca o mesmo fluxo com recarregamento automático ao guardar ficheiros em `Static/`; **`DevStatic-Browser.bat`** abre um preview no browser (sem bridge — ligação/montagem não funcionam).

### Provedores: automático vs guiado vs terminal

Na grelha **Adicionar**, provedores com distintivo **Auto** usam OAuth no navegador. Os com **formulário guiado** (passo 1) configuram o rclone sem terminal. O restante usa `rclone config` no terminal.

| OAuth automático | Guiado (formulário WebUI) | Manual (terminal) |
|------------------|---------------------------|-------------------|
| Google Drive (`drive`) | Amazon S3 (`s3`) | HDFS (`hdfs`) |
| OneDrive (`onedrive`) | WebDAV (`webdav`) | Azure Blob, Google Cloud Storage, … |
| Dropbox (`dropbox`) | SFTP (`sftp`) | Backends listados pelo seu `rclone` sem formulário |
| Box (`box`) | FTP (`ftp`) | |
| pCloud (`pcloud`) | HTTP (`http`, só leitura) | |
| Mega (`mega`) | SMB / CIFS (`smb`) | |
| | TeraBox (`terabox`, experimental) | |

Nos provedores **Auto**, **Alternativa: configurar no terminal** continua disponível. Nos **guiados**, use **Modo técnico** se preferir o assistente rclone interactivo.

### Fluxo com configuração automática

1. **Adicionar** (barra ou lista vazia).
2. **Passo 1 — Escolha o provedor:** selecione um serviço com distintivo **Auto** (ex.: Google Drive, OneDrive).
3. **Passo 2 — Detalhes:** defina um **nome da unidade** único, o **Remote (rclone)** sugerido (ex.: `gdrive_pessoal`) e a **letra de montagem** (ex.: `G:`). Opcional: montar ao abrir o RDrive / desmontar ao fechar.
4. **Passo 3 — Ligação:** clique **Configuração automática — conectar conta**. O browser abre para login OAuth; o RDrive cria o remote no rclone e valida o acesso.
5. **Guardar unidade.** Se **Conectar a unidade após guardar** estiver marcado, a montagem começa de seguida.
6. Na lista de unidades, use o interruptor **Montar unidade** (ou aguarde o arranque automático se configurou montagem ao abrir).

Validação opcional no terminal: `rclone about gdrive_pessoal:` ou `rclone lsd gdrive_pessoal:`.

### Fluxo sem configuração automática (guiado ou terminal)

Use este fluxo para S3, WebDAV, SFTP, FTP, HTTP, SMB e quando o OAuth automático não estiver disponível ou falhar.

**Pré-requisitos**

- **`rclone` no PATH** — confirmar com `rclone version` (o `Iniciar.bat` tenta instalar via `winget` se faltar).
- **Cofre desbloqueado** — o RDrive precisa de sessão ativa para guardar unidades e montar.

**Passos (formulário guiado)**

1. **Adicionar** → escolha o provedor (ex.: SFTP, FTP, SMB).
2. **Passo 1:** preencha host/URL/credenciais → **Testar ligação** (cria remote temporário e executa `rclone lsd`).
3. **Ligar e guardar** — cria o remote definitivo, valida e grava a unidade (com assistente automático activo, também sugere nome e letra).
4. Na lista, ligue **Montar unidade**.

**Passos (só terminal)**

1. **Adicionar** → provedor sem formulário (ex.: HDFS) ou **Modo técnico** num provedor guiado.
2. **Configurar manualmente (terminal)** — `rclone config` com documentação do backend no browser.
3. Confirme com `rclone listremotes` e `rclone lsd nome_remote:`.
4. Volte ao passo **Detalhes**, preencha **Remote (rclone)** e **Guardar unidade**.

### OneDrive empresarial

- **Configuração automática:** o fluxo OAuth cobre contas **pessoais** e muitos cenários **empresariais** (Microsoft 365). Se o rclone pedir tipo de drive durante a criação automática, o default interno é OneDrive pessoal (`onedrive`).
- **Manual recomendado** para **SharePoint**, bibliotecas específicas ou quando precisa escolher explicitamente **OneDrive personal** vs **OneDrive for Business** no assistente `rclone config` (pergunta `drive_type` / `type`).
- Remote de exemplo: `onedrive_trabalho` — depois copie esse nome para o campo **Remote (rclone)** no passo Detalhes.

### Problemas comuns

| Problema | O que fazer |
|----------|-------------|
| Montagem falha com **WinFsp necessário** | Instale WinFsp (`Iniciar.bat` tenta via `winget`, ou secção [Troubleshooting: WinFsp](#troubleshooting-winfsp-on-windows) abaixo). |
| **Este nome já está em uso** | Escolha outro **nome da unidade** — nomes são únicos no cofre. |
| **A letra X: já está em uso** | Outra unidade RDrive, `net use` ou processo `rclone` ocupa a letra; escolha outra ou use Definições → **Testes** → *Limpar mapeamento da letra*. |
| OAuth / remote inválido | Consulte `logs/rdrive.log` (comandos rclone, erros de mount). Definições → **Logs** → *Atualizar* ou **Testes** para diagnóstico rápido. |
| Assistente terminal não abre | Só funciona com o RDrive em execução via `Iniciar.bat` / `DevStatic-Live.bat` (não no preview `DevStatic-Browser.bat`). |

Matriz técnica de backends e limitações: `ARCHITECTURE.md` §10.

## Roadmap (paridade RaiDrive — não implementado)

Funcionalidades identificadas na comparação com o RaiDrive, planeadas para iterações futuras (não incluídas nesta sessão):

- **Assistente SharePoint completo** — wizard WebUI para bibliotecas/document libraries com escolha de site e drive ID.
- **Bloqueio de ficheiros (file lock)** — exclusão cooperativa durante edição em unidades montadas.
- **Encriptação de cache VFS** — cache local encriptado por unidade ou global.
- **Seletor de árvore de pastas** — picker visual de subpastas remotas ao criar/editar unidade (em vez de texto livre em `root_path`).

## Notes

- The app is designed for Windows and Linux.
- **Quota reservation** (`enable_preallocation`, default on): Definições → Geral → *Reservar espaço antes de gravar ficheiros grandes*. Uses `ReservationLedger` + `QuotaMonitor` when planning stripe splits; events appear in the human log feed.
- Experimental features (stripe split, union pool, dev watchdog) stay under **Por sua conta e risco** and may require risk acceptance.
- The first implementation focuses on architecture and safe operational flows.
