# RDrive


> [!WARNING]
> **Versão instável (em desenvolvimento)**  interface CustomTkinter experimental, combinar nuvens, otimizações de desempenho e TeraBox via Chrome dedicado; funcionalidades podem quebrar. **Não usar em produção.**

> [!IMPORTANT]
> **O RDrive monta o TeraBox como unidade de disco local no Windows** â letra em Â«Este PCÂ» via `rclone mount` + **WinFsp**, com build **nÃ£o oficial** do rclone (backend `terabox`, PR [rclone#8508](https://github.com/rclone/rclone/pull/8508)) e autenticaÃ§Ã£o por **cookie de sessÃ£o** (`ndus`), importado do **Chrome dedicado** via extensÃ£o `cookies.txt`.
>
> Existem PRs, forks e outros wrappers que tambÃ©m ligam o TeraBox ao rclone, mas **nenhum oferece o mesmo conjunto**: WebUI em `Static/` com assistente guiado, fluxo Chrome + cookies.txt para TeraBox, montagem WinFsp integrada, bandeja do sistema, bootstrap `Iniciar.bat` (rclone/WinFsp) e diagnÃ³stico em ConfiguraÃ§Ãµes â **Testes**.
>
> **Experimental e nÃ£o oficial:** depende de backend comunitÃ¡rio do rclone e de sessÃ£o web do TeraBox; nÃ£o Ã© produto homologado pelo provedor. Detalhes na seÃ§Ã£o [TeraBox (experimental)](#terabox-experimental).

RepositÃ³rio pÃºblico: [github.com/MiguelSilvaPorto/RDrive](https://github.com/MiguelSilvaPorto/RDrive)

O RDrive Ã© um aplicativo desktop inspirado no RaiDrive, construÃ­do sobre o [rclone](https://rclone.org/).
Ele monta armazenamento em nuvem como unidade local, com fluxo de trabalho orientado Ã  interface grÃ¡fica.

## Status atual

Este repositÃ³rio contÃ©m atualmente um bootstrap de implementaÃ§Ã£o:

- Scaffold do aplicativo desktop em PyQt6
- Janela principal com placeholder da lista de unidades
- DiÃ¡logo de configuraÃ§Ãµes com:
  - Geral (incl. reserva de cota / prÃ©-alocaÃ§Ã£o)
  - SeguranÃ§a
  - Logs
  - **Testes** (diagnÃ³stico: verificaÃ§Ãµes do sistema, conexÃ£o remota, teste de velocidade, status de montagem)
  - Privacidade
  - AvanÃ§ado
  - Armazenamento local
  - Â«Por sua conta e riscoÂ» (faixa experimental, union, watchdog de desenvolvimento)
- Esqueletos de serviÃ§os principais para:
  - ExecuÃ§Ã£o de comandos rclone
  - Monitoramento de cota
  - Ledger de reservas
  - AnÃ¡lise de limpeza residual
  - MÃ³dulos de planejamento/manifesto/verificaÃ§Ã£o de montagem em faixas (stripe)

## Ãcone do aplicativo

O Ã­cone da janela e da barra de tarefas do RDrive Ã© o botÃ£o metÃ¡lico 3D com marca de sincronizaÃ§Ã£o em nuvem ciano, empacotado em `src/rdrive/assets/branding/`:

| Arquivo | Finalidade |
|---------|------------|
| `rdrive_icon_source.png` | Recorte mestre (256Ã256, fundo transparente) |
| `rdrive_icon_{16,24,32,48,64,128,256}.png` | PNGs em vÃ¡rios tamanhos para Qt |
| `rdrive.ico` | Ãcone Windows multi-tamanho (uso externo opcional) |

O cÃ³digo em tempo de execuÃ§Ã£o carrega Ã­cones via `importlib.resources` (`rdrive.ui.foundation.app_icon`):

- `QApplication.setWindowIcon` em `app.py` (barra de tarefas / Alt+Tab)
- `MainWindow` e todas as janelas `InfiniteBorderDialog` (`setWindowIcon`)
- Pixmap 16Ã16 na barra de tÃ­tulo personalizada (`CustomTitleBar`)
- **Bandeja do sistema** (`QSystemTrayIcon` em `rdrive.ui.system_tray`, conectado em `app.py` apÃ³s `MainWindow.show()`):
  - Usa `tray_icon()` â no Windows prefere `rdrive.ico` ou `rdrive_icon_16.png` / `rdrive_icon_32.png` (a Ã¡rea de notificaÃ§Ã£o usa tamanhos diferentes do Ã­cone da barra de tarefas)
  - Tooltip com status ao vivo; menu de contexto **Abrir**, **Montar todas**, **Desmontar todas**, submenu **Abrir unidade** (letras montadas), **Estado**, **Sair**; clique esquerdo/duplo abre a janela
  - Criado quando o loop de eventos do app estÃ¡ em execuÃ§Ã£o (incluindo lanÃ§amento fantasma `pythonw` / `Iniciar.bat`)
  - Se o SO nÃ£o tiver bandeja (ex.: alguns ambientes Linux sem status notifier), um aviso Ã© gravado em `human.log`

Para regenerar os assets a partir de uma nova imagem fonte (requer **Pillow** no venv, nÃ£o Ã© dependÃªncia de runtime):

```bash
.venv\Scripts\python.exe scripts\build_app_icons.py [caminho\para\imagem.png]
```

Fonte padrÃ£o: `%USERPROFILE%\Downloads\Gemini_Generated_Image_6knqxo6knqxo6knq.png`. O `rembg` opcional melhora a remoÃ§Ã£o de fundo; caso contrÃ¡rio, o script remove o fundo cinza plano.

## DocumentaÃ§Ã£o do projeto

- Arquitetura: `ARCHITECTURE.md`
- Estrutura de pastas (mapa canÃ´nico): `docs/ESTRUTURA.md`
- ReferÃªncia de UI: `docs/ui-reference.md`
- Fluxo Git: `docs/GIT-CURSOR.md`

## Interface â CustomTkinter (padrÃ£o) vs. WebUI (legado)

A partir desta release o RDrive passa a usar **CustomTkinter** como interface nativa por defeito â mais leve, sem motor Chromium, com paleta dark blue alinhada aos tokens da antiga `Static/`. A UI antiga (HTML/CSS/JS em `Static/`) **continua disponÃ­vel** como modo de fallback.

| VariÃ¡vel `RDRIVE_UI` | Resultado |
|----------------------|-----------|
| _nÃ£o definido_       | CTk se `customtkinter` instalado; senÃ£o WebUI |
| `ctk`                | ForÃ§a a UI CustomTkinter (`src/rdrive/ui/ctk/`) |
| `web`                | ForÃ§a a WebUI/`Static/` (PyQt6-WebEngine) |
| `native`             | ForÃ§a a UI nativa antiga PyQt (`RDRIVE_WEBUI=0`) |

Para abrir a UI CTk via launcher: `set RDRIVE_UI=ctk && Iniciar.bat` (Windows) ou `RDRIVE_UI=ctk python -m rdrive` (qualquer SO).

> [!NOTE]
> **`Static/` estÃ¡ marcado como deprecado.** Permanece no repositÃ³rio como fallback atÃ© a paridade total ser atingida na CTk; novas features sÃ£o adicionadas primeiro em `src/rdrive/ui/ctk/`.

## Requisitos

- Python 3.11+
- **customtkinter â¥ 5.2** (incluÃ­do em `requirements.txt`) â UI nativa padrÃ£o
- **PyQt6-WebEngine** (incluÃ­do em `requirements.txt`) â motor Chromium embebido para a WebUI legado em `Static/`
- Rclone instalado e disponÃ­vel no PATH
- **WinFsp** (Windows) â necessÃ¡rio para `rclone mount`; detectado/instalado automaticamente pelo `Iniciar.bat` via `winget` quando possÃ­vel
- FUSE3 (Linux) para montagens

### PyQt6-WebEngine (Windows)

A interface web depende de `PyQt6-WebEngine`. O `Iniciar.bat` instala via `pip install -r requirements.txt` e executa uma verificaÃ§Ã£o rÃ¡pida.

**InstalaÃ§Ã£o manual / reparo:**

```powershell
.venv\Scripts\python.exe -m pip install --upgrade "PyQt6-WebEngine>=6.6.0"
.\scripts\verify_webengine.ps1
```

**Se o venv estiver corrompido**, recrie-o (feche o RDrive antes):

```powershell
Remove-Item -Recurse -Force .venv
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\verify_webengine.ps1
```

**DiagnÃ³stico:** import OK mas pÃ¡gina em branco â execute `verify_webengine.ps1`. Se a WebUI principal (`Static/`) nÃ£o carregar, reinstale PyQt6-WebEngine.

## Executar

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m rdrive
```

### WebUI (`Static/`)

Por padrÃ£o, o aplicativo carrega a interface HTML/CSS/JS de **`Static/`** na raiz do projeto (definido automaticamente pelo `Iniciar.bat` via `RDRIVE_STATIC_DIR`).

| VariÃ¡vel | PadrÃ£o | Finalidade |
|----------|--------|------------|
| `RDRIVE_WEBUI` | `1` | `0` / `false` forÃ§a a lista nativa legada em PyQt |
| `RDRIVE_STATIC_DIR` | `<projeto>/Static` | Pasta que contÃ©m `index.html` |
| `RDRIVE_STATIC_LIVE` | desligado | `1` serve `Static/` no lugar com recarga automÃ¡tica (~0,4 s) |
| `RDRIVE_PROJECT_ROOT` | definido pelo `Iniciar.bat` | Usado para localizar `Static/` quando o cwd difere |

**Desenvolver a UI:** `scripts\launchers\DevStatic-Live.bat` (PyQt + QWebChannel + live reload) ou `scripts\launchers\DevStatic-Browser.bat` (preview sÃ³ no navegador na porta 8765). SVGs de provedores: `python scripts/sync_static_providers.py` â `Static/providers/`.

### Agente de configuraÃ§Ã£o (WebUI)

Em **Adicionar unidade**, o cartÃ£o **Assistente automÃ¡tico** (ativo por padrÃ£o) executa o `CloudSetupAgent` (`src/rdrive/core/cloud_setup_agent.py`). A grade de provedores carrega o modo e os campos via `listProviders` (`remote_setup.py`).

#### Matriz de modos

| Modo | Provedores (exemplos) | O que vocÃª faz |
|------|------------------------|----------------|
| **OAuth automÃ¡tico** | Google Drive, OneDrive, Dropbox, Box, pCloud, Mega | Â«ConfiguraÃ§Ã£o automÃ¡ticaÂ» â login no navegador â remote criado e unidade salva |
| **Guiado (formulÃ¡rio)** | S3, WebDAV, SFTP, FTP, HTTP, SMB/CIFS, TeraBox (experimental) | Preenche credenciais no passo 1 â **Testar conexÃ£o** (opcional) â **Conectar e salvar** |
| **Manual (terminal)** | HDFS, Azure Blob, GCS, backends raros sem formulÃ¡rio | Â«Modo tÃ©cnicoÂ» ou assistente rclone (`rclone config`) |

Comandos bridge: `startCloudSetupAgent`, `cancelCloudSetupAgent`, `getCloudSetupState`, `testGuidedConnection`, `openProviderDocs`. Eventos: `cloud_setup_progress`, `cloud_setup_finished`.

#### Backends com formulÃ¡rio guiado

| Backend | Campos principais | Notas |
|---------|-------------------|--------|
| `s3` | endpoint, access key, secret, regiÃ£o, bucket (teste) | `pass` no rclone; teste com `rclone lsd remote:` ou `remote:bucket` |
| `webdav` | URL, usuÃ¡rio, senha | |
| `sftp` | host, porta (22), usuÃ¡rio, senha **ou** arquivo de chave **ou** PEM | Porta padrÃ£o 22 |
| `ftp` | host, porta (21), usuÃ¡rio, senha, FTPS explÃ­cito | Dicas em PT em falhas: firewall, FTP passivo, TLS |
| `http` | URL | Montagem somente leitura |
| `smb` | host, compartilhamento, domÃ­nio (opcional), usuÃ¡rio, senha | Compartilhamento = nome SMB, sem `\\` |
| `terabox` | cookie `ndus` | Requer rclone nÃ£o oficial; OAuth/TeraBox inalterado |

#### SeÃ§Ãµes README por protocolo

- <a id="agente-configuracao"></a> Esta seÃ§Ã£o (Ã­ndice)
- <a id="agente-oauth"></a> OAuth (Drive, OneDrive, â¦)
- <a id="agente-s3"></a> S3
- <a id="agente-webdav"></a> WebDAV
- <a id="agente-sftp"></a> SFTP
- <a id="agente-ftp"></a> FTP / FTPS
- <a id="agente-http"></a> HTTP
- <a id="agente-smb"></a> SMB / CIFS
- <a id="agente-terabox"></a> TeraBox (experimental)
- <a id="agente-manual"></a> Terminal (`rclone config`) â HDFS e outros

Na WebUI, os botÃµes **README** e **DocumentaÃ§Ã£o rclone** abrem a seÃ§Ã£o local ou a pÃ¡gina oficial do backend.

#### Ideias futuras (backlog)

- Importar sessÃ£o FileZilla (XML) ou WinSCP
- Descoberta de compartilhamentos SMB na LAN
- Colar URI (`ftp://user@host/path`) e preencher o formulÃ¡rio automaticamente

### TeraBox (experimental)

- O **rclone oficial** (ex.: v1.74) **nÃ£o inclui** o backend `terabox` (`rclone help backends` nÃ£o lista terabox).
- Suporte em PR comunitÃ¡rio [rclone#8508](https://github.com/rclone/rclone/pull/8508) e forks (ex.: [rclone-extra](https://github.com/iam-eo/rclone-extra-fork)) â autenticaÃ§Ã£o por **cookie de sessÃ£o** (cabeÃ§alho completo ou valor `ndus=â¦`), **nÃ£o Ã© OAuth**.
- No RDrive: **Adicionar unidade â TeraBox (experimental)** â autenticaÃ§Ã£o via **Chrome dedicado + cookies.txt**:
  1. Clique **Abrir Chrome do RDrive** (ou `scripts\launchers\Abrir-Chrome-TeraBox.bat`) â perfil isolado em `%LOCALAPPDATA%\RDrive\chrome-terabox-profile`. O RDrive **carrega automaticamente** a extensÃ£o descompactada [Get cookies.txt LOCALLY](https://github.com/kairi003/Get-cookies.txt-LOCALLY) (release v0.7.2 em `tools/get-cookies-txt-locally/` via `--load-extension`; bootstrap em `Iniciar.bat`).
  2. FaÃ§a login em terabox.com e exporte `cookies.txt` com o Ã­cone da extensÃ£o.
  3. No RDrive: **Importar cookie (Chrome)** ou **Abrir pasta Downloads** â ficheiros com cookies de vÃ¡rios sites sÃ£o filtrados automaticamente (`ndus=`).
  4. Alternativa: **Login no navegador integrado** (PyQt WebEngine dentro do RDrive; opcional â em alguns PCs a pÃ¡gina pode ficar em branco).
  5. **Testar ligaÃ§Ã£o** (opcional) â **Ligar e guardar**
- **Importante:** o site TeraBox **bloqueia ferramentas de desenvolvedor (F12)** â nÃ£o tente copiar cookies manualmente no terabox.com.
- AtualizaÃ§Ã£o opcional da extensÃ£o na [Chrome Web Store](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) (nÃ£o Ã© necessÃ¡ria para o fluxo RDrive).
- O navegador **integrado PyQt WebEngine** permanece disponÃ­vel como alternativa ao Chrome; nÃ£o suporta extensÃµes â prefira Chrome + cookies.txt quando possÃ­vel.
- **Testar conexÃ£o** (apÃ³s configurar o remote `terabox_pessoal` ou o nome que vocÃª escolheu):

```powershell
rclone lsd terabox_pessoal: --timeout 2m
```

- Se falhar com SSL/timeout: o TeraBox Ã© instÃ¡vel â aguarde e tente de novo; renove o cookie se a sessÃ£o expirou.
- Credenciais ficam no arquivo de config do rclone (e unidades no cofre RDrive); senhas/cookies **nÃ£o** sÃ£o gravados em `logs/`.

#### Instalar rclone com TeraBox (Windows)

O **rclone oficial** (winget, chocolatey, site rclone.org) **nÃ£o** inclui o backend `terabox`. NÃ£o hÃ¡ pacote winget/chocolatey fiÃ¡vel com TeraBox â instalaÃ§Ã£o **manual** de um build comunitÃ¡rio.

1. **Verificar o rclone atual** (PowerShell):

```powershell
rclone version
rclone help backends | findstr /i terabox
```

Se `findstr` nÃ£o imprimir nada, o backend TeraBox **nÃ£o** estÃ¡ disponÃ­vel.

2. **Obter um build nÃ£o oficial** com backend `terabox`:
   - PR comunitÃ¡rio: [rclone#8508](https://github.com/rclone/rclone/pull/8508)
   - Forks com builds (exemplos): [iam-eo/rclone-extra-fork](https://github.com/iam-eo/rclone-extra-fork/releases), branch `terabox` em forks do PR
   - Baixe o ZIP **Windows amd64** do release ou artefato CI do fork escolhido

3. **Substituir o executÃ¡vel no PATH** (feche o RDrive antes):

```powershell
# Exemplo: rclone oficial em C:\Program Files\rclone\
where.exe rclone
# Copie o rclone.exe do ZIP para a mesma pasta (backup do original):
Copy-Item "C:\Program Files\rclone\rclone.exe" "C:\Program Files\rclone\rclone.exe.bak"
Copy-Item "$env:USERPROFILE\Downloads\rclone\rclone.exe" "C:\Program Files\rclone\rclone.exe" -Force
```

4. **Confirmar** que o backend existe:

```powershell
rclone help backends | findstr /i terabox
# Deve listar: terabox    TeraBox
```

5. **Reinicie o RDrive** e volte a **Adicionar unidade â TeraBox (experimental)**.

Script auxiliar (sÃ³ diagnÃ³stico e instruÃ§Ãµes â **nÃ£o** baixa binÃ¡rios):

```powershell
.\scripts\install_rclone_terabox.ps1
```

Desative o assistente no passo 1 para o fluxo manual em 3 passos (inalterado). OneDrive empresarial: use o modo manual e escolha Â«EmpresarialÂ» no passo 3.

### Mapear sÃ³ uma pasta compartilhada (WebUI)

No assistente **Adicionar unidade â Detalhes**, ative **Â«Mapear apenas pasta/link compartilhadoÂ»** e informe o link ou ID da pasta. O remote rclone continua sendo a conta OAuth completa; a montagem limita a raiz com flags/paths do rclone:

| Provedor | O que colar | Comportamento rclone |
|----------|-------------|----------------------|
| Google Drive | URL `â¦/folders/ID` ou sÃ³ o ID | `--drive-root-folder-id` (+ `resource_key` se a URL tiver) |
| Dropbox | Nome da pasta em Compartilhados ou link `dropbox.com/sh/â¦` | `--dropbox-shared-folders` + `remote:NomeDaPasta` |
| OneDrive | URL com `?id=â¦` ou ID da pasta | `--onedrive-root-folder-id` |
| Outros | Subcaminho no remote | `remote:Subpasta/â¦` (sem flag extra) |

Campo **Subpasta** (opcional): caminho relativo dentro da raiz jÃ¡ limitada (ex.: `Projetos/2024`). Unidades antigas sem esses campos continuam montando a conta inteira.

### Combinar nuvens do mesmo provedor (rclone `union`)

Ligue duas ou mais contas do **mesmo provedor** (Google + Google, OneDrive + OneDrive, â¦) numa Ãºnica unidade no Explorador, somando o espaÃ§o Ãºtil.

1. Clique em **Combinar** na barra superior.
2. **Passo 1 â Nuvem principal:** escolha a primeira nuvem na lista (jÃ¡ aparecem sÃ³ as elegÃ­veis: remotes simples, sem wrappers).
3. **Passo 2 â Nuvens compatÃ­veis:** o RDrive lista apenas drives do **mesmo provedor canÃ³nico**. Selecione as outras contas que entram na uniÃ£o.
4. **Passo 3 â Nome e ponto de montagem:** dÃª um nome (ex.: *Google Drive Combinado*) e escolha uma letra livre (`A:`â`Z:` ou pasta `AA+`).
5. Clique em **Combinar nuvens**.

O backend cria uma entrada `[union_<nome>]` no `rclone.conf` (sanitizada) com defaults seguros â `create_policy=epmfs` (escreve no upstream existente com mais espaÃ§o livre) e `search_policy=ff` (primeiro encontrado, evita ambiguidade). Exemplo de config gerada (sanitizada):

```ini
[union_google_drive_combinado]
type = union
upstreams = gdrive_pessoal: gdrive_trabalho:
create_policy = epmfs
search_policy = ff
```

**Regras de seguranÃ§a aplicadas:**

- Cross-provider Ã© bloqueado (Google + OneDrive **nÃ£o** Ã© permitido â UX e validaÃ§Ã£o no backend recusam o pedido).
- Drives que **jÃ¡ sÃ£o uniÃµes** (`drive_type = union_pool`) ou backends wrapper (`crypt`, `alias`, `cache`, `combine`, â¦) nÃ£o entram na combinaÃ§Ã£o â impede recursÃ£o.
- Um remote **nÃ£o pode ser upstream de duas uniÃµes** ao mesmo tempo (contagem dupla de espaÃ§o).
- MÃ­nimo de **dois** remotes distintos por uniÃ£o; nomes e letras devem ser Ãºnicos.

**LimitaÃ§Ãµes conhecidas:**

- TeraBox: a uniÃ£o entre contas TeraBox Ã© experimental e segue as limitaÃ§Ãµes do backend `terabox` (ver secÃ§Ã£o [TeraBox](#terabox-experimental)).
- Backends OAuth diferentes do mesmo provedor (ex.: dois OneDrive â pessoal + empresarial) podem combinar tecnicamente, mas o rclone usa o **mesmo cliente OAuth** para cada upstream â confirme se ambos tÃªm token activo.
- EncriptaÃ§Ã£o (`crypt`), cache, alias e outras combinaÃ§Ãµes sÃ£o **wrappers**: para usÃ¡-las dentro de uma uniÃ£o, configure o wrapper directamente no `rclone.conf` (este fluxo cobre sÃ³ o caso simples).

### Pontos de montagem (Windows): AâZ e AA+

O Windows expÃµe apenas **26 letras de unidade** (`A:` â¦ `Z:`) no Explorador. O rclone suporta dezenas de remotes; o RDrive aloca pontos assim:

| Faixa | Onde monta | No Explorador |
|-------|------------|---------------|
| `A:` â¦ `Z:` | Letra WinFsp/rclone (como hoje) | Unidade em Â«Este PCÂ» |
| `AA`, `AB`, â¦ | Pasta `%LOCALAPPDATA%/RDrive/mounts/AA/` | Abrir via RDrive (coluna **Ponto** ou bandeja) â nÃ£o Ã© letra de disco |

Quando todas as letras livres estÃ£o ocupadas (sistema ou RDrive), a sugestÃ£o automÃ¡tica passa a `AA`, depois `AB`, etc. (sequÃªncia estilo Excel). Pastas AA+ sÃ£o montagens WinFsp vÃ¡lidas, mas **nÃ£o** aparecem como `AA:` no Explorador â use o atalho do RDrive ou navegue atÃ© `RDrive/mounts/`.

## Scripts e atalhos

Na raiz do repositÃ³rio fica apenas **`Iniciar.bat`** (launcher principal com UAC/bootstrap). Os demais comandos Windows estÃ£o em **`scripts\launchers\`** (duplo clique ou atalho do Explorador apontando para o `.bat` desejado).

| Comando | O que faz |
|---------|-----------|
| `Iniciar.bat` | Bootstrap (Python, venv, pip, rclone, WinFsp) e arranque do app (`pythonw -m rdrive`) |
| `scripts\launchers\DevStatic-Live.bat` | Mesmo fluxo que `Iniciar.bat` com `RDRIVE_STATIC_LIVE=1` (recarga da WebUI ao guardar `Static/`) |
| `scripts\launchers\DevStatic-Browser.bat` | Preview HTTP da pasta `Static/` na porta 8765 (sem PyQt nem bridge) |
| `scripts\launchers\Abrir-Chrome-TeraBox.bat` | Chrome dedicado TeraBox (perfil isolado + extensÃ£o cookies) |
| `scripts\launchers\Capturar-Cookie-TeraBox.bat` | GUI para importar `cookies.txt` para o rclone TeraBox |
| `scripts\launchers\Configurar-TeraBox.bat` | Assistente terminal: colar cookie e criar remote |
| `scripts\launchers\Montar-TeraBox.bat` | Montagem manual TeraBox via `mount_terabox.ps1` |
| `scripts\reset_vault.bat` | Repor cofre criptografado (confirmaÃ§Ã£o `RESET`) |

LÃ³gica pesada: orquestradores `.ps1` em `scripts\` (ex.: `log_launcher.ps1`, `launch_terabox_chrome.ps1`, `mount_terabox.ps1`).

## InÃ­cio rÃ¡pido no Windows (`Iniciar.bat`)

No Windows, vocÃª pode iniciar tudo com um clique executando `Iniciar.bat` na raiz do projeto.

O que ele faz automaticamente:

- Detecta Python 3.
- Se o Python estiver ausente, tenta instalar com `winget` (escopo de usuÃ¡rio, sem prompt de admin pelo script).
- Detecta `rclone` no PATH.
- Se o `rclone` estiver ausente, tenta instalar com `winget` (`Rclone.Rclone`, escopo de usuÃ¡rio).
- Se necessÃ¡rio, tenta adicionar a pasta detectada do `rclone.exe` ao PATH do usuÃ¡rio automaticamente (sem admin).
- Detecta **WinFsp** (registro, `winfsp-x64.dll`, `where winfsp-x64` ou serviÃ§o `WinFsp.Launcher`).
- Se o WinFsp estiver ausente, tenta `winget install --id WinFsp.WinFsp -e` (nÃ£o bloqueante â o app inicia e mostra um diÃ¡logo na montagem se ainda faltar).
- Cria `.venv` se necessÃ¡rio.
- Atualiza o `pip`.
- Instala `requirements.txt`.
- Inicia o app com `.venv\Scripts\pythonw.exe -m rdrive` (sem janela de console).
- Fecha o CMD do launcher quando o bootstrap termina; erros ficam em `logs\launcher.log` (defina `RDRIVE_LAUNCHER_DEBUG=1` para manter a janela aberta em caso de falha).

ObservaÃ§Ãµes:

- A primeira execuÃ§Ã£o pode demorar mais porque prepara o ambiente.
- O primeiro remote Ã© configurado no fluxo do aplicativo (`Adicionar` > **Conectar conta**), nÃ£o no bootstrap do terminal.
- Se o `winget` nÃ£o estiver disponÃ­vel, o script mostra instruÃ§Ãµes guiadas para instalaÃ§Ã£o manual.
- O script atualiza o PATH da sessÃ£o atual tambÃ©m, para continuar imediatamente apÃ³s detectar o `rclone`.
- Se ainda nÃ£o existir remote, o app abre normalmente e guia a configuraÃ§Ã£o antes de conectar uma unidade.
- O script espera acesso Ã  internet para instalaÃ§Ã£o de pacotes.
- Toda a saÃ­da do launcher (incluindo erros) Ã© acrescentada a `logs\launcher.log` na raiz do projeto via `scripts\log_launcher.ps1`.

## Logs e soluÃ§Ã£o de problemas

Os logs do aplicativo e do launcher ficam em **`logs/`** na raiz do repositÃ³rio (estilo Git). O caminho Ã© resolvido a partir de `RDRIVE_PROJECT_ROOT`, ou subindo a partir do pacote / cwd atÃ© encontrar `pyproject.toml` ou `Iniciar.bat`. Se nenhuma raiz de projeto for detectada (ex.: wheel isolado), os logs caem em `%LOCALAPPDATA%\RDrive\logs\`.

| Arquivo | Origem |
|---------|--------|
| `logs/rdrive.log` | App Python â exceÃ§Ãµes, subprocesso rclone, mount/connect, erros do watchdog |
| `logs/rdrive.log.1` â¦ `.3` | Backups rotacionados (5 MB cada, 3 geraÃ§Ãµes) |
| `logs/launcher.log` | Bootstrap do `Iniciar.bat` (instalaÃ§Ã£o Python/rclone/WinFsp, pip, erros de inicializaÃ§Ã£o) |

**Ver logs no app:** ConfiguraÃ§Ãµes â **Logs** â *Atualizar* (tail), *Abrir pasta de logs* ou *Abrir launcher.log*.

**DiagnÃ³stico:** ConfiguraÃ§Ãµes â **Testes** â verificaÃ§Ã£o rÃ¡pida do sistema (rclone, WinFsp, instÃ¢ncia Ãºnica, pasta de logs), teste de remote (`lsd` + `about`), teste opcional de velocidade de upload/download de 1 MB em `RDrive_speedtest/`, verificaÃ§Ãµes de montagem por unidade e checklist somente leitura de recursos ON/OFF a partir das configuraÃ§Ãµes atuais. Os resultados tambÃ©m sÃ£o gravados em `rdrive.log` e `human.log`.

**Ver logs manualmente** (substitua pelo caminho do seu clone):

```text
<projeto>\logs\rdrive.log
<projeto>\logs\launcher.log
```

Os arquivos de log estÃ£o no `.gitignore` (`logs/*.log`); a pasta `logs/` Ã© criada na primeira gravaÃ§Ã£o.

Se o app falhar antes da GUI abrir, verifique `launcher.log` primeiro â ele captura erros de bootstrap do `.bat` e do PowerShell que nunca chegam ao logger Python.

## Montagem: disco local vs local de rede (Windows)

O RDrive usa **rclone mount** com **WinFsp**. No Windows, o rclone pode expor a unidade de duas formas:

| Modo | Flag rclone | Explorador |
|------|-------------|------------|
| **Disco local** (padrÃ£o, estilo RaiDrive) | *(sem `--network-mode`)* + `--volname` | **Este PC â Discos locais** (ex.: `GDrive Pessoal (G:)`) |
| **Local de rede** (legado) | `--network-mode` | **Locais de rede** (ex.: `gdrive_pessoal (\\server) (G:)`) |

- **ConfiguraÃ§Ãµes â Geral â** *Montar como disco local (Este PC), estilo RaiDrive pago* â configuraÃ§Ã£o `mount_as_local_drive` (padrÃ£o **ligado**).
- Desligue **somente** se precisar do comportamento antigo WNet / Â«unidade de redeÂ».
- **RaiDrive (pago)** usa driver proprietÃ¡rio em kernel; o rclone nÃ£o replica isso exatamente. A aproximaÃ§Ã£o mais prÃ³xima Ã© **disco fixo WinFsp** (padrÃ£o): sem `--network-mode`, `--volname` amigÃ¡vel a partir do rÃ³tulo da unidade.
- Depois de alterar essa configuraÃ§Ã£o, **desconecte e reconecte** a unidade para um novo processo `rclone mount` com as flags corretas. Confira `logs/rdrive.log` por `[MOUNT] command:`.

### Entrada fantasma em Â«Locais de redeÂ»

Se apÃ³s **Desconectar** vocÃª ainda vir algo como `gdrive_pessoal (\\server) (A:)` com X vermelho em **Este PC â Locais de rede**:

| Sintoma | Causa habitual |
|--------|----------------|
| Aparece em **Locais de rede**, nÃ£o em Discos locais | A unidade foi montada com `--network-mode` (configuraÃ§Ã£o *Montar como disco local* desligada ou sessÃ£o antiga). |
| `net use A: /delete` diz que nÃ£o encontra a conexÃ£o | O WinFsp jÃ¡ liberou a letra, mas o perfil WNet (`HKCU\Network\A`) ou o atalho UNC ficou Ã³rfÃ£o. |
| X vermelho no Explorador | Processo `rclone` terminou sem desmontar o FUSE / mapeamento persistente. |

**O que fazer (por ordem):**

1. **ConfiguraÃ§Ãµes â Geral** â ative *Montar como disco local* e **salve** as configuraÃ§Ãµes (o RDrive passa a gravar essa opÃ§Ã£o).
2. **Desconecte** a unidade no RDrive e **conecte de novo** â confirme em `logs/rdrive.log` que o comando **nÃ£o** inclui `--network-mode`.
3. **ConfiguraÃ§Ãµes â Testes â Limpar mapeamento da letra** â escolha a letra (ex.: `A:`) e execute a limpeza forÃ§ada (WNet, `net use`, registro, Ã³rfÃ£os `rclone`).
4. **Manual (cmd como usuÃ¡rio):**
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

`rclone cmount` Ã© um alias de `rclone mount` no Windows (mesmo backend WinFsp). Ajustes extras do WinFsp sÃ£o possÃ­veis via `rclone mount --fuse-flag` / `--option` se vocÃª experimentar fora do app.

### Performance de exclusÃµes e escrita no Explorador

Apagar/escrever ficheiros no disco montado Ã©, por baixo, **uma chamada HTTP por ficheiro** ao provedor (TeraBox, Drive, OneDrive, â¦). O RDrive afina o `rclone mount` para reduzir o overhead por operaÃ§Ã£o:

**Sempre ligado (perfil Â«EquilibradoÂ»):**

| Flag | Valor | PorquÃª |
|------|-------|--------|
| `--checkers` | `16` (rclone default: 8) | Mais paralelismo de verificaÃ§Ãµes; permite ao WinFsp despachar IRPs concorrentes. |
| `--transfers` | `8` (default: 4) | Limpeza do cache VFS para a nuvem deixa de serializar em 4. |
| `--log-level` | `NOTICE` (era `INFO`) | Cada apagamento deixa de escrever ~3 linhas sÃ­ncronas em `mount.log`. |
| `--vfs-fast-fingerprint` | â | Usa sÃ³ `size+modtime` em vez de hash para identificar entradas no cache. |
| `--dir-cache-time` | `30m` (era `5m`) | Menos re-listagens completas depois de operaÃ§Ãµes em lote. |
| `--poll-interval` | `1m` | Polling menos agressivo de mudanÃ§as externas. |
| `--attr-timeout` | `1s` | Cache de atributos do kernel acelera `stat` repetido. |

**Opt-in: Â«ExclusÃ£o rÃ¡pidaÂ»** (ConfiguraÃ§Ãµes â Geral â *ExclusÃ£o rÃ¡pida*)

Acrescenta flags mais agressivas â desligadas por padrÃ£o por reduzirem a verificaÃ§Ã£o de integridade:

| Flag | Efeito |
|------|--------|
| `--no-checksum` | NÃ£o compara checksum em uploads (ficheiros recÃ©m-enviados nÃ£o sÃ£o re-verificados). |
| `--no-modtime` | NÃ£o preserva data de modificaÃ§Ã£o em uploads (cosmÃ©tico). |
| `--vfs-write-back 5s` | Agrupa writes pendentes antes de subir; menos chamadas, mais throughput. |
| `--dir-cache-time 1h` | Janela ainda maior para o cache de diretÃ³rios. |
| `--log-level ERROR` | SÃ³ erros em `mount.log` â zero I/O por operaÃ§Ã£o rotineira. |

**Quanto melhora?** Em backends com pacer prÃ³prio (TeraBox, baidu), o teto vem do servidor â o ganho tÃ­pico fica em ~1,5â2Ã (8 â 12â16 ficheiros/s). Em backends sem pacer agressivo (Google Drive, Dropbox, OneDrive em conta com quota OK), a remoÃ§Ã£o do `--log-level INFO` + `--vfs-fast-fingerprint` + concorrÃªncia maior costuma render 3â10Ã nas exclusÃµes em lote a partir do Explorador.

**AtenÃ§Ã£o:** depois de mexer no Â«ExclusÃ£o rÃ¡pidaÂ» ou Â«TransferÃªncia aceleradaÂ», **desconecte e reconecte** a unidade para o novo `rclone mount` arrancar com as flags atualizadas. Confirme em `logs/rdrive.log` por `[MOUNT] command:` e `perf=balanced` / `fast-transfer` / `fast-delete` / `fast-delete+transfer`.

### TransferÃªncia acelerada (upload/download via Explorador)

**Opt-in:** ConfiguraÃ§Ãµes â Geral â *TransferÃªncia acelerada*

O RDrive **nÃ£o consegue** aumentar o tamanho de cada parte HTTP que o provedor impÃµe. Em **TeraBox** (backend baidu nÃ£o oficial) e serviÃ§os similares, o upload via API costuma ser fatiado em **~4â5 MiB por pedido** â isso Ã© limite do servidor, nÃ£o do buffer local. O modo acelerado optimiza o que estÃ¡ sob controlo do cliente:

| Flag | Equilibrado | TransferÃªncia acelerada |
|------|-------------|-------------------------|
| `--buffer-size` | valor da unidade (ex. 256M) | `512M` |
| `--vfs-read-ahead` | valor da unidade (ex. 512M) | `1G` |
| `--vfs-read-chunk-size` | rclone default (128M) | `256M` |
| `--vfs-read-chunk-size-limit` | â | `2G` |
| `--transfers` | `8` | `16` |
| `--checkers` | `16` | `24` |
| Google Drive extra | â | `--drive-chunk-size 64M` |

**Por provedor:**

| Provedor | O que o RDrive pode fazer | O que nÃ£o dÃ¡ para contornar |
|----------|---------------------------|-----------------------------|
| **TeraBox / baidu** | Mais paralelismo local; cache VFS maior; menos overhead WinFsp | Chunk de upload ~4â5 MiB; pacer/rate-limit do servidor |
| **Google Drive** | `--drive-chunk-size 64M` + buffers maiores | Quota diÃ¡ria (~750 GB); throttling acima de ~8 transfers |
| **OneDrive / Dropbox** | Buffers e `--transfers` maiores | Limites de volume e throttling da conta |

**Quando usar `rclone copy` em vez do Explorador:** lotes enormes (centenas de GB), retomada fiÃ¡vel (`--resume`), ou quando precisa de `--transfers 32` sem a camada VFS/WinFsp. Exemplo TeraBox:

```bat
rclone copy "D:\Backup" terabox_pessoal:Backup --transfers 8 --checkers 16 -P
```

Combine Â«TransferÃªncia aceleradaÂ» com Â«ExclusÃ£o rÃ¡pidaÂ» se quiser tambÃ©m write-back agregado e menos verificaÃ§Ã£o de integridade em uploads recentes.

## <a id="solucao-problemas-winfsp"></a> SoluÃ§Ã£o de problemas: WinFsp no Windows

O WinFsp Ã© a camada de sistema de arquivos em modo usuÃ¡rio que permite ao rclone expor armazenamento em nuvem como letra de unidade. Sem ele, conectar/montar falha com o diÃ¡logo **WinFsp necessÃ¡rio**.

- **AutomÃ¡tico:** execute `Iniciar.bat` â ele tenta `winget install --id WinFsp.WinFsp -e` quando o WinFsp nÃ£o Ã© detectado.
- **Manual:** https://winfsp.dev/rel/ ou `winget install --id WinFsp.WinFsp -e`
- **Verificar:** `where winfsp-x64` ou confira `C:\Program Files (x86)\WinFsp\bin\winfsp-x64.dll`
- O WinFsp instala em todo o sistema (pode pedir UAC). Se o winget falhar, instale manualmente e reinicie o RDrive.

## SoluÃ§Ã£o de problemas: rclone no Windows

- Se o `rclone` nÃ£o for reconhecido, instale manualmente:
  - `winget install --id Rclone.Rclone -e --scope user`
  - Downloads oficiais: https://rclone.org/downloads/
- ApÃ³s a instalaÃ§Ã£o, feche e reabra o terminal.
- Configure o primeiro remote no app (`Adicionar` > **Conectar conta**) ou manualmente no terminal:
  - `rclone config`
- Valide remotes no terminal:
  - `rclone listremotes`

### Cofre encriptado (experimental, desligado por padrÃ£o)

Por padrÃ£o o RDrive usa **modo simples**: `drives.json` e `settings.json` em texto legÃ­vel no perfil local, **sem** pedir senha mestra na inicializaÃ§Ã£o.

O **cofre encriptado** (`drives.enc` / `settings.enc`) Ã© **opcional e experimental**. Ative em **ConfiguraÃ§Ãµes â SeguranÃ§a â Cofre encriptado (experimental)**:

| Modo | Comportamento |
|------|----------------|
| **Cofre DESLIGADO** (padrÃ£o) | Sem senha mestra; dados em JSON no perfil local |
| **Cofre LIGADO** (experimental) | Senha mestra na inicializaÃ§Ã£o; dados criptografados localmente; recuperaÃ§Ã£o por e-mail OTP |

InstalaÃ§Ãµes novas comeÃ§am com `vault_enabled: false` em `profile_meta.json`. Arquivos `.enc` antigos **nÃ£o** ativam o cofre sozinhos: o RDrive usa `drives.json` / `settings.json` em modo simples atÃ© ativar explicitamente em **ConfiguraÃ§Ãµes â SeguranÃ§a** (com a senha mestra correta para reutilizar `.enc` existentes). Ao desativar, os dados criptografados sÃ£o exportados para JSON e os `.enc` removidos â a aÃ§Ã£o exige confirmaÃ§Ã£o.

**Aviso (modo simples):** qualquer pessoa com acesso Ã  pasta de perfil (`%LOCALAPPDATA%\RDrive\â¦`) pode ler unidades e configuraÃ§Ãµes. Use apenas em ambientes confiÃ¡veis.

Para ativar o cofre via variÃ¡vel de ambiente (legado / scripts):

```bash
set RDRIVE_MASTER_PASSWORD=your-strong-password
python -m rdrive
```

Quando o cofre estÃ¡ ativo, o RDrive ignora a variÃ¡vel se `vault_enabled` estiver OFF em `profile_meta.json`.

### Manter sessÃ£o iniciada (este PC)

Na tela **Desbloquear cofre**, vocÃª pode marcar **Manter sessÃ£o iniciada** para salvar a senha mestra criptografada neste computador (Windows DPAPI, vinculada ao usuÃ¡rio Windows atual). Na prÃ³xima inicializaÃ§Ã£o o RDrive tenta restaurar a sessÃ£o sem pedir a senha.

- Os dados ficam em `%LOCALAPPDATA%\RDrive\session\<profile_id>\remembered_vault.blob` â nunca em texto simples.
- Cada conta (e-mail / `profile_id`) tem sua prÃ³pria sessÃ£o memorizada.
- Em **ConfiguraÃ§Ãµes â SeguranÃ§a**, use **Encerrar sessÃ£o neste dispositivo** para apagar a sessÃ£o memorizada.
- **SeguranÃ§a:** protege apenas contra leitura casual no disco; quem usar sua sessÃ£o Windows neste PC pode desbloquear o cofre. NÃ£o use em PCs compartilhados ou nÃ£o confiÃ¡veis.

### RecuperaÃ§Ã£o de senha (e-mail OTP)

No desbloqueio, use **Esqueci a senha** para verificar seu e-mail de recuperaÃ§Ã£o com um cÃ³digo de 6 dÃ­gitos (10 minutos, mÃ¡ximo 3 tentativas).

Configure em **ConfiguraÃ§Ãµes â SeguranÃ§a**:

- **E-mail de recuperaÃ§Ã£o** â obrigatÃ³rio para redefiniÃ§Ã£o; armazenado em `recovery_profile.json` (legÃ­vel antes do desbloqueio).
- **SMTP avanÃ§ado** (opcional) â envia cÃ³digos via `smtplib` SSL (porta 465). Se o SMTP nÃ£o estiver configurado, o modo dev grava cÃ³digos em `logs/password_reset_otp.log` e os mostra em um diÃ¡logo.

#### Senha de app do Gmail (exemplo)

1. Ative a verificaÃ§Ã£o em duas etapas na sua conta Google.
2. Abra [Senhas de app do Google](https://myaccount.google.com/apppasswords) e crie uma para Â«MailÂ».
3. No RDrive â ConfiguraÃ§Ãµes â SeguranÃ§a â SMTP avanÃ§ado:
   - Host: `smtp.gmail.com`
   - Porta: `465`
   - UsuÃ¡rio: seu endereÃ§o Gmail
   - Senha: a senha de app de 16 caracteres (nÃ£o a senha normal do Gmail)
   - De: o mesmo endereÃ§o Gmail

#### LimitaÃ§Ã£o criptogrÃ¡fica (`.enc`)

Se `drives.enc` / `settings.enc` jÃ¡ existirem e vocÃª **esqueceu** a senha mestra, os dados criptografados **nÃ£o** podem ser descriptografados sem a senha antiga. ApÃ³s verificaÃ§Ã£o por e-mail, o RDrive sÃ³ pode:

- **Limpar o cofre** e criar um novo armazenamento criptografado vazio (todas as unidades/configuraÃ§Ãµes salvas em `.enc` sÃ£o perdidas), ou
- Alterar a senha normalmente nas configuraÃ§Ãµes se vocÃª ainda souber a senha atual.

Estado JSON em texto (sem `.enc`) pode ser migrado para uma nova senha mestra apÃ³s OTP sem perda de dados.

### Repor senha / cofre perdido

Se a senha mestra foi perdida (por exemplo apÃ³s alteraÃ§Ãµes manuais em `drives.enc`), os dados criptografados **nÃ£o** podem ser lidos sem a senha antiga. Para voltar a usar o RDrive com cofre novo:

1. **Feche** o RDrive (bandeja e processo).
2. Na raiz do projeto, execute `scripts\reset_vault.bat` (ou `powershell -File scripts\reset_vault.ps1`), digite **`RESET`** quando pedido e confirme. Isso remove `drives.enc`, `settings.enc` e `recovery_token.json`, mas **mantÃ©m** `drives.json` / `settings.json` legados se existirem. Detalhes em `logs\reset_vault.log`. Para apagar tambÃ©m JSON e perfis multi-usuÃ¡rio: `reset_vault.ps1 -WipeAll`.
3. **Reinicie** com `Iniciar.bat`. Na primeira tela, defina o **e-mail de recuperaÃ§Ã£o** e a **nova senha mestra** (fluxo de criaÃ§Ã£o do cofre). JSON legado Ã© migrado automaticamente na abertura.

Alternativa no app (com cofre jÃ¡ desbloqueado): **ConfiguraÃ§Ãµes â SeguranÃ§a â Repor cofre (perder dados criptografados)** â confirmaÃ§Ã£o dupla com texto `RESET`, depois reinicie com `Iniciar.bat`.

## Conectar uma nuvem (com e sem configuraÃ§Ã£o automÃ¡tica)

A WebUI em `Static/` guia a conexÃ£o em trÃªs passos (**Escolha o provedor** â **Detalhes** â **ConexÃ£o**). Use **`Iniciar.bat`** para o RDrive completo (PyQt + bridge + montagem real). Para desenvolver sÃ³ a interface, **`scripts\launchers\DevStatic-Live.bat`** inicia o mesmo fluxo com recarga automÃ¡tica ao salvar arquivos em `Static/`; **`scripts\launchers\DevStatic-Browser.bat`** abre um preview no navegador (sem bridge â conexÃ£o/montagem nÃ£o funcionam).

### Provedores: automÃ¡tico vs guiado vs terminal

Na grade **Adicionar**, provedores com distintivo **Auto** usam OAuth no navegador. Os com **formulÃ¡rio guiado** (passo 1) configuram o rclone sem terminal. O restante usa `rclone config` no terminal.

| OAuth automÃ¡tico | Guiado (formulÃ¡rio WebUI) | Manual (terminal) |
|------------------|---------------------------|-------------------|
| Google Drive (`drive`) | Amazon S3 (`s3`) | HDFS (`hdfs`) |
| OneDrive (`onedrive`) | WebDAV (`webdav`) | Azure Blob, Google Cloud Storage, â¦ |
| Dropbox (`dropbox`) | SFTP (`sftp`) | Backends listados pelo seu `rclone` sem formulÃ¡rio |
| Box (`box`) | FTP (`ftp`) | |
| pCloud (`pcloud`) | HTTP (`http`, somente leitura) | |
| Mega (`mega`) | SMB / CIFS (`smb`) | |
| | TeraBox (`terabox`, experimental) | |

Nos provedores **Auto**, **Alternativa: configurar no terminal** continua disponÃ­vel. Nos **guiados**, use **Modo tÃ©cnico** se preferir o assistente rclone interativo.

### Fluxo com configuraÃ§Ã£o automÃ¡tica

1. **Adicionar** (barra ou lista vazia).
2. **Passo 1 â Escolha o provedor:** selecione um serviÃ§o com distintivo **Auto** (ex.: Google Drive, OneDrive).
3. **Passo 2 â Detalhes:** defina um **nome da unidade** Ãºnico, o **Remote (rclone)** sugerido (ex.: `gdrive_pessoal`) e a **letra de montagem** (ex.: `G:`). Opcional: montar ao abrir o RDrive / desmontar ao fechar.
4. **Passo 3 â ConexÃ£o:** clique **ConfiguraÃ§Ã£o automÃ¡tica â conectar conta**. O navegador abre para login OAuth; o RDrive cria o remote no rclone e valida o acesso.
5. **Salvar unidade.** Se **Conectar unidade apÃ³s salvar** estiver marcado, a montagem comeÃ§a em seguida.
6. Na lista de unidades, use o interruptor **Montar unidade** (ou aguarde a inicializaÃ§Ã£o automÃ¡tica se configurou montagem ao abrir).

ValidaÃ§Ã£o opcional no terminal: `rclone about gdrive_pessoal:` ou `rclone lsd gdrive_pessoal:`.

### Fluxo sem configuraÃ§Ã£o automÃ¡tica (guiado ou terminal)

Use este fluxo para S3, WebDAV, SFTP, FTP, HTTP, SMB e quando o OAuth automÃ¡tico nÃ£o estiver disponÃ­vel ou falhar.

**PrÃ©-requisitos**

- **`rclone` no PATH** â confirme com `rclone version` (o `Iniciar.bat` tenta instalar via `winget` se faltar).
- **Cofre desbloqueado** â o RDrive precisa de sessÃ£o ativa para salvar unidades e montar.

**Passos (formulÃ¡rio guiado)**

1. **Adicionar** â escolha o provedor (ex.: SFTP, FTP, SMB).
2. **Passo 1:** preencha host/URL/credenciais â **Testar conexÃ£o** (cria remote temporÃ¡rio e executa `rclone lsd`).
3. **Conectar e salvar** â cria o remote definitivo, valida e grava a unidade (com assistente automÃ¡tico ativo, tambÃ©m sugere nome e letra).
4. Na lista, ligue **Montar unidade**.

**Passos (somente terminal)**

1. **Adicionar** â provedor sem formulÃ¡rio (ex.: HDFS) ou **Modo tÃ©cnico** em um provedor guiado.
2. **Configurar manualmente (terminal)** â `rclone config` com documentaÃ§Ã£o do backend no navegador.
3. Confirme com `rclone listremotes` e `rclone lsd nome_remote:`.
4. Volte ao passo **Detalhes**, preencha **Remote (rclone)** e **Salvar unidade**.

### OneDrive empresarial

- **ConfiguraÃ§Ã£o automÃ¡tica:** o fluxo OAuth cobre contas **pessoais** e muitos cenÃ¡rios **empresariais** (Microsoft 365). Se o rclone pedir tipo de drive durante a criaÃ§Ã£o automÃ¡tica, o padrÃ£o interno Ã© OneDrive pessoal (`onedrive`).
- **Manual recomendado** para **SharePoint**, bibliotecas especÃ­ficas ou quando precisar escolher explicitamente **OneDrive personal** vs **OneDrive for Business** no assistente `rclone config` (pergunta `drive_type` / `type`).
- Remote de exemplo: `onedrive_trabalho` â depois copie esse nome para o campo **Remote (rclone)** no passo Detalhes.

### Problemas comuns

| Problema | O que fazer |
|----------|-------------|
| **App muito pesado / arranque lento / interface engasga** | O **Modo leve** estÃ¡ activo por omissÃ£o (ConfiguraÃ§Ãµes â Geral â *Modo leve*). Se vem de uma instalaÃ§Ã£o antiga, force via variÃ¡vel de ambiente `RDRIVE_LITE=1` antes de `Iniciar.bat`. Pausa o watchdog quando minimizado, desliga animaÃ§Ã£o da borda, atrasa varreduras de integridade no arranque (4â5s) e agrupa snapshots da WebUI. Para feedback em tempo real durante desenvolvimento, defina `RDRIVE_LITE=0` ou desligue o toggle. |
| Montagem falha com **WinFsp necessÃ¡rio** | Instale WinFsp (`Iniciar.bat` tenta via `winget`, ou seÃ§Ã£o [SoluÃ§Ã£o de problemas: WinFsp](#solucao-problemas-winfsp) abaixo). |
| **Este nome jÃ¡ estÃ¡ em uso** | Escolha outro **nome da unidade** â nomes sÃ£o Ãºnicos no cofre. |
| **A letra X: jÃ¡ estÃ¡ em uso** | Outra unidade RDrive, `net use` ou processo `rclone` ocupa a letra; escolha outra ou use ConfiguraÃ§Ãµes â **Testes** â *Limpar mapeamento da letra*. |
| OAuth / remote invÃ¡lido | Consulte `logs/rdrive.log` (comandos rclone, erros de mount). ConfiguraÃ§Ãµes â **Logs** â *Atualizar* ou **Testes** para diagnÃ³stico rÃ¡pido. |
| Assistente de terminal nÃ£o abre | SÃ³ funciona com o RDrive em execuÃ§Ã£o via `Iniciar.bat` / `scripts\launchers\DevStatic-Live.bat` (nÃ£o no preview `scripts\launchers\DevStatic-Browser.bat`). |
| VÃ¡rios diÃ¡logos Â«Reiniciar o RDrive?Â» ao editar `.bat` | Com `DevStatic-Live.bat` (`RDRIVE_STATIC_LIVE=1`) o watchdog ignora `scripts\launchers\`; noutros modos desative **Reiniciar ao alterar cÃ³digo** ou active **Modo compatÃ­vel IDE** em ConfiguraÃ§Ãµes â Watchdog. |
| Cookies TeraBox: extensÃ£o nÃ£o instala no arranque | Por omissÃ£o (Modo leve) o `Iniciar.bat` salta `bootstrap_cookies_extension.ps1`; a extensÃ£o Ã© instalada quando abrir o Chrome dedicado em ConfiguraÃ§Ãµes â TeraBox. Para forÃ§ar install eager, defina `RDRIVE_BOOTSTRAP_COOKIES_EAGER=1` antes do launcher. |

Matriz tÃ©cnica de backends e limitaÃ§Ãµes: `ARCHITECTURE.md` Â§10.

## Roadmap (paridade RaiDrive â nÃ£o implementado)

Funcionalidades identificadas na comparaÃ§Ã£o com o RaiDrive, planejadas para iteraÃ§Ãµes futuras (nÃ£o incluÃ­das nesta sessÃ£o):

- **Assistente SharePoint completo** â wizard WebUI para bibliotecas/document libraries com escolha de site e drive ID.
- **Bloqueio de arquivos (file lock)** â exclusÃ£o cooperativa durante ediÃ§Ã£o em unidades montadas.
- **Criptografia de cache VFS** â cache local criptografado por unidade ou global.
- **Seletor de Ã¡rvore de pastas** â seletor visual de subpastas remotas ao criar/editar unidade (em vez de texto livre em `root_path`).

## ObservaÃ§Ãµes

- O aplicativo foi projetado para Windows e Linux.
- **Reserva de cota** (`enable_preallocation`, padrÃ£o ligado): ConfiguraÃ§Ãµes â Geral â *Reservar espaÃ§o antes de gravar arquivos grandes*. Usa `ReservationLedger` + `QuotaMonitor` ao planejar divisÃµes em faixas (stripe); eventos aparecem no feed do log humano.
- Recursos experimentais (divisÃ£o em faixas, pool union, watchdog de desenvolvimento) permanecem em **Por sua conta e risco** e podem exigir aceitaÃ§Ã£o de risco.
- A primeira implementaÃ§Ã£o foca em arquitetura e fluxos operacionais seguros.

## Git e contribuiÃ§Ã£o

Este projeto segue um fluxo Git documentado em `docs/GIT-CURSOR.md` (commits, branches, o que nÃ£o versionar). O repositÃ³rio pÃºblico estÃ¡ em [github.com/MiguelSilvaPorto/RDrive](https://github.com/MiguelSilvaPorto/RDrive).

Para clonar:

```bash
git clone https://github.com/MiguelSilvaPorto/RDrive.git
cd RDrive
```

Para abrir issues ou pull requests no GitHub (requer [GitHub CLI](https://cli.github.com/) autenticado):

```bash
gh issue create
gh pr create
```
