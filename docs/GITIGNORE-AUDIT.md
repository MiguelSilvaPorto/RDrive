# Auditoria `.gitignore` — RDrive

**Data:** 2026-05-24  
**Objetivo:** Confirmar que o `.gitignore` **não bloqueia funcionalidade** do código (imports, UI, scripts, testes).

---

## 1. Git ignore vs runtime

| Conceito | Efeito |
|----------|--------|
| `.gitignore` | Controla **apenas** o que o Git rastreia/commita. |
| Python `import` | Resolve ficheiros **no disco** (`sys.path`, `PYTHONPATH`). |
| `Iniciar.bat` | Cria `.venv/`, instala deps, corre bootstrap — **independente** do Git. |

**Conclusão:** Ignorar `.venv/`, `logs/` ou binários em `tools/` **não impede** a app de correr localmente. Só afeta o que um `git clone` traz versionado.

---

## 2. `git check-ignore -v` — paths críticos

### Deve **NÃO** ser ignorado

| Categoria | Amostra / sweep | Resultado |
|-----------|-----------------|-----------|
| `src/rdrive/**/*.py` | 165 ficheiros `.py` em `src/`, `tests/`, `scripts/` | **PASS** — 0 ignorados |
| `src/rdrive/assets/providers/**/*.svg` | 15 SVG | **PASS** |
| `Static/index.html` | — | **PASS** |
| `Static/script.js` | — | **PASS** |
| `Static/css/**` | 6 ficheiros | **PASS** |
| `scripts/**/*.ps1`, `*.py`, `launchers/*.bat` | 10+ amostras + launchers | **PASS** |
| `Iniciar.bat` | — | **PASS** |
| `requirements.txt` | — | **PASS** |
| `pyproject.toml` | — | **PASS** |
| `tests/**` | `test_ctk_smoke.py`, `test_drive_validation.py` + sweep | **PASS** |
| `tools/**/.gitkeep`, `tools/**/NOTICE` | 4 ficheiros | **PASS** (exceções `!` activas) |

### Deve **SER** ignorado (intencional)

| Path | Regra | Resultado |
|------|-------|-----------|
| `tools/rclone-extra/rclone.exe` | `/tools/rclone-extra/*` | **PASS** |
| `tools/get-cookies-txt-locally/manifest.json` | `/tools/get-cookies-txt-locally/*` | **PASS** |
| `.venv/` | `/.venv/` | **PASS** |
| `logs/` | `logs/` | **PASS** |
| `tempo/` | `/tempo/` | **PASS** |

---

## 3. Simulação de clone limpo (`git ls-files`)

| Diretório | Ficheiros versionados |
|-----------|----------------------|
| `src/` | 151 |
| `Static/` | 48 (6 css, 1 html, 1 js, 40 providers) |
| `scripts/` | 26 |
| `tests/` | 15 |
| `src/rdrive/assets/` | 37 |
| `tools/` | 4 (`.gitkeep` + `NOTICE` × 2 pastas) |

**Padrões sensíveis/binários em ficheiros rastreados** (`.enc`, `.pem`, `.key`, `.exe`, `.env`, `rclone.conf`, `cookies.txt`, …):

→ **Nenhum** — **PASS**

**Nota:** Existem ~21 ficheiros **untracked** em `src/`, `tests/`, `scripts/` (ex.: `resolver.py`, novos testes CTK). **Não** estão ignorados — apenas ainda não commitados. Não é falha do `.gitignore`.

---

## 4. Padrões perigosos no `.gitignore`

| Padrão procurado | Encontrado? | Risco |
|------------------|-------------|-------|
| `*.py` (ignorar todos) | **Não** | — |
| `src/` | **Não** (só comentário) | — |
| `Static` / `scripts` | **Não** | — |
| Regra `*` global em código | **Não** | — |
| `*.py[cod]` | Sim | **Baixo** — só bytecode (`.pyc`, `.pyo`) |
| `*.manifest` | Sim | **Baixo** — builds; extensão Chrome já coberta por `/tools/get-cookies-txt-locally/*` |
| `*.enc` | Sim | **Baixo** — dados runtime/segredos, não código-fonte |
| `!` conflitos em `tools/` | `/tools/.../*` + `!.../.gitkeep` + `!.../NOTICE` | **OK** — exceções funcionam |

**Alterações ao `.gitignore` nesta auditoria:** nenhuma (nenhum problema real encontrado).

---

## 5. Smoke runtime

```text
.venv\Scripts\python.exe -c "from rdrive.app import main; from rdrive.ui.ctk.bootstrap import run_ctk_main"
→ IMPORT OK

.venv\Scripts\python.exe -m pytest tests/test_ctk_smoke.py tests/test_drive_validation.py -q --tb=no
→ 11 passed in 1.16s
```

**Resultado:** **PASS**

---

## 6. Dependências de bootstrap

| Artefacto | Estado no repo | Recuperação |
|-----------|----------------|-------------|
| `tools/get-cookies-txt-locally/` | Só `.gitkeep` + `NOTICE` | `scripts/bootstrap/bootstrap_cookies_extension.ps1` (via `Iniciar.bat`) descarrega release v0.7.2 se `manifest.json` faltar |
| `tools/rclone-extra/rclone.exe` | Ignorado (binário) | `resolve_rclone_executable()`: bundled → `RDRIVE_RCLONE_EXE` → `rclone` no PATH; script `scripts/terabox/install_rclone_terabox.ps1` documenta instalação TeraBox |

Scripts de bootstrap **versionados:** `scripts/bootstrap/bootstrap_cookies_extension.ps1`, `bootstrap_cookies_extension.py`.

**Resultado:** **PASS** — fluxo documentado e funcional após clone + `Iniciar.bat`.

---

## 7. Checklist final

| # | Verificação | Status |
|---|-------------|--------|
| 1 | `.gitignore` não afecta imports Python | **PASS** |
| 2 | Código-fonte (`src/`, `tests/`, `scripts/`) não ignorado | **PASS** |
| 3 | UI estática (`Static/`) não ignorada | **PASS** |
| 4 | Assets SVG de providers não ignorados | **PASS** |
| 5 | Binários/segredos ignorados intencionalmente | **PASS** |
| 6 | `tools/` mantém `.gitkeep` + `NOTICE` versionados | **PASS** |
| 7 | Nenhum segredo/binário rastreado | **PASS** |
| 8 | Sem regras perigosas (`*.py`, `src/`, etc.) | **PASS** |
| 9 | Smoke imports + pytest | **PASS** |
| 10 | Bootstrap extensão + rclone documentados | **PASS** |

**Veredicto geral:** **PASS** — `.gitignore` seguro; não bloqueia funcionalidade.

---

## Após clone

```bat
Iniciar.bat
```

Cria `.venv/`, instala `requirements.txt`, corre bootstrap da extensão cookies (se necessário) e inicia a app. Para TeraBox/rclone: copiar `rclone.exe` para `tools/rclone-extra/` ou usar `rclone` no PATH com backend TeraBox.
