# Git e Source Control no Cursor (RDrive)

Este guia liga o projeto **RDrive** ao Git/GitHub e explica o fluxo na interface do Cursor (baseado em VS Code).

## Estado esperado no projeto

- Repositório local: pasta `.git` na raiz do projeto.
- `.gitignore` na raiz (segredos, `.venv`, `logs/`, builds, etc. não entram no Git).
- Identidade Git **local** neste repo: `user.name` = Miguel Silva, `user.email` = miguelsilvaporto1@gmail.com (sem `--global`).

- Remoto `origin` no GitHub (após criar o repositório e fazer o primeiro push).

## Painel Source Control no Cursor

1. Abra a pasta do projeto: **File → Open Folder** → `RDrive`.
2. Ícone de ramificação na barra lateral esquerda (**Source Control**) ou atalho `Ctrl+Shift+G`.
3. Se aparecer **Initialize Repository**, o Git ainda não estava ativo — neste projeto já foi feito `git init` localmente; você deve ver ficheiros em *Changes*.

### Commit manual (recomendado para o código completo)

1. Em *Changes*, clique **+** em cada ficheiro ou **Stage All Changes** quando estiver pronto.
2. Caixa de mensagem no topo: escreva um resumo (ex.: `feat: painel de ficheiros inicial`).
3. **Commit** (ícone de visto) ou `Ctrl+Enter`.
4. Menu **⋯** → **Push** (primeira vez pode pedir login GitHub).

### Pull / sincronizar

- **⋯** → **Pull**, ou ícone de sincronização na barra de estado.
- Resolva conflitos no editor se o Cursor os assinalar.

### Pedir ao Agent (Cursor)

Peça explicitamente, por exemplo:

- «Faz commit só de `.gitignore` e `docs/`»
- «Cria commit com mensagem X e não faças push»
- «Abre PR no GitHub» (requer `gh` instalado e autenticado)

**Regra do projeto:** o agente só deve fazer **commit** ou **push** quando você pedir (ver `.cursor/rules/git-workflow.mdc`).

## GitHub CLI (`gh`) — não instalado nesta máquina (verificar)

Se `gh` não estiver no PATH:

1. Instale: [GitHub CLI releases](https://github.com/cli/cli/releases) ou `winget install GitHub.cli`.
2. Autentique (terminal **interativo** — faça você no PowerShell):

```powershell
gh auth login
```

Escolha **GitHub.com** → **HTTPS** → login no browser ou **Paste an authentication token** (Settings → Developer settings → Personal access tokens).

3. Verifique:

```powershell
gh auth status
```

### Criar repositório remoto (quando `gh` funcionar)

Na pasta do projeto:

```powershell
cd "c:\Users\migue\Documents\projeto em desenvolvimento\Github\RDrive"
gh repo create RDrive --private --source=. --remote=origin --description "RDrive cloud file manager"
# ou público: omita --private ou use --public
```

Se o nome `RDrive` já existir na sua conta, use outro nome ou `usuario/RDrive`.

### Primeiro push (sem `gh repo create`)

1. Crie um repositório vazio em [github.com/new](https://github.com/new) (sem README se já tiver commits locais).
2. No projeto:

```powershell
git remote add origin https://github.com/SEU_USUARIO/RDrive.git
git branch -M main
git add .
git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>" -m "Initial commit: RDrive application"
git push -u origin main
```

**Antes do `git add .`:** confirme que `.env`, `rclone.conf` e `logs/` não aparecem em `git status` (devem estar ignorados).

## HTTPS vs SSH

- **HTTPS:** Cursor/Git pedem credenciais ou Git Credential Manager; token PAT se pedido.
- **SSH:** `git@github.com:usuario/RDrive.git` — exige chave SSH em [GitHub Settings → SSH keys](https://github.com/settings/keys).

## Comandos úteis (PowerShell)

```powershell
Set-Location "c:\Users\migue\Documents\projeto em desenvolvimento\Github\RDrive"
git status
git diff
git log --oneline -5
```

## O que falta versionar (após setup)

Após o commit inicial só de documentação/gitignore, faça um commit maior com o resto do código quando quiser: `src/`, `Static/`, `scripts/`, `tests/`, `requirements.txt`, etc. — tudo via Source Control ou `git add` seletivo.
