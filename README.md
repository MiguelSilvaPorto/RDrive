# RDrive

Aplicativo desktop inspirado no RaiDrive, construído sobre o [rclone](https://rclone.org/) — monta armazenamento em nuvem como unidade local no Windows.

## Transparência legal e responsabilidade

Esta secção descreve, de forma directa, o que o RDrive **é** e **não é**, os riscos ao usar serviços de nuvem por meios não oficiais, e as suas responsabilidades como utilizador ou empresa que avalia este repositório.

### O que o RDrive é — e o que não é

| | |
|---|---|
| **É** | Projecto independente de hobby/comunidade, código aberto, mantido por voluntários |
| **Não é** | Produto comercial, serviço empresarial com SLA, ou fork oficial do RaiDrive |
| **Não representa** | Google, Microsoft, Dropbox, TeraBox/Dubox, a equipa do [rclone](https://rclone.org/), WinFsp, ou qualquer outro provedor ou upstream |

A inspiração no RaiDrive é apenas funcional (montar nuvens como unidades locais). **Não há afiliação, patrocínio ou endosso** de terceiros.

### Termos de serviço dos provedores

Muitos provedores de nuvem **proíbem ou limitam** acesso por APIs não documentadas, automação não autorizada ou reutilização de cookies/sessões web. O RDrive usa o [rclone](https://rclone.org/) (OAuth, tokens ou credenciais que você configura) e, no TeraBox, um backend comunitário + cookie de sessão — ver [TeraBox (experimental)](#terabox-experimental) e `ARCHITECTURE.md`.

**Riscos possíveis:** suspensão ou bloqueio de conta, revogação de tokens, perda de acesso a dados, ou outras acções do provedor. **A decisão de usar o RDrive com a sua conta é sua.** Leia os termos do serviço de cada nuvem antes de ligar uma unidade. O TeraBox é o caso mais sensível por depender de sessão web experimental.

### Segurança e privacidade

- **Dados locais:** configurações, remotes do rclone, cookies exportados e credenciais ficam no perfil `%LOCALAPPDATA%\RDrive\` (e em `rclone.conf` no mesmo perfil ou caminho que configurar). Por omissão, JSON legível — ver [Cofre encriptado](#cofre-encriptado-experimental-desligado-por-padrão).
- **Cofre opcional:** encriptação local com senha mestra; não substitui boas práticas no PC (sessão Windows, backups, antivírus).
- **Telemetria:** o RDrive **não envia** dados de uso, analytics ou conteúdo de ficheiros para servidores do autor. Comunicação de rede típica: OAuth dos provedores, APIs rclone, verificação de updates no GitHub Releases, e SMTP opcional para recuperação de senha (se configurado por você).
- **Repositório Git:** **nunca** faça commit de `rclone.conf`, cookies, tokens, senhas ou `%LOCALAPPDATA%\RDrive\`. Estão no `.gitignore`; detalhes em `docs/GIT-CURSOR.md`.
- **Cookies e sessões:** trate ficheiros de cookie como credenciais — quem tiver acesso ao perfil local pode impersonar a sessão na nuvem.

### Licenças de software

| Componente | Licença / notas |
|------------|-----------------|
| **Código RDrive (este repositório)** | Ainda **sem ficheiro `LICENSE` na raiz** — recomenda-se adoptar **MIT** e um `THIRD_PARTY_NOTICES.md` com atribuições consolidadas |
| **[rclone](https://rclone.org/)** | MIT — build comunitário TeraBox: `tools/rclone-extra/NOTICE` |
| **PyQt6 / PyQt6-WebEngine** | GPL — relevante se **distribuir** binários ligados ao Qt (modo WebUI legado); UI CTk padrão não depende de Qt em runtime |
| **[WinFsp](https://winfsp.dev/)** | Licença própria (gratuita para uso comum) — necessário para montagem no Windows |
| **Extensão [Get cookies.txt LOCALLY](https://github.com/kairi003/Get-cookies.txt-LOCALLY)** | MIT — `tools/get-cookies-txt-locally/NOTICE` |
| **Ícones de provedores** | Marcas de terceiros; assets em `src/rdrive/assets/providers/` — uso para identificação na UI |

Binários externos (rclone TeraBox, extensão cookies Edge) são descarregados em runtime; ver `docs/ESTRUTURA.md` § `tools/`.

### Sem garantia

Os avisos **WARNING** e **IMPORTANT** logo abaixo aplicam-se aqui: software **instável, em desenvolvimento**, sem garantia de funcionamento, disponibilidade ou compatibilidade futura com APIs dos provedores. **Use por sua conta e risco.** O autor e colaboradores **não se responsabilizam** por perda de dados, indisponibilidade, danos indirectos ou consequências do uso com contas pessoais ou empresariais.

### Marcas registadas

Nomes e logótipos de Google Drive, OneDrive, Dropbox, TeraBox, Amazon S3, RaiDrive e outros aparecem **apenas para identificar** o serviço correspondente. São marcas dos respectivos titulares. **RDrive** é o nome deste projecto independente e **não** implica associação com RaiDrive® ou qualquer provedor listado.

### Atualização automática

Descrita em [Atualização interactiva (GitHub)](#atualização-interactiva-github): verifica releases estáveis no GitHub; **só descarrega e aplica** se escolher **Atualizar agora** no diálogo (excepto modo avançado `RDRIVE_AUTO_UPDATE_SILENT=1`). Pode desactivar com `RDRIVE_AUTO_UPDATE=0` ou nas definições. O zip vem de [GitHub Releases](https://github.com/MiguelSilvaPorto/RDrive/releases) — revise o código ou desactive se a sua política interna exigir aprovação manual de binários.

### Uso ético

- Use **apenas contas e dados que lhe pertencem** ou para os quais tem autorização explícita.
- **Não** use o RDrive para contornar paywalls, quotas abusivas, partilha não autorizada de conteúdo protegido, ou violação de termos de serviço ou lei aplicável.
- Em ambientes corporativos, obtenha aprovação de TI/segurança antes de montar nuvens de trabalho — políticas internas podem proibir clientes não homologados.

> [!WARNING]
> **Versão semi-estável (em desenvolvimento)** — canal recomendado para testadores: UI CustomTkinter, assistente de ligação, TeraBox Edge em duas fases, OAuth em browser isolado e instalador Windows (`docs/INSTALLER.md`); ainda pode quebrar. **Não usar em produção.**

> [!IMPORTANT]
> **O RDrive monta o TeraBox como unidade de disco local no Windows** — letra em «Este PC» via `rclone mount` + **WinFsp**, com build **não oficial** do rclone (backend `terabox`, PR [rclone#8508](https://github.com/rclone/rclone/pull/8508)) e autenticação por **cookie de sessão** (`ndus`), importado do **Edge isolado** via extensão `cookies.txt`.
>
> Existem PRs, forks e outros wrappers que também ligam o TeraBox ao rclone; o RDrive distingue-se pela **UI CustomTkinter** (padrão), assistente de ligação integrado, agente TeraBox (Playwright + Edge isolado), combinar nuvens (`union`), montagem WinFsp, bandeja do sistema, bootstrap `Iniciar.bat` e diagnóstico em **Definições → Testes**. A WebUI em `Static/` permanece como modo legado.
>
> **Experimental e não oficial:** depende de backend comunitário do rclone e de sessão web do TeraBox; não é produto homologado pelo provedor. Detalhes na seção [TeraBox (experimental)](#terabox-experimental).

Repositório público: [github.com/MiguelSilvaPorto/RDrive](https://github.com/MiguelSilvaPorto/RDrive)

## Status atual

**Descarregar (semi-estável):** [GitHub Releases — RDrive Semi-stable](https://github.com/MiguelSilvaPorto/RDrive/releases) — use o asset **`RDrive-*-windows.zip`** (pasta `RDrive-<tag>/` após extrair). O zip automático **Source code** também funciona, mas extrai para `MiguelSilvaPorto-RDrive-<hash>/` e na 1.ª execução o bootstrap demora vários minutos **sem parecer que abriu nada** se fechar a consola cedo; aguarde ou veja `logs\launcher.log`. Instalador opcional: `docs/INSTALLER.md`, `scripts/build/build_installer.ps1`. Publicação: `docs/RELEASE.md`. Canal Git: [`semi-stable`](https://github.com/MiguelSilvaPorto/RDrive/tree/semi-stable) / [`main`](https://github.com/MiguelSilvaPorto/RDrive/tree/main). Atualização automática na app ignora pré-releases e tags com sufixo (`-unstable`, `-semi-stable`, etc.).

Aplicação desktop **funcional em desenvolvimento** (semi-estável, não produção). O caminho recomendado é **CustomTkinter** (`RDRIVE_UI=ctk`, predefinido no `Iniciar.bat`).

**Já disponível (CTk):**

- Lista de unidades: montar/desmontar, renomear, alterar letra, auto-início, abrir no Explorador
- **Adicionar unidade** com assistente de ligação (OAuth, formulários guiados, TeraBox com **Ligar conta TeraBox**)
- **Assistente de nuvem** (painel CTk), OAuth em browser isolado, agente TeraBox (Edge + extensão cookies)
- **Combinar nuvens** do mesmo provedor (`rclone union`)
- **Definições**: Geral (modo leve, montagem local, desempenho), Segurança (cofre opcional), Logs, **Testes** (rclone, WinFsp, remote, montagens, benchmark), Risco (stripe, watchdog)
- Bandeja do sistema (`pystray`), minimizar ao fechar (X), atualização interactiva via GitHub Releases
- Motor: `MountManager`, `RcloneCli`, `CloudSetupAgent`, cofre JSON ou encriptado, reserva de cota / stripe (experimental)

**Legado / fallback:** WebUI `Static/` (PyQt6-WebEngine) e UI PyQt nativa (`RDRIVE_UI=web` ou `native`). Paridade CTk ≈ 85 % — ver `docs/CTK-MIGRATION.md`.

**Ainda principalmente na WebUI ou PyQt:** alguns fluxos de cofre (esqueci senha, switch user), transfer jobs, stripe splitter visual, pasta partilhada OAuth (mapear subpasta) na CTk.

## Ícone do aplicativo

O ícone da janela e da barra de tarefas do RDrive é o botão metálico 3D com marca de sincronização em nuvem ciano, empacotado em `src/rdrive/assets/branding/`:

| Arquivo | Finalidade |
|---------|------------|
| `rdrive_icon_source.png` | Recorte mestre (256×256, fundo transparente) |
| `rdrive_icon_{16,24,32,48,64,128,256}.png` | PNGs em vários tamanhos (Qt legado e referência) |
| `rdrive.ico` | Ícone Windows multi-tamanho (bandeja e atalhos) |

Ícones via `importlib.resources` (`rdrive.ui.foundation.app_icon`):

- **CTk (padrão):** janela + **bandeja** (`rdrive.ui.ctk.system_tray` com `pystray` + Pillow) — **Abrir**, **Montar todas**, **Desmontar todas**, submenu **Abrir unidade**, **Sair**; fechar (X) minimiza para a bandeja quando configurado
- **WebUI / PyQt legado:** `QSystemTrayIcon` em `rdrive.ui.system_tray` após `MainWindow.show()`

Para regenerar os assets (requer **Pillow** no venv):

```bash
.venv\Scripts\python.exe scripts\dev\build_app_icons.py [caminho\para\imagem.png]
```

Fonte padrão: `%USERPROFILE%\Downloads\Gemini_Generated_Image_6knqxo6knqxo6knq.png`. O `rembg` opcional melhora a remoção de fundo; caso contrário, o script remove o fundo cinza plano.

## Documentação do projeto

- Arquitetura: `ARCHITECTURE.md`
- Estrutura de pastas: `docs/ESTRUTURA.md`
- Migração CTk / paridade: `docs/CTK-MIGRATION.md`
- Edge isolado (OAuth, TeraBox): `docs/RDRIVE-ISOLATED-BROWSER.md`
- Instalador Windows: `docs/INSTALLER.md`
- Referência de UI (legado): `docs/ui-reference.md`
- Fluxo Git: `docs/GIT-CURSOR.md`

## Interface — CustomTkinter (padrão) vs. WebUI (legado)

O **`Iniciar.bat` define `RDRIVE_UI=ctk`** por defeito. A UI **CustomTkinter** (`src/rdrive/ui/ctk/`) é a interface principal — sem Chromium embebido, tema escuro alinhado à antiga `Static/`. A WebUI HTML em `Static/` e a lista PyQt antiga continuam como fallback.

| Variável `RDRIVE_UI` | Resultado |
|----------------------|-----------|
| `ctk` (predefinido no launcher) | UI CustomTkinter |
| _não definido_ (sem launcher) | CTk se `customtkinter` instalado; senão WebUI |
| `web` | WebUI `Static/` + PyQt6-WebEngine |
| `native` | Lista PyQt sem WebEngine (`RDRIVE_WEBUI=0`) |

Modo legado WebUI: `set RDRIVE_UI=web && Iniciar.bat`. Desenvolvimento WebUI: `scripts\launchers\DevStatic-Live.bat`.

> [!NOTE]
> **`Static/` está deprecado** para novas funcionalidades. Mantém-se no repositório como fallback; desenvolvimento activo em `src/rdrive/ui/ctk/`.

## Atualização interactiva (GitHub)

Verifica releases **estáveis** em [github.com/MiguelSilvaPorto/RDrive](https://github.com/MiguelSilvaPorto/RDrive) ~5 s após abrir a UI e depois a cada 24 h. Se já estiver na versão mais recente (`pyproject.toml`), não há aviso.

Com update disponível: diálogo **«Encontrámos uma nova versão»** (notas, **Atualizar agora**, **Mais tarde**, **Saber mais**). Só **Atualizar agora** descarrega o zip e reinicia. **Mais tarde** deixa badge **Nova atualização disponível** na barra lateral CTk.

**Preservado:** `%LOCALAPPDATA%\RDrive\` (unidades, cofre, definições), `rclone.conf`, mounts activos (detach no reinício).

| Variável | Efeito |
|----------|--------|
| `RDRIVE_AUTO_UPDATE=0` | Desactiva verificação |
| `RDRIVE_AUTO_UPDATE_SILENT=1` | Aplica sem diálogo (power users) |
| `RDRIVE_AUTO_UPDATE_CHECK_ONLY=1` | Só regista no log |
| `RDRIVE_AUTO_UPDATE_INTERVAL_HOURS` | Intervalo (predef.: 24) |

Release estável = GitHub non-prerelease + tag semver sem `-beta`, `-unstable`, `-rc`. `auto_update_enabled` em `settings.json` controla só a verificação.

## Instalador Windows

Instalação sem Git: `RDriveSetup.exe` (pasta, utilizador actual vs. todos, atalho opcional). Construir o instalador: ver **`docs/INSTALLER.md`** (Inno Setup 6).

## Requisitos

- Python 3.11+
- **customtkinter ≥ 5.2**, **pystray**, **Pillow** — UI CTk e bandeja
- **playwright** — agente TeraBox e instalação assistida da extensão cookies (channel=msedge — Edge do sistema)
- **PyQt6** + **PyQt6-WebEngine** — só necessários para `RDRIVE_UI=web` ou componentes legado
- **rclone** no PATH (TeraBox: build comunitário com backend `terabox`)
- **WinFsp** (Windows) — `rclone mount`; o `Iniciar.bat` tenta `winget` se faltar
- FUSE3 (Linux) para montagens

### PyQt6-WebEngine (modo WebUI legado)

Só relevante com `RDRIVE_UI=web`. O `Iniciar.bat` instala `requirements.txt` e corre `scripts\bootstrap\verify_webengine.ps1`.

**Reparo:**

```powershell
.venv\Scripts\python.exe -m pip install --upgrade "PyQt6-WebEngine>=6.6.0"
.\scripts\bootstrap\verify_webengine.ps1
```

**Se o venv estiver corrompido**, recrie-o (feche o RDrive antes):

```powershell
Remove-Item -Recurse -Force .venv
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\bootstrap\verify_webengine.ps1
```

**Diagnóstico:** import OK mas página em branco — execute `verify_webengine.ps1`. Se a WebUI (`Static/`) não carregar, reinstale PyQt6-WebEngine.

## Executar

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m rdrive
```

### WebUI legado (`Static/`)

**Não é o modo predefinido.** Use `RDRIVE_UI=web` (ou fallback automático se CTk não estiver disponível). O `Iniciar.bat` define `RDRIVE_STATIC_DIR=<projeto>/Static`.

| Variável | Padrão | Finalidade |
|----------|--------|------------|
| `RDRIVE_WEBUI` | `1` em modo `web` | `0` força lista PyQt nativa |
| `RDRIVE_STATIC_DIR` | `<projeto>/Static` | Pasta com `index.html` |
| `RDRIVE_STATIC_LIVE` | desligado | Recarga automática (~0,4 s) |
| `RDRIVE_PROJECT_ROOT` | `Iniciar.bat` | Raiz do projeto |

**Desenvolver a WebUI:** `scripts\launchers\DevStatic-Live.bat` ou `DevStatic-Browser.bat` (porta 8765). Ícones: `python scripts/dev/sync_static_providers.py` → `Static/providers/`.

### Assistente de ligação (CTk e WebUI)

Em **Adicionar unidade**, o **Assistente de ligação** (`CloudSetupAgent` em `src/rdrive/core/cloud/cloud_setup_agent.py`) cobre OAuth, formulários guiados e progresso. Na **CTk** está em `cloud_assistant_panel.py`; na **WebUI**, via bridge QWebChannel (`listProviders`, eventos `cloud_setup_progress`).

#### Matriz de modos

| Modo | Provedores (exemplos) | O que você faz |
|------|------------------------|----------------|
| **OAuth automático** | Google Drive, OneDrive, Dropbox, Box, pCloud, Mega | «Configuração automática» → login no navegador → remote criado |
| **Guiado (formulário)** | S3, WebDAV, SFTP, FTP, HTTP, SMB/CIFS, TeraBox (experimental) | Credenciais → **Testar conexão** → **Conectar e salvar** / **Guardar unidade** (CTk) |
| **Manual (terminal)** | HDFS, Azure Blob, GCS, backends raros sem formulário | «Assistente manual (terminal)» ou `rclone config` |

Comandos bridge: `startCloudSetupAgent`, `cancelCloudSetupAgent`, `getCloudSetupState`, `testGuidedConnection`, `openProviderDocs`. Eventos: `cloud_setup_progress`, `cloud_setup_finished`.

#### Backends com formulário guiado

| Backend | Campos principais | Notas |
|---------|-------------------|--------|
| `s3` | endpoint, access key, secret, região, bucket (teste) | `pass` no rclone; teste com `rclone lsd remote:` ou `remote:bucket` |
| `webdav` | URL, usuário, senha | |
| `sftp` | host, porta (22), usuário, senha **ou** arquivo de chave **ou** PEM | Porta padrão 22 |
| `ftp` | host, porta (21), usuário, senha, FTPS explícito | Dicas em PT em falhas: firewall, FTP passivo, TLS |
| `http` | URL | Montagem somente leitura |
| `smb` | host, compartilhamento, domínio (opcional), usuário, senha | Compartilhamento = nome SMB, sem `\\` |
| `terabox` | cookie `ndus` | Requer rclone não oficial; OAuth/TeraBox inalterado |

#### Seções README por protocolo

- <a id="agente-configuracao"></a> Esta seção (índice)
- <a id="agente-oauth"></a> OAuth (Drive, OneDrive, …)
- <a id="agente-s3"></a> S3
- <a id="agente-webdav"></a> WebDAV
- <a id="agente-sftp"></a> SFTP
- <a id="agente-ftp"></a> FTP / FTPS
- <a id="agente-http"></a> HTTP
- <a id="agente-smb"></a> SMB / CIFS
- <a id="agente-terabox"></a> TeraBox (experimental)
- <a id="agente-manual"></a> Terminal (`rclone config`) — HDFS e outros

Na WebUI, os botões **README** e **Documentação rclone** abrem a seção local ou a página oficial do backend.

#### Ideias futuras (backlog)

- Importar sessão FileZilla (XML) ou WinSCP
- Descoberta de compartilhamentos SMB na LAN
- Colar URI (`ftp://user@host/path`) e preencher o formulário automaticamente

### TeraBox (experimental)

- O **rclone oficial** **não inclui** o backend `terabox` (`rclone help backends` não lista `terabox`).
- Suporte em PR [rclone#8508](https://github.com/rclone/rclone/pull/8508) e forks (ex.: [rclone-extra-fork](https://github.com/iam-eo/rclone-extra-fork/releases)) — autenticação por **cookie de sessão** (`ndus`), **não OAuth**.
- No RDrive (CTk): **Adicionar unidade → TeraBox (experimental)** → **Ligar conta TeraBox** — o assistente mostra o passo a passo, a extensão obrigatória e notas de privacidade antes de iniciar (detalhes na UI; resumo abaixo):
  1. Browser isolado `%LOCALAPPDATA%\RDrive\chrome-rdrive-isolated-profile` — **Microsoft Edge exclusivo** (sideload `--load-extension`); se em falta, o `Iniciar.bat` e o fluxo TeraBox tentam instalar via winget (`Microsoft.Edge`). Extensão [Get cookies.txt LOCALLY](https://github.com/kairi003/Get-cookies.txt-LOCALLY) (`tools/get-cookies-txt-locally/`, bootstrap `scripts\bootstrap\bootstrap_cookies_extension.ps1`) — **obrigatória**; sem ela o fluxo bloqueia.
  2. **Login manual** no Edge do RDrive em `terabox.com/portuguese/login` (ou `/login`; evite `/passport/login` — devolve JSON de API, sem formulário). Use email/telefone e senha no formulário à **direita**. **Não use «Entrar com Google» nem Facebook** neste browser — o Google recusa OAuth em perfis isolados («navegador não seguro» / `signin/rejected`); não é corrigível só com flags do RDrive.
  3. O agente deteta sessão (`ndus`), exporta `cookies.txt` para **TEMP** e apaga ficheiro + perfil após importar.
  4. **Testar ligação** → **Ligar e guardar**
- **Conta só Google:** no assistente, «Conta só Google…» ou «Edge normal…» — login no Edge/Chrome diário, exportar `cookies.txt`, **Importar .txt** no RDrive. O fluxo automático no Edge isolado **não** suporta Google OAuth.
- **OAuth** (Drive, OneDrive, …): **Configuração automática** usa o **mesmo Edge isolado**; perfil limpo após autorizar (`docs/RDRIVE-ISOLATED-BROWSER.md`).
- Opções avançadas: importar `.txt`, abrir Edge sem agente, captura legado PyQt (sem extensões).
- `playwright` em `requirements.txt`; `Iniciar.bat` verifica Edge + Playwright na primeira vez (ou `RDRIVE_FORCE_PLAYWRIGHT_INSTALL=1`).
- **Importante:** o site TeraBox **bloqueia F12** — não copie cookies manualmente no site.
- Atalho manual: `scripts\launchers\Abrir-Edge-TeraBox.bat` (ou `Abrir-Chrome-TeraBox.bat` — redireciona)
- **Testar conexão** (após configurar o remote `terabox_pessoal` ou o nome que você escolheu):

```powershell
rclone lsd terabox_pessoal: --timeout 2m
```

- Se falhar com SSL/timeout: o TeraBox é instável — aguarde e tente de novo; renove o cookie se a sessão expirou.
- Credenciais ficam no arquivo de config do rclone (e unidades no cofre RDrive); senhas/cookies **não** são gravados em `logs/`.

#### Instalar rclone com TeraBox (Windows)

O **rclone oficial** (winget, chocolatey, site rclone.org) **não** inclui o backend `terabox`. Não há pacote winget/chocolatey fiável com TeraBox — instalação **manual** de um build comunitário.

1. **Verificar o rclone atual** (PowerShell):

```powershell
rclone version
rclone help backends | findstr /i terabox
```

Se `findstr` não imprimir nada, o backend TeraBox **não** está disponível.

2. **Obter um build não oficial** com backend `terabox`:
   - PR comunitário: [rclone#8508](https://github.com/rclone/rclone/pull/8508)
   - Forks com builds (exemplos): [iam-eo/rclone-extra-fork](https://github.com/iam-eo/rclone-extra-fork/releases), branch `terabox` em forks do PR
   - Baixe o ZIP **Windows amd64** do release ou artefato CI do fork escolhido

3. **Substituir o executável no PATH** (feche o RDrive antes):

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

5. **Reinicie o RDrive** e volte a **Adicionar unidade → TeraBox (experimental)**.

Script auxiliar (só diagnóstico e instruções — **não** baixa binários):

```powershell
.\scripts\terabox\install_rclone_terabox.ps1
```

Desative o assistente no passo 1 para o fluxo manual em 3 passos. OneDrive empresarial: use o modo manual e escolha «Empresarial» no passo 3.

### Mapear só uma pasta compartilhada (principalmente WebUI)

No assistente **Adicionar unidade → Detalhes** (WebUI), ative **«Mapear apenas pasta/link compartilhado»** e informe o link ou ID da pasta. O remote rclone continua sendo a conta OAuth completa; a montagem limita a raiz com flags/paths do rclone:

| Provedor | O que colar | Comportamento rclone |
|----------|-------------|----------------------|
| Google Drive | URL `…/folders/ID` ou só o ID | `--drive-root-folder-id` (+ `resource_key` se a URL tiver) |
| Dropbox | Nome da pasta em Compartilhados ou link `dropbox.com/sh/…` | `--dropbox-shared-folders` + `remote:NomeDaPasta` |
| OneDrive | URL com `?id=…` ou ID da pasta | `--onedrive-root-folder-id` |
| Outros | Subcaminho no remote | `remote:Subpasta/…` (sem flag extra) |

Campo **Subpasta** (opcional): caminho relativo dentro da raiz já limitada (ex.: `Projetos/2024`). Unidades antigas sem esses campos continuam montando a conta inteira.

### Combinar nuvens do mesmo provedor (rclone `union`)

Ligue duas ou mais contas do **mesmo provedor** (Google + Google, OneDrive + OneDrive, …) numa única unidade no Explorador, somando o espaço útil.

1. Clique em **Combinar** na barra superior.
2. **Passo 1 — Nuvem principal:** escolha a primeira nuvem na lista (já aparecem só as elegíveis: remotes simples, sem wrappers).
3. **Passo 2 — Nuvens compatíveis:** o RDrive lista apenas drives do **mesmo provedor canónico**. Selecione as outras contas que entram na união.
4. **Passo 3 — Nome e ponto de montagem:** dê um nome (ex.: *Google Drive Combinado*) e escolha uma letra livre (`A:`–`Z:` ou pasta `AA+`).
5. Clique em **Combinar nuvens**.

O backend cria uma entrada `[union_<nome>]` no `rclone.conf` (sanitizada) com defaults seguros — `create_policy=epmfs` (escreve no upstream existente com mais espaço livre) e `search_policy=ff` (primeiro encontrado, evita ambiguidade). Exemplo de config gerada (sanitizada):

```ini
[union_google_drive_combinado]
type = union
upstreams = gdrive_pessoal: gdrive_trabalho:
create_policy = epmfs
search_policy = ff
```

**Regras de segurança aplicadas:**

- Cross-provider é bloqueado (Google + OneDrive **não** é permitido — UX e validação no backend recusam o pedido).
- Drives que **já são uniões** (`drive_type = union_pool`) ou backends wrapper (`crypt`, `alias`, `cache`, `combine`, …) não entram na combinação — impede recursão.
- Um remote **não pode ser upstream de duas uniões** ao mesmo tempo (contagem dupla de espaço).
- Mínimo de **dois** remotes distintos por união; nomes e letras devem ser únicos.

**Limitações conhecidas:**

- TeraBox: a união entre contas TeraBox é experimental e segue as limitações do backend `terabox` (ver secção [TeraBox](#terabox-experimental)).
- Backends OAuth diferentes do mesmo provedor (ex.: dois OneDrive — pessoal + empresarial) podem combinar tecnicamente, mas o rclone usa o **mesmo cliente OAuth** para cada upstream — confirme se ambos têm token activo.
- Encriptação (`crypt`), cache, alias e outras combinações são **wrappers**: para usá-las dentro de uma união, configure o wrapper directamente no `rclone.conf` (este fluxo cobre só o caso simples).

### Pontos de montagem (Windows): A–Z e AA+

O Windows expõe apenas **26 letras de unidade** (`A:` … `Z:`) no Explorador. O rclone suporta dezenas de remotes; o RDrive aloca pontos assim:

| Faixa | Onde monta | No Explorador |
|-------|------------|---------------|
| `A:` … `Z:` | Letra WinFsp/rclone (como hoje) | Unidade em «Este PC» |
| `AA`, `AB`, … | Pasta `%LOCALAPPDATA%/RDrive/mounts/AA/` | Abrir via RDrive (coluna **Ponto** ou bandeja) — não é letra de disco |

Quando todas as letras livres estão ocupadas (sistema ou RDrive), a sugestão automática passa a `AA`, depois `AB`, etc. (sequência estilo Excel). Pastas AA+ são montagens WinFsp válidas, mas **não** aparecem como `AA:` no Explorador — use o atalho do RDrive ou navegue até `RDrive/mounts/`.

## Scripts e atalhos

Na raiz do repositório fica apenas **`Iniciar.bat`** (launcher principal com UAC/bootstrap). Os demais comandos Windows estão em **`scripts\launchers\`** (duplo clique ou atalho do Explorador apontando para o `.bat` desejado).

| Comando | O que faz |
|---------|-----------|
| `Iniciar.bat` | Bootstrap (Python, venv, pip, rclone, WinFsp) e arranque do app (`pythonw -m rdrive`) |
| `scripts\launchers\DevStatic-Live.bat` | Mesmo fluxo que `Iniciar.bat` com `RDRIVE_STATIC_LIVE=1` (recarga da WebUI ao guardar `Static/`) |
| `scripts\launchers\DevStatic-Browser.bat` | Preview HTTP da pasta `Static/` na porta 8765 (sem PyQt nem bridge) |
| `scripts\launchers\Abrir-Edge-TeraBox.bat` | Edge dedicado TeraBox (perfil isolado + extensão cookies) |
| `scripts\launchers\Abrir-Chrome-TeraBox.bat` | Redireciona para `Abrir-Edge-TeraBox.bat` (compat.) |
| `scripts\launchers\Capturar-Cookie-TeraBox.bat` | GUI para importar `cookies.txt` para o rclone TeraBox |
| `scripts\launchers\Configurar-TeraBox.bat` | Assistente terminal: colar cookie e criar remote |
| `scripts\launchers\Montar-TeraBox.bat` | Montagem manual TeraBox via `mount_terabox.ps1` |
| `scripts\maintenance\reset_vault.bat` | Repor cofre criptografado (confirmação `RESET`) |

Lógica pesada: orquestradores `.ps1` em subpastas de `scripts\` (ex.: `maintenance\log_launcher.ps1`, `terabox\launch_terabox_chrome.ps1`, `bootstrap\verify_webengine.ps1`). Ver `scripts\README.md`.

## Início rápido no Windows (`Iniciar.bat`)

### Release GitHub (zip)

1. Descarregue **`RDrive-*-windows.zip`** da [página Releases](https://github.com/MiguelSilvaPorto/RDrive/releases) (recomendado) ou o **Source code (zip)**.
2. Extraia **toda** a pasta (ex.: `RDrive-0.2.1-semi-stable\`).
3. Abra essa pasta e execute **`Iniciar.bat`** (duplo clique).
4. **Primeira vez:** aparece uma janela de consola durante 2–5 minutos (Python, `.venv`, `pip`, rclone). Não feche antes de terminar. Depois o RDrive abre em segundo plano (`pythonw`); procure o ícone na bandeja.
5. Se nada abrir: `logs\launcher.log` na pasta extraída; repita com `set RDRIVE_LAUNCHER_DEBUG=1` antes de `Iniciar.bat` ou `set RDRIVE_LAUNCHER_VISIBLE=1` para manter a consola visível.

Requisitos: Windows 10+, Internet na 1.ª execução; Python 3.11+ e rclone podem ser instalados automaticamente via `winget` (ver secção abaixo).

### Desenvolvimento / clone Git

No Windows, você pode iniciar tudo com um clique executando `Iniciar.bat` na raiz do projeto.

O que ele faz automaticamente:

- Detecta Python 3.
- Se o Python estiver ausente, tenta instalar com `winget` (escopo de usuário, sem prompt de admin pelo script).
- Detecta `rclone` no PATH.
- Se o `rclone` estiver ausente, tenta instalar com `winget` (`Rclone.Rclone`, escopo de usuário).
- Se necessário, tenta adicionar a pasta detectada do `rclone.exe` ao PATH do usuário automaticamente (sem admin).
- Detecta **WinFsp** (registro, `winfsp-x64.dll`, `where winfsp-x64` ou serviço `WinFsp.Launcher`).
- Se o WinFsp estiver ausente, tenta `winget install --id WinFsp.WinFsp -e` (não bloqueante — o app inicia e mostra um diálogo na montagem se ainda faltar).
- Cria `.venv` se necessário.
- Atualiza o `pip`.
- Instala `requirements.txt`.
- Inicia o app com `.venv\Scripts\pythonw.exe -m rdrive` (sem janela de console).
- Fecha o CMD do launcher quando o bootstrap termina; erros ficam em `logs\launcher.log` (defina `RDRIVE_LAUNCHER_DEBUG=1` para manter a janela aberta em caso de falha).

Observações:

- A primeira execução pode demorar mais porque prepara o ambiente.
- O primeiro remote é configurado no fluxo do aplicativo (`Adicionar` > **Conectar conta**), não no bootstrap do terminal.
- Se o `winget` não estiver disponível, o script mostra instruções guiadas para instalação manual.
- O script atualiza o PATH da sessão atual também, para continuar imediatamente após detectar o `rclone`.
- Se ainda não existir remote, o app abre normalmente e guia a configuração antes de conectar uma unidade.
- O script espera acesso à internet para instalação de pacotes.
- Toda a saída do launcher (incluindo erros) é acrescentada a `logs\launcher.log` na raiz do projeto via `scripts\maintenance\log_launcher.ps1`.

## Logs e solução de problemas

Os logs do aplicativo e do launcher ficam em **`logs/`** na raiz do repositório (estilo Git). O caminho é resolvido a partir de `RDRIVE_PROJECT_ROOT`, ou subindo a partir do pacote / cwd até encontrar `pyproject.toml` ou `Iniciar.bat`. Se nenhuma raiz de projeto for detectada (ex.: wheel isolado), os logs caem em `%LOCALAPPDATA%\RDrive\logs\`.

| Arquivo | Origem |
|---------|--------|
| `logs/rdrive.log` | App Python — exceções, subprocesso rclone, mount/connect, erros do watchdog |
| `logs/rdrive.log.1` … `.3` | Backups rotacionados (5 MB cada, 3 gerações) |
| `logs/launcher.log` | Bootstrap do `Iniciar.bat` (instalação Python/rclone/WinFsp, pip, erros de inicialização) |

**Ver logs no app:** Configurações → **Logs** → *Atualizar* (tail), *Abrir pasta de logs* ou *Abrir launcher.log*.

**Diagnóstico:** Configurações → **Testes** — verificação rápida do sistema (rclone, WinFsp, instância única, pasta de logs), teste de remote (`lsd` + `about`), teste opcional de velocidade de upload/download de 1 MB em `RDrive_speedtest/`, verificações de montagem por unidade e checklist somente leitura de recursos ON/OFF a partir das configurações atuais. Os resultados também são gravados em `rdrive.log` e `human.log`.

**Ver logs manualmente** (substitua pelo caminho do seu clone):

```text
<projeto>\logs\rdrive.log
<projeto>\logs\launcher.log
```

Os arquivos de log estão no `.gitignore` (`logs/*.log`); a pasta `logs/` é criada na primeira gravação.

Se o app falhar antes da GUI abrir, verifique `launcher.log` primeiro — ele captura erros de bootstrap do `.bat` e do PowerShell que nunca chegam ao logger Python.

## Montagem: disco local vs local de rede (Windows)

O RDrive usa **rclone mount** com **WinFsp**. No Windows, o rclone pode expor a unidade de duas formas:

| Modo | Flag rclone | Explorador |
|------|-------------|------------|
| **Disco local** (padrão, estilo RaiDrive) | *(sem `--network-mode`)* + `--volname` | **Este PC → Discos locais** (ex.: `GDrive Pessoal (G:)`) |
| **Local de rede** (legado) | `--network-mode` | **Locais de rede** (ex.: `gdrive_pessoal (\\server) (G:)`) |

- **Configurações → Geral →** *Montar como disco local (Este PC), estilo RaiDrive pago* — configuração `mount_as_local_drive` (padrão **ligado**).
- Desligue **somente** se precisar do comportamento antigo WNet / «unidade de rede».
- **RaiDrive (pago)** usa driver proprietário em kernel; o rclone não replica isso exatamente. A aproximação mais próxima é **disco fixo WinFsp** (padrão): sem `--network-mode`, `--volname` amigável a partir do rótulo da unidade.
- Depois de alterar essa configuração, **desconecte e reconecte** a unidade para um novo processo `rclone mount` com as flags corretas. Confira `logs/rdrive.log` por `[MOUNT] command:`.

### Entrada fantasma em «Locais de rede»

Se após **Desconectar** você ainda vir algo como `gdrive_pessoal (\\server) (A:)` com X vermelho em **Este PC → Locais de rede**:

| Sintoma | Causa habitual |
|--------|----------------|
| Aparece em **Locais de rede**, não em Discos locais | A unidade foi montada com `--network-mode` (configuração *Montar como disco local* desligada ou sessão antiga). |
| `net use A: /delete` diz que não encontra a conexão | O WinFsp já liberou a letra, mas o perfil WNet (`HKCU\Network\A`) ou o atalho UNC ficou órfão. |
| X vermelho no Explorador | Processo `rclone` terminou sem desmontar o FUSE / mapeamento persistente. |

**O que fazer (por ordem):**

1. **Configurações → Geral** — ative *Montar como disco local* e **salve** as configurações (o RDrive passa a gravar essa opção).
2. **Desconecte** a unidade no RDrive e **conecte de novo** — confirme em `logs/rdrive.log` que o comando **não** inclui `--network-mode`.
3. **Configurações → Testes → Limpar mapeamento da letra** — escolha a letra (ex.: `A:`) e execute a limpeza forçada (WNet, `net use`, registro, órfãos `rclone`).
4. **Manual (cmd como usuário):**
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

`rclone cmount` é um alias de `rclone mount` no Windows (mesmo backend WinFsp). Ajustes extras do WinFsp são possíveis via `rclone mount --fuse-flag` / `--option` se você experimentar fora do app.

### Performance de exclusões e escrita no Explorador

Apagar/escrever ficheiros no disco montado é, por baixo, **uma chamada HTTP por ficheiro** ao provedor (TeraBox, Drive, OneDrive, …). O RDrive afina o `rclone mount` para reduzir o overhead por operação:

**Sempre ligado (perfil «Equilibrado»):**

| Flag | Valor | Porquê |
|------|-------|--------|
| `--checkers` | `16` (rclone default: 8) | Mais paralelismo de verificações; permite ao WinFsp despachar IRPs concorrentes. |
| `--transfers` | `8` (default: 4) | Limpeza do cache VFS para a nuvem deixa de serializar em 4. |
| `--log-level` | `NOTICE` (era `INFO`) | Cada apagamento deixa de escrever ~3 linhas síncronas em `mount.log`. |
| `--vfs-fast-fingerprint` | — | Usa só `size+modtime` em vez de hash para identificar entradas no cache. |
| `--dir-cache-time` | `30m` (era `5m`) | Menos re-listagens completas depois de operações em lote. |
| `--poll-interval` | `1m` | Polling menos agressivo de mudanças externas. |
| `--attr-timeout` | `1s` | Cache de atributos do kernel acelera `stat` repetido. |

**Opt-in: «Exclusão rápida»** (Definições → Geral → *Exclusão rápida*)

Acrescenta flags mais agressivas — desligadas por padrão por reduzirem a verificação de integridade:

| Flag | Efeito |
|------|--------|
| `--no-checksum` | Não compara checksum em uploads (ficheiros recém-enviados não são re-verificados). |
| `--no-modtime` | Não preserva data de modificação em uploads (cosmético). |
| `--vfs-write-back 5s` | Agrupa writes pendentes antes de subir; menos chamadas, mais throughput. |
| `--dir-cache-time 1h` | Janela ainda maior para o cache de diretórios. |
| `--log-level ERROR` | Só erros em `mount.log` — zero I/O por operação rotineira. |

**Quanto melhora?** Em backends com pacer próprio (TeraBox, baidu), o teto vem do servidor — o ganho típico fica em ~1,5–2× (8 → 12–16 ficheiros/s). Em backends sem pacer agressivo (Google Drive, Dropbox, OneDrive), remover `--log-level INFO`, usar `--vfs-fast-fingerprint` e mais concorrência costuma render 3–10× nas exclusões em lote no Explorador.

**Atenção:** depois de alterar «Exclusão rápida» ou «Transferência acelerada», **desconecte e reconecte** a unidade. Confirme em `logs/rdrive.log` por `[MOUNT] command:` e `perf=balanced` / `fast-transfer` / `fast-delete`.

### Transferência acelerada (upload/download via Explorador)

**Opt-in:** Configurações → Geral → *Transferência acelerada*

O RDrive **não consegue** aumentar o tamanho de cada parte HTTP que o provedor impõe. Em **TeraBox** (backend baidu não oficial) e serviços similares, o upload via API costuma ser fatiado em **~4–5 MiB por pedido** — isso é limite do servidor, não do buffer local. O modo acelerado optimiza o que está sob controlo do cliente:

| Flag | Equilibrado | Transferência acelerada |
|------|-------------|-------------------------|
| `--buffer-size` | valor da unidade (ex. 256M) | `512M` |
| `--vfs-read-ahead` | valor da unidade (ex. 512M) | `1G` |
| `--vfs-read-chunk-size` | rclone default (128M) | `256M` |
| `--vfs-read-chunk-size-limit` | — | `2G` |
| `--transfers` | `8` | `16` |
| `--checkers` | `16` | `24` |
| Google Drive extra | — | `--drive-chunk-size 64M` |

**Por provedor:**

| Provedor | O que o RDrive pode fazer | O que não dá para contornar |
|----------|---------------------------|-----------------------------|
| **TeraBox / baidu** | Mais paralelismo local; cache VFS maior; menos overhead WinFsp | Chunk de upload ~4–5 MiB; pacer/rate-limit do servidor |
| **Google Drive** | `--drive-chunk-size 64M` + buffers maiores | Quota diária (~750 GB); throttling acima de ~8 transfers |
| **OneDrive / Dropbox** | Buffers e `--transfers` maiores | Limites de volume e throttling da conta |

**Quando usar `rclone copy` em vez do Explorador:** lotes enormes (centenas de GB), retomada fiável (`--resume`), ou quando precisa de `--transfers 32` sem a camada VFS/WinFsp. Exemplo TeraBox:

```bat
rclone copy "D:\Backup" terabox_pessoal:Backup --transfers 8 --checkers 16 -P
```

Combine «Transferência acelerada» com «Exclusão rápida» se quiser também write-back agregado e menos verificação de integridade em uploads recentes.

## <a id="solucao-problemas-winfsp"></a> Solução de problemas: WinFsp no Windows

O WinFsp é a camada de sistema de arquivos em modo usuário que permite ao rclone expor armazenamento em nuvem como letra de unidade. Sem ele, conectar/montar falha com o diálogo **WinFsp necessário**.

- **Automático:** execute `Iniciar.bat` — ele tenta `winget install --id WinFsp.WinFsp -e` quando o WinFsp não é detectado.
- **Manual:** https://winfsp.dev/rel/ ou `winget install --id WinFsp.WinFsp -e`
- **Verificar:** `where winfsp-x64` ou confira `C:\Program Files (x86)\WinFsp\bin\winfsp-x64.dll`
- O WinFsp instala em todo o sistema (pode pedir UAC). Se o winget falhar, instale manualmente e reinicie o RDrive.

## Solução de problemas: rclone no Windows

- Se o `rclone` não for reconhecido, instale manualmente:
  - `winget install --id Rclone.Rclone -e --scope user`
  - Downloads oficiais: https://rclone.org/downloads/
- Após a instalação, feche e reabra o terminal.
- Configure o primeiro remote no app (`Adicionar` > **Conectar conta**) ou manualmente no terminal:
  - `rclone config`
- Valide remotes no terminal:
  - `rclone listremotes`

### Cofre encriptado (experimental, desligado por padrão)

Por padrão o RDrive usa **modo simples**: `drives.json` e `settings.json` em texto legível no perfil local, **sem** pedir senha mestra na inicialização.

O **cofre encriptado** (`drives.enc` / `settings.enc`) é **opcional e experimental**. Ative em **Configurações → Segurança → Cofre encriptado (experimental)**:

| Modo | Comportamento |
|------|----------------|
| **Cofre DESLIGADO** (padrão) | Sem senha mestra; dados em JSON no perfil local |
| **Cofre LIGADO** (experimental) | Senha mestra na inicialização; dados criptografados localmente; recuperação por e-mail OTP |

Instalações novas começam com `vault_enabled: false` em `profile_meta.json`. Arquivos `.enc` antigos **não** ativam o cofre sozinhos: o RDrive usa `drives.json` / `settings.json` em modo simples até ativar explicitamente em **Configurações → Segurança** (com a senha mestra correta para reutilizar `.enc` existentes). Ao desativar, os dados criptografados são exportados para JSON e os `.enc` removidos — a ação exige confirmação.

**Aviso (modo simples):** qualquer pessoa com acesso à pasta de perfil (`%LOCALAPPDATA%\RDrive\…`) pode ler unidades e configurações. Use apenas em ambientes confiáveis.

Para ativar o cofre via variável de ambiente (legado / scripts):

```bash
set RDRIVE_MASTER_PASSWORD=your-strong-password
python -m rdrive
```

Quando o cofre está ativo, o RDrive ignora a variável se `vault_enabled` estiver OFF em `profile_meta.json`.

### Manter sessão iniciada (este PC)

Na tela **Desbloquear cofre**, você pode marcar **Manter sessão iniciada** para salvar a senha mestra criptografada neste computador (Windows DPAPI, vinculada ao usuário Windows atual). Na próxima inicialização o RDrive tenta restaurar a sessão sem pedir a senha.

- Os dados ficam em `%LOCALAPPDATA%\RDrive\session\<profile_id>\remembered_vault.blob` — nunca em texto simples.
- Cada conta (e-mail / `profile_id`) tem sua própria sessão memorizada.
- Em **Configurações → Segurança**, use **Encerrar sessão neste dispositivo** para apagar a sessão memorizada.
- **Segurança:** protege apenas contra leitura casual no disco; quem usar sua sessão Windows neste PC pode desbloquear o cofre. Não use em PCs compartilhados ou não confiáveis.

### Recuperação de senha (e-mail OTP)

No desbloqueio, use **Esqueci a senha** para verificar seu e-mail de recuperação com um código de 6 dígitos (10 minutos, máximo 3 tentativas).

Configure em **Configurações → Segurança**:

- **E-mail de recuperação** — obrigatório para redefinição; armazenado em `recovery_profile.json` (legível antes do desbloqueio).
- **SMTP avançado** (opcional) — envia códigos via `smtplib` SSL (porta 465). Se o SMTP não estiver configurado, o modo dev grava códigos em `logs/password_reset_otp.log` e os mostra em um diálogo.

#### Senha de app do Gmail (exemplo)

1. Ative a verificação em duas etapas na sua conta Google.
2. Abra [Senhas de app do Google](https://myaccount.google.com/apppasswords) e crie uma para «Mail».
3. No RDrive → Configurações → Segurança → SMTP avançado:
   - Host: `smtp.gmail.com`
   - Porta: `465`
   - Usuário: seu endereço Gmail
   - Senha: a senha de app de 16 caracteres (não a senha normal do Gmail)
   - De: o mesmo endereço Gmail

#### Limitação criptográfica (`.enc`)

Se `drives.enc` / `settings.enc` já existirem e você **esqueceu** a senha mestra, os dados criptografados **não** podem ser descriptografados sem a senha antiga. Após verificação por e-mail, o RDrive só pode:

- **Limpar o cofre** e criar um novo armazenamento criptografado vazio (todas as unidades/configurações salvas em `.enc` são perdidas), ou
- Alterar a senha normalmente nas configurações se você ainda souber a senha atual.

Estado JSON em texto (sem `.enc`) pode ser migrado para uma nova senha mestra após OTP sem perda de dados.

### Repor senha / cofre perdido

Se a senha mestra foi perdida (por exemplo após alterações manuais em `drives.enc`), os dados criptografados **não** podem ser lidos sem a senha antiga. Para voltar a usar o RDrive com cofre novo:

1. **Feche** o RDrive (bandeja e processo).
2. Na raiz do projeto, execute `scripts\maintenance\reset_vault.bat` (ou `powershell -File scripts\maintenance\reset_vault.ps1`), digite **`RESET`** quando pedido e confirme. Isso remove `drives.enc`, `settings.enc` e `recovery_token.json`, mas **mantém** `drives.json` / `settings.json` legados se existirem. Detalhes em `logs\reset_vault.log`. Para apagar também JSON e perfis multi-usuário: `reset_vault.ps1 -WipeAll`.
3. **Reinicie** com `Iniciar.bat`. Na primeira tela, defina o **e-mail de recuperação** e a **nova senha mestra** (fluxo de criação do cofre). JSON legado é migrado automaticamente na abertura.

Alternativa no app (com cofre já desbloqueado): **Configurações → Segurança → Repor cofre (perder dados criptografados)** — confirmação dupla com texto `RESET`, depois reinicie com `Iniciar.bat`.

## Conectar uma nuvem (com e sem configuração automática)

**Modo recomendado (CTk):** `Iniciar.bat` → **Adicionar unidade** → escolher provedor → **Assistente de ligação** (OAuth, formulário guiado ou TeraBox) → preencher nome/remote/letra (modo técnico colapsado) → **Guardar unidade** → montar na lista.

**WebUI legado:** três passos em `Static/` (**Escolha o provedor** → **Detalhes** → **Conexão**) com `RDRIVE_UI=web`. Dev: `DevStatic-Live.bat` (bridge + live reload) ou `DevStatic-Browser.bat` (preview sem montagem).

### Provedores: automático vs guiado vs terminal

Na grade **Adicionar**, provedores com distintivo **Auto** usam OAuth no navegador. Os com **formulário guiado** (passo 1) configuram o rclone sem terminal. O restante usa `rclone config` no terminal.

| OAuth automático | Guiado (formulário) | Manual (terminal) |
|------------------|---------------------------|-------------------|
| Google Drive (`drive`) | Amazon S3 (`s3`) | HDFS (`hdfs`) |
| OneDrive (`onedrive`) | WebDAV (`webdav`) | Azure Blob, Google Cloud Storage, … |
| Dropbox (`dropbox`) | SFTP (`sftp`) | Backends listados pelo seu `rclone` sem formulário |
| Box (`box`) | FTP (`ftp`) | |
| pCloud (`pcloud`) | HTTP (`http`, somente leitura) | |
| Mega (`mega`) | SMB / CIFS (`smb`) | |
| | TeraBox (`terabox`, experimental) | |

Nos provedores **Auto**, **Alternativa: configurar no terminal** continua disponível. Nos **guiados**, use **Modo técnico** se preferir o assistente rclone interativo.

### Fluxo com configuração automática

1. **Adicionar** (barra ou lista vazia).
2. **Passo 1 — Escolha o provedor:** selecione um serviço com distintivo **Auto** (ex.: Google Drive, OneDrive).
3. **Passo 2 — Detalhes:** defina um **nome da unidade** único, o **Remote (rclone)** sugerido (ex.: `gdrive_pessoal`) e a **letra de montagem** (ex.: `G:`). Opcional: montar ao abrir o RDrive / desmontar ao fechar.
4. **Passo 3 — Conexão:** clique **Configuração automática — conectar conta**. O navegador abre para login OAuth; o RDrive cria o remote no rclone e valida o acesso.
5. **Salvar unidade.** Se **Conectar unidade após salvar** estiver marcado, a montagem começa em seguida.
6. Na lista de unidades, use o interruptor **Montar unidade** (ou aguarde a inicialização automática se configurou montagem ao abrir).

Validação opcional no terminal: `rclone about gdrive_pessoal:` ou `rclone lsd gdrive_pessoal:`.

### Fluxo sem configuração automática (guiado ou terminal)

Use este fluxo para S3, WebDAV, SFTP, FTP, HTTP, SMB e quando o OAuth automático não estiver disponível ou falhar.

**Pré-requisitos**

- **`rclone` no PATH** — confirme com `rclone version` (o `Iniciar.bat` tenta instalar via `winget` se faltar).
- **Cofre desbloqueado** — o RDrive precisa de sessão ativa para salvar unidades e montar.

**Passos (formulário guiado)**

1. **Adicionar** → escolha o provedor (ex.: SFTP, FTP, SMB).
2. **Passo 1:** preencha host/URL/credenciais → **Testar conexão** (cria remote temporário e executa `rclone lsd`).
3. **Conectar e salvar** — cria o remote definitivo, valida e grava a unidade (com assistente automático ativo, também sugere nome e letra).
4. Na lista, ligue **Montar unidade**.

**Passos (somente terminal)**

1. **Adicionar** → provedor sem formulário (ex.: HDFS) ou **Modo técnico** em um provedor guiado.
2. **Configurar manualmente (terminal)** — `rclone config` com documentação do backend no navegador.
3. Confirme com `rclone listremotes` e `rclone lsd nome_remote:`.
4. Volte ao passo **Detalhes**, preencha **Remote (rclone)** e **Salvar unidade**.

### OneDrive empresarial

- **Configuração automática:** o fluxo OAuth cobre contas **pessoais** e muitos cenários **empresariais** (Microsoft 365). Se o rclone pedir tipo de drive durante a criação automática, o padrão interno é OneDrive pessoal (`onedrive`).
- **Manual recomendado** para **SharePoint**, bibliotecas específicas ou quando precisar escolher explicitamente **OneDrive personal** vs **OneDrive for Business** no assistente `rclone config` (pergunta `drive_type` / `type`).
- Remote de exemplo: `onedrive_trabalho` — depois copie esse nome para o campo **Remote (rclone)** no passo Detalhes.

### Problemas comuns

| Problema | O que fazer |
|----------|-------------|
| **App muito pesado / arranque lento / interface engasga** | O **Modo leve** está activo por omissão (Configurações → Geral → *Modo leve*). Se vem de uma instalação antiga, force via variável de ambiente `RDRIVE_LITE=1` antes de `Iniciar.bat`. Pausa o watchdog quando minimizado, desliga animação da borda, atrasa varreduras de integridade no arranque (4–5s) e agrupa snapshots da WebUI. Para feedback em tempo real durante desenvolvimento, defina `RDRIVE_LITE=0` ou desligue o toggle. |
| Montagem falha com **WinFsp necessário** | Instale WinFsp (`Iniciar.bat` tenta via `winget`, ou seção [Solução de problemas: WinFsp](#solucao-problemas-winfsp) abaixo). |
| **Este nome já está em uso** | Escolha outro **nome da unidade** — nomes são únicos no cofre. |
| **A letra X: já está em uso** | Outra unidade RDrive, `net use` ou processo `rclone` ocupa a letra; escolha outra ou use Configurações → **Testes** → *Limpar mapeamento da letra*. |
| OAuth / remote inválido | Consulte `logs/rdrive.log` (comandos rclone, erros de mount). Configurações → **Logs** → *Atualizar* ou **Testes** para diagnóstico rápido. |
| Assistente de terminal não abre | Só funciona com o RDrive em execução via `Iniciar.bat` / `scripts\launchers\DevStatic-Live.bat` (não no preview `scripts\launchers\DevStatic-Browser.bat`). |
| Vários diálogos «Reiniciar o RDrive?» ao editar `.bat` | Com `DevStatic-Live.bat` o watchdog ignora `scripts\launchers\`; noutros modos desactive **Reiniciar ao alterar código** ou **Modo compatível IDE** em Definições → Risco → Watchdog. |
| Cookies TeraBox: extensão não instala no arranque | Por omissão (Modo leve) o `Iniciar.bat` salta `bootstrap_cookies_extension.ps1`; a extensão é instalada quando abrir o browser dedicado em Configurações → TeraBox. Para forçar install eager, defina `RDRIVE_BOOTSTRAP_COOKIES_EAGER=1` antes do launcher. |
| TeraBox: «Edge não encontrado» / sideload falha | O sideload prefere **Microsoft Edge**. O `Iniciar.bat` tenta `winget install --id Microsoft.Edge -e --scope user` (não bloqueia o arranque). Se falhar: [microsoft.com/edge](https://www.microsoft.com/edge) ou repita «Ligar conta TeraBox» (tenta instalar de novo). |

Matriz técnica de backends e limitações: `ARCHITECTURE.md` §10.

## Roadmap (paridade RaiDrive — não implementado)

Funcionalidades identificadas na comparação com o RaiDrive, planejadas para iterações futuras (não incluídas nesta sessão):

- **Assistente SharePoint completo** — wizard WebUI para bibliotecas/document libraries com escolha de site e drive ID.
- **Bloqueio de arquivos (file lock)** — exclusão cooperativa durante edição em unidades montadas.
- **Criptografia de cache VFS** — cache local criptografado por unidade ou global.
- **Seletor de árvore de pastas** — seletor visual de subpastas remotas ao criar/editar unidade (em vez de texto livre em `root_path`).

## Observações

- Foco principal em **Windows**; Linux com FUSE3 é suportado em parte (sem bandeja WinFsp).
- Versão em `pyproject.toml` (ex.: `0.1.0`); releases GitHub usam tags de canal, por exemplo `v0.2.0-semi-stable` (pré-release) ou `v0.2.0-unstable`; só tags estáveis sem sufixo activam a atualização automática.
- **Reserva de cota** (`enable_preallocation`, predef. ligado): Definições → Geral.
- Recursos experimentais (stripe, union avançado, watchdog de desenvolvimento) em **Por sua conta e risco**.
- Testes automatizados: `pytest tests/` — ver `tests/README.md` (não confundir com Definições → Testes na app).

## Git e contribuição

Este projeto segue um fluxo Git documentado em `docs/GIT-CURSOR.md` (commits, branches, o que não versionar). O repositório público está em [github.com/MiguelSilvaPorto/RDrive](https://github.com/MiguelSilvaPorto/RDrive).

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
