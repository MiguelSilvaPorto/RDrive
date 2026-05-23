# RDrive

Repositório público: [github.com/MiguelSilvaPorto/RDrive](https://github.com/MiguelSilvaPorto/RDrive)

O RDrive é um aplicativo desktop inspirado no RaiDrive, construído sobre o [rclone](https://rclone.org/).
Ele monta armazenamento em nuvem como unidade local, com fluxo de trabalho orientado à interface gráfica.

## Status atual

Este repositório contém atualmente um bootstrap de implementação:

- Scaffold do aplicativo desktop em PyQt6
- Janela principal com placeholder da lista de unidades
- Diálogo de configurações com:
  - Geral (incl. reserva de cota / pré-alocação)
  - Segurança
  - Logs
  - **Testes** (diagnóstico: verificações do sistema, conexão remota, teste de velocidade, status de montagem)
  - Privacidade
  - Avançado
  - Armazenamento local
  - «Por sua conta e risco» (faixa experimental, union, watchdog de desenvolvimento)
- Esqueletos de serviços principais para:
  - Execução de comandos rclone
  - Monitoramento de cota
  - Ledger de reservas
  - Análise de limpeza residual
  - Módulos de planejamento/manifesto/verificação de montagem em faixas (stripe)

## Ícone do aplicativo

O ícone da janela e da barra de tarefas do RDrive é o botão metálico 3D com marca de sincronização em nuvem ciano, empacotado em `src/rdrive/assets/branding/`:

| Arquivo | Finalidade |
|---------|------------|
| `rdrive_icon_source.png` | Recorte mestre (256×256, fundo transparente) |
| `rdrive_icon_{16,24,32,48,64,128,256}.png` | PNGs em vários tamanhos para Qt |
| `rdrive.ico` | Ícone Windows multi-tamanho (uso externo opcional) |

O código em tempo de execução carrega ícones via `importlib.resources` (`rdrive.ui.foundation.app_icon`):

- `QApplication.setWindowIcon` em `app.py` (barra de tarefas / Alt+Tab)
- `MainWindow` e todas as janelas `InfiniteBorderDialog` (`setWindowIcon`)
- Pixmap 16×16 na barra de título personalizada (`CustomTitleBar`)
- **Bandeja do sistema** (`QSystemTrayIcon` em `rdrive.ui.system_tray`, conectado em `app.py` após `MainWindow.show()`):
  - Usa `tray_icon()` — no Windows prefere `rdrive.ico` ou `rdrive_icon_16.png` / `rdrive_icon_32.png` (a área de notificação usa tamanhos diferentes do ícone da barra de tarefas)
  - Tooltip com status ao vivo; menu de contexto **Abrir**, **Montar todas**, **Desmontar todas**, submenu **Abrir unidade** (letras montadas), **Estado**, **Sair**; clique esquerdo/duplo abre a janela
  - Criado quando o loop de eventos do app está em execução (incluindo lançamento fantasma `pythonw` / `Iniciar.bat`)
  - Se o SO não tiver bandeja (ex.: alguns ambientes Linux sem status notifier), um aviso é gravado em `human.log`

Para regenerar os assets a partir de uma nova imagem fonte (requer **Pillow** no venv, não é dependência de runtime):

```bash
.venv\Scripts\python.exe scripts\build_app_icons.py [caminho\para\imagem.png]
```

Fonte padrão: `%USERPROFILE%\Downloads\Gemini_Generated_Image_6knqxo6knqxo6knq.png`. O `rembg` opcional melhora a remoção de fundo; caso contrário, o script remove o fundo cinza plano.

## Documentação do projeto

- Arquitetura: `ARCHITECTURE.md`
- Referência de UI: `docs/ui-reference.md`

## Requisitos

- Python 3.11+
- **PyQt6-WebEngine** (incluído em `requirements.txt`) — motor Chromium embebido para a WebUI (`Static/`) e login TeraBox integrado
- Rclone instalado e disponível no PATH
- **WinFsp** (Windows) — necessário para `rclone mount`; detectado/instalado automaticamente pelo `Iniciar.bat` via `winget` quando possível
- FUSE3 (Linux) para montagens

### PyQt6-WebEngine (Windows)

A interface web e o navegador TeraBox integrado dependem de `PyQt6-WebEngine`. O `Iniciar.bat` instala via `pip install -r requirements.txt` e executa uma verificação rápida.

**Instalação manual / reparo:**

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

**Diagnóstico:** import OK mas página em branco — execute `verify_webengine.ps1`. Se a WebUI principal (`Static/`) carregar mas o TeraBox integrado ficar branco, o WebEngine está instalado; use «Abrir no browser do sistema» ou limpe o cache em `%APPDATA%\RDrive\terabox-browser\cache`.

## Executar

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m rdrive
```

### WebUI (`Static/`)

Por padrão, o aplicativo carrega a interface HTML/CSS/JS de **`Static/`** na raiz do projeto (definido automaticamente pelo `Iniciar.bat` via `RDRIVE_STATIC_DIR`).

| Variável | Padrão | Finalidade |
|----------|--------|------------|
| `RDRIVE_WEBUI` | `1` | `0` / `false` força a lista nativa legada em PyQt |
| `RDRIVE_STATIC_DIR` | `<projeto>/Static` | Pasta que contém `index.html` |
| `RDRIVE_STATIC_LIVE` | desligado | `1` serve `Static/` no lugar com recarga automática (~0,4 s) |
| `RDRIVE_PROJECT_ROOT` | definido pelo `Iniciar.bat` | Usado para localizar `Static/` quando o cwd difere |

**Desenvolver a UI:** `DevStatic-Live.bat` (PyQt + QWebChannel + live reload) ou `DevStatic-Browser.bat` (preview só no navegador na porta 8765). SVGs de provedores: `python scripts/sync_static_providers.py` → `Static/providers/`.

### Agente de configuração (WebUI)

Em **Adicionar unidade**, o cartão **Assistente automático** (ativo por padrão) executa o `CloudSetupAgent` (`src/rdrive/core/cloud_setup_agent.py`). A grade de provedores carrega o modo e os campos via `listProviders` (`remote_setup.py`).

#### Matriz de modos

| Modo | Provedores (exemplos) | O que você faz |
|------|------------------------|----------------|
| **OAuth automático** | Google Drive, OneDrive, Dropbox, Box, pCloud, Mega | «Configuração automática» → login no navegador → remote criado e unidade salva |
| **Guiado (formulário)** | S3, WebDAV, SFTP, FTP, HTTP, SMB/CIFS, TeraBox (experimental) | Preenche credenciais no passo 1 → **Testar conexão** (opcional) → **Conectar e salvar** |
| **Manual (terminal)** | HDFS, Azure Blob, GCS, backends raros sem formulário | «Modo técnico» ou assistente rclone (`rclone config`) |

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

- O **rclone oficial** (ex.: v1.74) **não inclui** o backend `terabox` (`rclone help backends` não lista terabox).
- Suporte em PR comunitário [rclone#8508](https://github.com/rclone/rclone/pull/8508) e forks (ex.: [rclone-extra](https://github.com/iam-eo/rclone-extra-fork)) — autenticação por **cookie de sessão** (cabeçalho completo ou valor `ndus=…`), **não é OAuth**.
- No RDrive: **Adicionar unidade → TeraBox (experimental)** — o utilizador **só faz login na janela RDrive**; o cookie é capturado automaticamente:
  1. Ao escolher TeraBox abre o **navegador integrado** (sessão guardada entre aberturas).
  2. Login em `https://www.terabox.com/login` → **Meus ficheiros** (URL com `/main`) → captura automática do cookie (`ndus=`).
  3. **Testar ligação** (opcional) → **Ligar e guardar**
- **Importante:** o site TeraBox **bloqueia ferramentas de desenvolvedor (F12)** — não tente copiar cookies manualmente no terabox.com.
- Alternativa: «Abrir no browser do sistema», login, volte ao integrado (perfil persistente) ou cole cookie exportado de extensão noutro browser (ver **Ajuda avançada** na UI).
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
   - Baixe o ZIP **Windows amd64** do release ou artefacto CI do fork escolhido

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

Script auxiliar (só diagnóstico e instruções — **não** descarrega binários):

```powershell
.\scripts\install_rclone_terabox.ps1
```

Desative o assistente no passo 1 para o fluxo manual em 3 passos (inalterado). OneDrive empresarial: use o modo manual e escolha «Empresarial» no passo 3.

### Mapear só uma pasta compartilhada (WebUI)

No assistente **Adicionar unidade → Detalhes**, ative **«Mapear apenas pasta/link compartilhado»** e informe o link ou ID da pasta. O remote rclone continua sendo a conta OAuth completa; a montagem limita a raiz com flags/paths do rclone:

| Provedor | O que colar | Comportamento rclone |
|----------|-------------|----------------------|
| Google Drive | URL `…/folders/ID` ou só o ID | `--drive-root-folder-id` (+ `resource_key` se a URL tiver) |
| Dropbox | Nome da pasta em Compartilhados ou link `dropbox.com/sh/…` | `--dropbox-shared-folders` + `remote:NomeDaPasta` |
| OneDrive | URL com `?id=…` ou ID da pasta | `--onedrive-root-folder-id` |
| Outros | Subcaminho no remote | `remote:Subpasta/…` (sem flag extra) |

Campo **Subpasta** (opcional): caminho relativo dentro da raiz já limitada (ex.: `Projetos/2024`). Unidades antigas sem esses campos continuam montando a conta inteira.

### Pontos de montagem (Windows): A–Z e AA+

O Windows expõe apenas **26 letras de unidade** (`A:` … `Z:`) no Explorador. O rclone suporta dezenas de remotes; o RDrive aloca pontos assim:

| Faixa | Onde monta | No Explorador |
|-------|------------|---------------|
| `A:` … `Z:` | Letra WinFsp/rclone (como hoje) | Unidade em «Este PC» |
| `AA`, `AB`, … | Pasta `%LOCALAPPDATA%/RDrive/mounts/AA/` | Abrir via RDrive (coluna **Ponto** ou bandeja) — não é letra de disco |

Quando todas as letras livres estão ocupadas (sistema ou RDrive), a sugestão automática passa a `AA`, depois `AB`, etc. (sequência estilo Excel). Pastas AA+ são montagens WinFsp válidas, mas **não** aparecem como `AA:` no Explorador — use o atalho do RDrive ou navegue até `RDrive/mounts/`.

## Início rápido no Windows (`Iniciar.bat`)

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
- Toda a saída do launcher (incluindo erros) é acrescentada a `logs\launcher.log` na raiz do projeto via `scripts\log_launcher.ps1`.

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

Por padrão o RDrive usa **modo simples**: `drives.json` e `settings.json` em texto legível no perfil local, **sem** pedir senha mestra no arranque.

O **cofre encriptado** (`drives.enc` / `settings.enc`) é **opcional e experimental**. Active em **Configurações → Segurança → Cofre encriptado (experimental)**:

| Modo | Comportamento |
|------|----------------|
| **Cofre DESLIGADO** (padrão) | Sem senha mestra; dados em JSON no perfil local |
| **Cofre LIGADO** (experimental) | Senha mestra na inicialização; dados criptografados localmente; recuperação por e-mail OTP |

Instalações novas começam com `vault_enabled: false` em `profile_meta.json`. Ficheiros `.enc` antigos **não** activam o cofre sozinhos: o RDrive usa `drives.json` / `settings.json` em modo simples até activar explicitamente em **Configurações → Segurança** (com a senha mestra correcta para reutilizar `.enc` existentes). Ao desactivar, os dados criptografados são exportados para JSON e os `.enc` removidos — a acção exige confirmação.

**Aviso (modo simples):** qualquer pessoa com acesso à pasta de perfil (`%LOCALAPPDATA%\RDrive\…`) pode ler unidades e configurações. Use apenas em ambientes confiáveis.

Para ativar o cofre via variável de ambiente (legado / scripts):

```bash
set RDRIVE_MASTER_PASSWORD=your-strong-password
python -m rdrive
```

Quando o cofre está ativo, o RDrive ignora a variável se `vault_enabled` estiver OFF em `profile_meta.json`.

### Manter sessão iniciada (este PC)

Na tela **Desbloquear cofre**, você pode marcar **Manter sessão iniciada** para guardar a senha mestra criptografada neste computador (Windows DPAPI, ligada ao usuário Windows atual). Na próxima inicialização o RDrive tenta restaurar a sessão sem pedir a senha.

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
2. Na raiz do projeto, execute `scripts\reset_vault.bat` (ou `powershell -File scripts\reset_vault.ps1`), digite **`RESET`** quando pedido e confirme. Isso remove `drives.enc`, `settings.enc` e `recovery_token.json`, mas **mantém** `drives.json` / `settings.json` legados se existirem. Detalhes em `logs\reset_vault.log`. Para apagar também JSON e perfis multi-usuário: `reset_vault.ps1 -WipeAll`.
3. **Reinicie** com `Iniciar.bat`. Na primeira tela, defina o **e-mail de recuperação** e a **nova senha mestra** (fluxo de criação do cofre). JSON legado é migrado automaticamente na abertura.

Alternativa no app (com cofre já desbloqueado): **Configurações → Segurança → Repor cofre (perder dados criptografados)** — confirmação dupla com texto `RESET`, depois reinicie com `Iniciar.bat`.

## Conectar uma nuvem (com e sem configuração automática)

A WebUI em `Static/` guia a conexão em três passos (**Escolha o provedor** → **Detalhes** → **Conexão**). Use **`Iniciar.bat`** para o RDrive completo (PyQt + bridge + montagem real). Para desenvolver só a interface, **`DevStatic-Live.bat`** inicia o mesmo fluxo com recarga automática ao salvar arquivos em `Static/`; **`DevStatic-Browser.bat`** abre um preview no navegador (sem bridge — conexão/montagem não funcionam).

### Provedores: automático vs guiado vs terminal

Na grade **Adicionar**, provedores com distintivo **Auto** usam OAuth no navegador. Os com **formulário guiado** (passo 1) configuram o rclone sem terminal. O restante usa `rclone config` no terminal.

| OAuth automático | Guiado (formulário WebUI) | Manual (terminal) |
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
| Montagem falha com **WinFsp necessário** | Instale WinFsp (`Iniciar.bat` tenta via `winget`, ou seção [Solução de problemas: WinFsp](#solucao-problemas-winfsp) abaixo). |
| **Este nome já está em uso** | Escolha outro **nome da unidade** — nomes são únicos no cofre. |
| **A letra X: já está em uso** | Outra unidade RDrive, `net use` ou processo `rclone` ocupa a letra; escolha outra ou use Configurações → **Testes** → *Limpar mapeamento da letra*. |
| OAuth / remote inválido | Consulte `logs/rdrive.log` (comandos rclone, erros de mount). Configurações → **Logs** → *Atualizar* ou **Testes** para diagnóstico rápido. |
| Assistente de terminal não abre | Só funciona com o RDrive em execução via `Iniciar.bat` / `DevStatic-Live.bat` (não no preview `DevStatic-Browser.bat`). |

Matriz técnica de backends e limitações: `ARCHITECTURE.md` §10.

## Roadmap (paridade RaiDrive — não implementado)

Funcionalidades identificadas na comparação com o RaiDrive, planejadas para iterações futuras (não incluídas nesta sessão):

- **Assistente SharePoint completo** — wizard WebUI para bibliotecas/document libraries com escolha de site e drive ID.
- **Bloqueio de arquivos (file lock)** — exclusão cooperativa durante edição em unidades montadas.
- **Criptografia de cache VFS** — cache local criptografado por unidade ou global.
- **Seletor de árvore de pastas** — seletor visual de subpastas remotas ao criar/editar unidade (em vez de texto livre em `root_path`).

## Observações

- O aplicativo foi projetado para Windows e Linux.
- **Reserva de cota** (`enable_preallocation`, padrão ligado): Configurações → Geral → *Reservar espaço antes de gravar arquivos grandes*. Usa `ReservationLedger` + `QuotaMonitor` ao planejar divisões em faixas (stripe); eventos aparecem no feed do log humano.
- Recursos experimentais (divisão em faixas, pool union, watchdog de desenvolvimento) permanecem em **Por sua conta e risco** e podem exigir aceitação de risco.
- A primeira implementação foca em arquitetura e fluxos operacionais seguros.

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
