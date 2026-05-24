# Migração CustomTkinter — Estado actual (Maio 2026)

Documento de auditoria comparando a UI legacy `Static/` (HTML + JS via QWebChannel)
com a nova UI nativa `src/rdrive/ui/ctk/` (CustomTkinter + Tk). Mantemos as duas
em coexistência: `RDRIVE_UI=ctk` activa CTk, `RDRIVE_UI=web` mantém o stack
PyQt + WebEngine. **Static/ não foi removido**.

> Fonte canónica de paridade: `Static/index.html`, `Static/script.js`,
> `src/rdrive/ui/main_window.py`. Este documento usa esses ficheiros como
> referência ponto-a-ponto.

## Filosofia da migração CTk

* Sem QWebChannel — a UI fala directamente com `CtkAppContext`
  (`services.py`), que encapsula `ConfigStore`, `MountManager`, `RcloneCli`,
  `CloudSetupAgent`, etc.
* Sem `MainWindow` PyQt — bootstrap `rdrive.ui.ctk.bootstrap.run_ctk_main`
  cuida do single-instance, vault unlock e DPI.
* Operações pesadas (mount/unmount, OAuth, system check) correm em threads;
  callbacks usam `widget.after(0, …)` para regressar à thread Tk.
* Estilo escuro premium em pt-BR (tokens em `theme.py`); modais nativos
  Tk (`messagebox`, `simpledialog`) reutilizados onde a UX se mantém boa.

### Assistente de ligação (Adicionar unidade)

O painel direito prioriza o **Assistente de ligação** (`CloudAssistantPanel`):
dica PT por provedor, «Configuração automática» (OAuth via `CloudSetupAgent` em
thread com `get_cloud_setup_state` / `cancel_cloud_setup`), formulário guiado
para backends S3/WebDAV/SFTP/etc., atalhos TeraBox e «Assistente manual».
O remote é criado no rclone sem gravar a unidade; após sucesso o formulário
técnico é pré-preenchido e o toast pede «Guardar unidade». O modo técnico
(nome, remote, letra) fica colapsado por omissão.

## Matriz de paridade

Legenda: ✅ pronto · ⚠️ parcial · ❌ ausente · ➖ não aplicável.

### Lista de unidades (Home)

| Funcionalidade Static                  | CTk |
| -------------------------------------- | --- |
| Cartão por unidade                     | ✅  |
| Conectar/desconectar (`toggleConnection`) | ✅ |
| Renomear inline (`rename-drive`)       | ✅ (`simpledialog`) |
| Alterar letra (`change-drive-letter`)  | ✅ (`simpledialog`) |
| Auto-início                            | ✅  |
| Abrir letra no Explorador              | ✅  |
| Excluir unidade                        | ✅  |
| Force disconnect (`forceDisconnect`)   | ✅  |
| Editar unidade (`edit-drive` overlay)  | ✅ (CTkToplevel novo) |
| Pílula de integridade                  | ⚠️ (estado simples já mostra) |
| Drives demo (`add-demo-drive`)         | ❌  |

### Toolbar/Home

| Recurso Static                         | CTk |
| -------------------------------------- | --- |
| Adicionar unidade                      | ✅  |
| Combinar nuvens                        | ✅  |
| Definições                             | ✅  |
| Painel de actividade                   | ✅  |
| Toggle tema                            | ➖ (apenas dark) |
| Ping bridge                            | ➖  |
| Transfer jobs (`open-transfer-jobs`)   | ❌  |
| Stripe splitter (`open-stripe-splitter`) | ❌ |

### Adicionar unidade

| Static                                 | CTk |
| -------------------------------------- | --- |
| Provider grid                          | ✅ (lista scroll) |
| Formulário base (label/remote/letra)   | ✅  |
| Sugestão automática de letra           | ✅ (botão «Sugerir») |
| Sugestão de remote                     | ✅  |
| Assistente de ligação (`CloudSetupAgent`) | ✅ (`cloud_assistant_panel.py`: OAuth, guiado, progresso, cancelar/retry) |
| OAuth automático (browser)             | ✅ («Configuração automática») |
| Manual setup (`launch_setup_flow`)     | ✅ («Assistente manual (terminal)») |
| Atalhos TeraBox (Chrome/cookies/captura) | ✅ (dentro do painel assistente) |
| Embedded TeraBox browser (Qt WebEngine) | ⚠️ (captura via `capture_terabox_cookie_via_browser`, sem WebEngine Qt) |
| Modo técnico (formulário colapsável)   | ✅  |
| Guided setup (s3/webdav/ftp/sftp/smb)  | ✅ (campos de `guided_fields_for_backend`) |
| Badge OAuth/Experimental no card       | ⚠️ (dica PT no assistente) |

### Combinar nuvens

| Static                                 | CTk |
| -------------------------------------- | --- |
| 1. Escolher principal                  | ✅  |
| 2. Escolher peers                      | ✅  |
| 3. Confirmar nome/letra                | ✅  |
| `listCombinableDrives` / `createCombinedDrive` | ✅ (via `combine_drives.py`) |

### Definições

