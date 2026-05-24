# Testes automatizados do RDrive (pytest)

A pasta `tests/` contém **testes automatizados de software** para o código do RDrive —
unitários e de integração leve, executados com [pytest](https://docs.pytest.org/).

**Não** são testes de IA, avaliação de LLM, prompts de agente ou experimentos de
Cursor/Auto. Também **não** são a aba **Configurações → Testes** da aplicação (diagnóstico
interativo: rclone, WinFsp, velocidade, montagem) — essa UI vive em
`src/rdrive/core/diagnostics/`.

## Como executar

Com o ambiente virtual ativo (criado por `Iniciar.bat`):

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

Um ficheiro ou módulo específico:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_drive_delete.py -q
.venv\Scripts\python.exe -m pytest tests/test_ctk_smoke.py tests/test_cloud_benchmark.py -q
```

Saída verbosa (útil para depuração):

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v --tb=short
```

## Convenções

| Regra | Detalhe |
|-------|---------|
| Nome dos ficheiros | `test_*.py` na raiz de `tests/` (sem subpastas) |
| Nome das funções | `test_<comportamento>()` |
| Dependências | `pytest` (e mocks da stdlib); sem rede nem cloud real na maioria dos casos |
| UI CTk | smoke tests importam módulos sem abrir `mainloop` (sem display no CI) |

## O que é coberto

| Área | Exemplos de ficheiros |
|------|------------------------|
| Montagem e letras | `test_mount_manager.py`, `test_shared_mount.py`, `test_drive_validation.py` |
| Eliminação de unidades | `test_drive_delete.py`, `test_app_service_delete.py` |
| Setup guiado / cloud | `test_guided_setup.py`, `test_provider_setup_registry.py` |
| UI CustomTkinter | `test_ctk_smoke.py`, `test_ctk_navigation.py`, `test_ctk_cloud_assistant.py`, … |
| TeraBox | `test_terabox_*.py` |
| Runtime / watchdog | `test_app_restart_ctk.py`, `test_watchdog_restart_prompt.py`, `test_perf_idle.py` |
| Benchmark diagnóstico | `test_cloud_benchmark.py` (filesystem mock, sem upload real) |

## Onde **não** colocar código

- Scripts utilitários, scratch ou debug → `scripts/dev/`
- Diagnóstico manual na app → `src/rdrive/core/diagnostics/`
- Novos testes pytest → `tests/test_<domínio>.py`

Mapa geral do repositório: `docs/ESTRUTURA.md` §7.
