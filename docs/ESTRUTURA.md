# Estrutura do projeto RDrive

> Mapa canônico de pastas e ficheiros. Use este documento como referência rápida
> ao adicionar novos módulos, scripts ou docs — para manter a raiz limpa e cada
> arquivo no lugar certo. Alinha com `ARCHITECTURE.md` (visão técnica) e
> `DiretrizesGlobais/regras_globais.md` (pastas Git-style, raiz limpa,
> modularidade extrema).

## 1. Visão de topo

```
RDrive/
├── Iniciar.bat              # único launcher Windows (UAC, venv, rclone, pythonw)
├── README.md                # apresentação, instalação, fluxos de uso
├── ARCHITECTURE.md          # visão técnica de camadas/serviços (raiz por convenção)
├── pyproject.toml           # metadata Python + setuptools (package-dir = src)
├── requirements.txt         # deps runtime (PyQt6, PyQt6-WebEngine, …)
├── .gitignore               # artefactos locais, segredos, .venv, logs, tempo
├── Static/                  # WebUI HTML/CSS/JS (fonte canônica da UI)
├── src/rdrive/              # pacote Python único (entrypoint: python -m rdrive)
├── scripts/                 # automação .ps1 + .py utilitários
│   └── launchers/           # .bat especializados (TeraBox, DevStatic, …)
├── docs/                    # documentação (arquitetura UI, este ESTRUTURA, Git)
├── tests/                   # pytest (test_*.py)
├── tools/                   # binários externos (rclone-extra, extensão Chrome)
├── logs/                    # runtime (gitignored)
├── tempo/                   # backups manuais do utilizador (gitignored)
└── .venv/                   # ambiente virtual local (gitignored)
```

## 2. `Static/` — WebUI canônica

```
Static/
├── index.html               # SPA principal carregada por QWebEngineView
├── script.js                # bridge QWebChannel, estado, fluxos UI
├── css/
│   ├── base.css             # tokens (variáveis CSS), reset, tipografia
│   ├── components.css       # botões, modais, cartões, micro-interações
│   └── views.css            # layouts por tela (lista, adicionar, definições)
└── providers/               # SVGs de provedores (sincronizado via scripts/sync_static_providers.py)
```

Fonte da verdade dos SVGs: `src/rdrive/assets/providers/`.  
`scripts/sync_static_providers.py` espelha para `Static/providers/`.

## 3. `src/rdrive/` — pacote Python

```
src/rdrive/
├── __init__.py
├── __main__.py              # python -m rdrive → app.main()
├── app.py                   # bootstrap PyQt6, single-instance, tray
├── assets/
│   ├── branding/            # ícones rdrive_icon_*.png, rdrive.ico
│   └── providers/           # SVGs por categoria (cloud/, storage/, protocol/, local/, _fallback/)
├── models/
│   └── drive.py             # dataclass Drive + estados de montagem
├── core/                    # serviços por domínio (raiz só __init__.py)
│   ├── cleanup/             # análise de resíduos
│   ├── cloud/               # OAuth, remote_setup, terabox_setup, cloud_setup_agent
│   ├── diagnostics/         # testes do sistema (Configurações → Testes)
│   ├── logging/             # app_logger, human_logger, rotação
│   ├── mount/               # mount_manager, validação WinFsp/FUSE, letras
│   ├── paths/               # project_paths (resolve_project_root), data_paths
│   ├── profile/             # multi-usuário, e-mail, recovery
│   ├── rclone/              # CLI rclone (subprocess) + proxy
│   ├── runtime/             # single_instance, watchdog, restart, mutex
│   ├── stripe/              # planeamento/manifesto/verificação (faixas)
│   └── vault/               # cofre (cryptography), config_store, unlock
└── ui/
    ├── main_window.py       # janela principal (fallback nativo)
    ├── system_tray.py       # bandeja (QSystemTrayIcon)
    ├── unlock_vault.py      # tela de desbloqueio
    ├── chrome/              # window_chrome (frameless título personalizado)
    ├── dialogs/             # new_drive, password_reset, remote_setup, transfer_jobs, settings
    ├── foundation/          # app_icon (importlib.resources)
    ├── settings/            # abas legacy (settings_diagnostics_tab, settings_logs_tab)
    ├── terabox/             # terabox_browser (WebEngine), chrome_cookie_browser
    ├── web/                 # web_shell (QWebEngineView), app_service (QObject exposto)
    └── widgets/             # widgets nativos (fallback sem WebUI)
```

Regra: nada de scripts soltos em `src/rdrive/` — toda lógica desce para
`core/<domínio>/` ou `ui/<área>/`. O entrypoint público é `python -m rdrive`.

## 4. `scripts/` — automação