| Aba Static                             | CTk |
| -------------------------------------- | --- |
| Geral — modo leve, animação            | ✅  |
| Geral — Explorador, ícone custom       | ✅ (parcial — ícone custom é cosmético) |
| Geral — montar como local              | ✅  |
| Geral — apagar/transferir rápido       | ✅  |
| Geral — minimizar bandeja, confirmação fechar | ✅ |
| Geral — proxy HTTP                     | ✅  |
| Geral — pré-alocação                   | ✅  |
| Geral — limpeza automática             | ✅  |
| Segurança — toggle cofre/recovery email | ✅ (ler/gravar email) |
| Segurança — alterar senha mestra       | ❌ (continua na PyQt) |
| Segurança — repor cofre                | ❌  |
| Segurança — switch user                | ❌  |
| Segurança — SMTP avançado              | ✅ (campos persistem nas settings) |
| Risco — flags experimentais            | ✅  |
| Risco — retentativas (count/intervalo) | ✅  |
| Risco — watchdog (todos os toggles + intervalos) | ✅ |
| Risco — IDE compat / hot-reload idle / startup grace | ✅ |
| Risco — botão «Reiniciar RDrive»       | ✅  |
| Logs — feed limit                      | ✅  |
| Logs — log tail viewer (rdrive.log)    | ✅ (`Pre`-style read-only) |
| Logs — abrir pasta                     | ✅  |
| Testes — diag-system-check             | ✅ (rclone version + winfsp) |
| Testes — diag-remote-test              | ✅ (rclone lsd) |
| Testes — diag-speed-start              | ❌ (não migrado — não-crítico) |
| Testes — diag-mount-check              | ✅ (lista status reais) |
| Testes — diag-human-log                | ✅ (botão para Activity panel) |
| Testes — diag-force-cleanup-letter     | ❌ (não-crítico) |
| Testes — bateria benchmark nuvem       | ✅ (`benchmark_panel.py` + `cloud_benchmark.py`) |
| Testes — show_home_test_tools          | ✅ (toggle persistido) |
| Info — texto explicativo               | ✅  |

### Cofre

| Static                                 | CTk |
| -------------------------------------- | --- |
| Unlock no arranque                     | ✅ (`bootstrap._prompt_vault_password`) |
| Memorizar (DPAPI)                      | ✅  |
| Esqueci a senha (`forgotVaultPassword`) | ❌ (PyQt mantém) |
| Switch user                            | ❌  |
| Setup novo cofre interactivo           | ❌  |

### Bandeja do sistema

| Recurso                                | CTk |
| -------------------------------------- | --- |
| Ícone na bandeja (mostrar/ocultar)     | ✅ (via `pystray` opcional) |
| Acção «Abrir»                          | ✅  |
| Montar/desmontar todas                 | ✅  |
| Submenu «Abrir unidade»                | ✅  |
| Sair                                   | ✅  |
| Fallback gracioso quando `pystray` falta | ✅ (log + sem crash) |

### Modais

| Static                                 | CTk |
| -------------------------------------- | --- |
| `vault-unlock-overlay`                 | ✅ (CTkToplevel) |
| `edit-drive` (label/remote/letra/cache) | ✅ (CTkToplevel novo) |
| `rename-drive`                         | ✅ (`simpledialog`) |
| `change-drive-letter`                  | ✅ (`simpledialog`) |
| `confirm-dialog`                       | ✅ (`messagebox.askyesno`) |

### Activity panel / Diagnostics

| Static                                 | CTk |
| -------------------------------------- | --- |
| Painel de actividade lateral           | ✅ (frame integrado) |
| Tail human.log                         | ✅  |
| Limit configurável                     | ✅  |
| Diagnostics speed test                 | ❌  |
| Diagnostics mount check                | ✅  |
| Diagnostics system check               | ✅  |

## Resumo de paridade

* Itens **prontos**: 49
* Itens **parciais**: 5
* Itens **ausentes**: 9 (maioritariamente flows ainda servidos pelo painel
  PyQt — speed test, stripe splitter, transfer jobs, switch user, etc.).

**Estimativa de paridade global ≈ 85 %** para o caminho diário (criar drive,
ligar, montar, listar, editar, settings core). Restos são fluxos
secundários ou específicos ao stack Qt (embedded WebEngine, transfer jobs).

## O que falta para 100 %

1. Speed test em CTk (precisa progresso animado + cancel via thread).
2. Painel de transfer jobs (lista de cópias rclone em curso).
3. Stripe splitter (UI experimental).
4. Switch user + setup de cofre dentro da app (sem reiniciar).
5. Embedded TeraBox browser (depende de Qt WebEngine — a alternativa CTk
   delega ao Chrome do utilizador).
6. Visualização de pílula de integridade detalhada (estados internos
   `vfs_cache_status`).
7. Drag-drop de cookies.txt no painel TeraBox.
8. Mock/dev modes (`add-demo-drive`).
9. Force-cleanup-letter (`net use /delete` + WNet) com selector dedicado.

## Benchmark de nuvem (Definições → Testes)

A aba **Testes** na UI CTk executa uma bateria completa após ligar uma nuvem
(montada ou só com remote). O módulo `src/rdrive/core/diagnostics/cloud_benchmark.py`
gera ~100 MB localmente, envia para `RDriveBench/_rdrive_test_<timestamp>/` e
valida integridade (SHA256, chunks 100×1 MB, velocidades, paralelo, latências).

* **UI:** dropdown de unidade, «Executar bateria completa», botões por teste,
  barra de progresso, log e tabela resumo; «Cancelar» via `threading.Event`.
* **Backend:** `CtkAppContext.run_cloud_benchmark(drive_id, suite="full"|test_id)`.
* **Segurança:** nunca escreve fora do prefixo `RDriveBench/`; cleanup local e
  remoto no `finally`.
* **Testes:** `pytest tests/test_cloud_benchmark.py -q` (mock filesystem, sem cloud).

## Como testar a UI CTk

```powershell
$env:RDRIVE_UI = "ctk"
.\Iniciar.bat
```

Smoke tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ctk_smoke.py tests/test_cloud_benchmark.py -q
.\.venv\Scripts\python.exe -c "from rdrive.ui.ctk.bootstrap import run_ctk_main"
```

Ver `ARCHITECTURE.md` para o pano geral do RDrive (mount manager, vault,
watchdog) e `docs/ESTRUTURA.md` para o mapa de pastas.
