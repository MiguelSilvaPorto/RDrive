## RDrive Semi-stable 0.2.3 — arranque em release

### Correções

- **Bootstrap pip:** após `python -m venv`, o launcher garante `pip` com `ensurepip` e recria `.venv` se estiver corrompido (`No module named pip`).
- **Arranques paralelos:** `log_launcher.ps1` usa lock em `.venv\.launcher-bootstrap.lock` para evitar vários bootstraps em simultâneo.
- **Código de saída:** `logs\.launcher-exit-code` e deteção de `[ERRO]` no log — a caixa de diálogo aparece quando o bootstrap falha de facto.
- **Teste isolado:** `Iniciar-Isolado.bat` e `scripts\test\isolated_launch_test.ps1` (AppData limpo, relatório com timestamps).

### Test plan

1. Extrair zip numa pasta nova → `Iniciar.bat` → `logs\launcher.log` sem `[ERRO]`, `logs\.launcher-exit-code` = `0`.
2. `Iniciar-Isolado.bat` ou `isolated_launch_test.ps1 -Reset` — não deve usar `%LOCALAPPDATA%\RDrive\` existente.
3. Se 0.2.2 falhou com pip: apagar `.venv` na pasta extraída e repetir com 0.2.3.