```
scripts/
├── log_launcher.ps1                    # tee do Iniciar.bat → logs/launcher.log
├── verify_webengine.ps1                # validação PyQt6-WebEngine
├── ensure_user_path.ps1                # PATH persistente do utilizador
├── install_rclone_terabox.ps1          # build PR rclone#8508 → tools/rclone-extra/
├── bootstrap_cookies_extension.{ps1,py}# baixa extensão Chrome cookies.txt
├── launch_terabox_chrome.ps1           # Chrome dedicado + --load-extension
├── mount_terabox.ps1                   # montagem TeraBox via rclone mount
├── configurar_terabox.ps1              # assistente terminal (cole cookie → remote)
├── cleanup_drive_letter.ps1            # libera letra ocupada
├── reset_vault.{ps1,bat}               # apaga drives.enc/settings.enc com confirmação
├── restart_rdrive.ps1                  # reinício assíncrono (novo processo antes do antigo cair)
├── build_app_icons.py                  # gera rdrive_icon_*.png a partir de imagem fonte
├── fetch_provider_icons.py             # baixa SVGs upstream → assets/providers/
├── sync_static_providers.py            # espelha assets/providers/ → Static/providers/
├── capture_terabox_cookie_gui.py       # Tkinter: cola cookies.txt → rclone
├── _webengine_*.py                     # helpers chamados por verify_webengine.ps1
└── launchers/                          # *.bat de duplo-clique (ver §5)
```

Regra: scripts `.py` aqui são utilitários **fora** do runtime do app
(empacotamento, instalação, diagnóstico). Lógica usada pelo app vai para
`src/rdrive/core/` ou `src/rdrive/ui/`.

## 5. `scripts/launchers/` — atalhos `.bat` (uma implementação por launcher)

```
scripts/launchers/
├── Abrir-Chrome-TeraBox.bat       # → launch_terabox_chrome.ps1
├── Capturar-Cookie-TeraBox.bat    # → capture_terabox_cookie_gui.py
├── Configurar-TeraBox.bat         # → configurar_terabox.ps1
├── Montar-TeraBox.bat             # → mount_terabox.ps1
├── DevStatic-Live.bat             # Iniciar.bat com RDRIVE_STATIC_LIVE=1
└── DevStatic-Browser.bat          # preview HTTP em :8765 (sem PyQt)
```

Regra: **um** `.bat` por launcher, dentro de `scripts/launchers/`. Sem
duplicados/stubs na raiz (exceto `Iniciar.bat`, que é o launcher mestre).

## 6. `docs/` — documentação

```
docs/
├── ESTRUTURA.md       # (este ficheiro) — mapa de pastas
├── GIT-CURSOR.md      # fluxo Git + boas práticas Cursor
└── ui-reference.md    # referência UX detalhada (telas, micro-interações)
```

`ARCHITECTURE.md` fica na raiz por convenção GitHub (`ARCHITECTURE.md` no
topo é o padrão exibido na página inicial do repo).

## 7. `tests/` — pytest

```
tests/
├── test_app_service_delete.py
├── test_guided_setup.py
├── test_mount_manager.py
├── test_perf_idle.py
├── test_shared_mount.py
├── test_subprocess_utils.py
├── test_terabox_backend.py
├── test_terabox_browser.py
├── test_terabox_cookie.py
├── test_terabox_help_strings.py
└── test_terabox_login.py
```

Executar: `.venv\Scripts\python.exe -m pytest tests/ -q`.

## 8. `tools/` — binários externos (não versionados)

```
tools/
├── rclone-extra/
│   ├── .gitkeep
│   ├── NOTICE              # atribuição rclone + PR 8508
│   └── rclone.exe          # build com backend TeraBox (gitignored)
└── get-cookies-txt-locally/
    ├── .gitkeep
    ├── NOTICE              # atribuição kairi003
    └── (extensão Chrome v0.7.2 baixada em runtime — gitignored)
```

## 9. Pastas runtime (gitignored)

| Pasta    | Conteúdo                                                          |
|----------|-------------------------------------------------------------------|
| `.venv/` | ambiente Python local; criado por `Iniciar.bat`                   |
| `logs/`  | `rdrive.log`, `human.log`, `launcher.log`, `reset_vault.log`, …   |
| `tempo/` | backups manuais (`backup-YYYYMMDD-HHMMSS/`) com `MANIFEST.txt`   |

`tempo/` é apagável sem afetar o app; criada por scripts de limpeza como
snapshot reversível.

## 10. Regras de adição

1. **Novo módulo Python do app** → `src/rdrive/core/<domínio>/` ou `src/rdrive/ui/<área>/`.
2. **Novo script utilitário** (instalação, build, diagnóstico) → `scripts/`.
3. **Novo `.bat` de duplo-clique** → `scripts/launchers/`. Sem stubs na raiz.
4. **Nova documentação** → `docs/`. Nunca colocar `*.md` extras na raiz
   (`README.md` e `ARCHITECTURE.md` são as únicas exceções).
5. **Novos assets WebUI** → `Static/`. SVGs de provedores: editar fonte em
   `src/rdrive/assets/providers/` e rodar `python scripts/sync_static_providers.py`.
6. **Novo teste** → `tests/test_*.py`.
7. **Binário externo** → `tools/<nome>/` com `NOTICE` (atribuição) e
   `.gitignore` entry para o binário (ver §8).
