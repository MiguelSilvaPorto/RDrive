# Instalador Windows (RDriveSetup.exe)

Instalador gráfico em português (Brasil) para distribuir o RDrive sem clonar o repositório Git. Baseado em [Inno Setup 6](https://jrsoftware.org/isinfo.php).

## O que é instalado

| Conteúdo | Notas |
|----------|--------|
| `Iniciar.bat` | Launcher principal (bootstrap Python, venv, pip, rclone, WinFsp) |
| `src/`, `Static/`, `scripts/`, `docs/` | Aplicação e WebUI legada |
| `tools/rclone-extra/`, `tools/get-cookies-txt-locally/` | Apenas `NOTICE` e `.gitkeep` — binários na 1.ª execução |
| `logs/` | Pasta vazia (logs criados em runtime) |
| `requirements.txt`, `pyproject.toml` | Versão e dependências |

**Não incluído no pacote:** `.venv`, `tests/`, `.git`, logs antigos, segredos (`rclone.conf`, `.enc`, `cookies.txt`), caches de dev.

**Não incluído no desinstalar por omissão:** dados do utilizador em `%LOCALAPPDATA%\RDrive\` (cofre, montagens, definições). Remova manualmente se quiser apagar tudo.

## Modos de instalação

| Modo | Pasta predefinida | Admin (UAC) | Registo desinstalação |
|------|-------------------|-------------|------------------------|
| **Apenas utilizador atual** | `%LOCALAPPDATA%\Programs\RDrive` | Não | `HKCU\...\Uninstall\...` |
| **Todos os utilizadores** | `%ProgramFiles%\RDrive` (`{commonpf}`) | Sim (reinício elevado) | `HKLM\...\Uninstall\...` |

O assistente permite **alterar a pasta** em ambos os modos.

Dados de runtime (cofre, drives, etc.) continuam em **`%LOCALAPPDATA%\RDrive\`**, independentemente do modo — igual ao desenvolvimento.

## Atalhos

| Atalho | Alvo | Quando |
|--------|------|--------|
| Menu Iniciar → **RDrive** | `{app}\Iniciar.bat` | Sempre |
| Menu Iniciar → **Desinstalar RDrive** | `unins000.exe` | Sempre |
| Área de trabalho → **RDrive** | `{app}\Iniciar.bat` | Se marcar *Criar atalho na Área de trabalho* |

Ícone: `src\rdrive\assets\branding\rdrive.ico`.

Tarefa opcional: **Abrir o RDrive após concluir** — executa `Iniciar.bat` (pode demorar na 1.ª vez: venv + pip + Playwright).

## Primeira execução após instalar

1. Python 3.11+ no sistema (ou winget via `Iniciar.bat`).
2. Criação de `.venv` e `pip install -r requirements.txt`.
3. Verificação Playwright/Edge (`channel=msedge`), WebEngine, rclone/WinFsp conforme `Iniciar.bat`.

Não é necessário Python pré-instalado no PC alvo se o bootstrap winget funcionar; recomenda-se Python 3.11+ instalado para arranque mais fiável.

## Como construir o `.exe`

### Pré-requisitos

- Windows 10+
- [Inno Setup 6](https://jrsoftware.org/isdl.php) (comando `ISCC.exe`)

### Comando

Na raiz do repositório:

```powershell
.\scripts\build\build_installer.ps1
```

Saída: **`dist\RDriveSetup.exe`**.

Opções:

```powershell
# Só preparar dist\installer-staging\ (sem ISCC)
.\scripts\build\build_installer.ps1 -SkipCompile

# Caminho explícito do compilador
.\scripts\build\build_installer.ps1 -InnoSetupPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

Validação estática (sem compilar):

```powershell
.\scripts\build\validate_installer.ps1
```

### Compilação manual

Se o script não encontrar `ISCC.exe`:

```powershell
.\scripts\build\build_installer.ps1 -SkipCompile
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" `
  /DMyAppVersion=0.1.0 /DMyAppVersionInfo=0.1.0.0 `
  "installer\RDriveSetup.iss"
```

A versão é lida de `pyproject.toml` quando usa o script de build.

## Ficheiros do projeto

| Ficheiro | Função |
|----------|--------|
| `installer\RDriveSetup.iss` | Script Inno Setup (UI pt-BR, escopo, atalhos) |
| `installer\rdrive.ico` | Cópia do ícone (gerada no build a partir de `src\rdrive\assets\branding\`) |
| `scripts\build\build_installer.ps1` | Staging + invocação ISCC |
| `scripts\build\validate_installer.ps1` | Verificação mínima da estrutura |
| `dist\installer-staging\` | Árvore intermédia (gitignored) |
| `dist\RDriveSetup.exe` | Instalador final (gitignored) |

## Desinstalar

**Definições → Aplicações → Aplicações instaladas** (ou *Adicionar ou remover programas*) → **RDrive** → Desinstalar.

Remove a pasta de instalação (`{app}`), incluindo `.venv` se já existir. Não apaga `%LOCALAPPDATA%\RDrive\` automaticamente.

## Resolução de problemas

| Problema | Ação |
|----------|------|
| ISCC não encontrado | Instalar Inno Setup 6; usar `-InnoSetupPath` |
| `SetupIconFile` em falta | Executar `build_installer.ps1` (copia `rdrive.ico` para `installer\`) |
| Instalação “todos” não eleva | Executar `RDriveSetup.exe` como administrador ou escolher modo utilizador |
| App não abre após instalar | Ver `logs\launcher.log` na pasta de instalação; instalar Python manualmente |
