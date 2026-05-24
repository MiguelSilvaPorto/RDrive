## RDrive Semi-stable 0.2.2 — privacidade e empacotamento

### Segurança

- Validação automática (`validate_release.ps1`) no staging e no zip Windows — a publicação **falha** se forem detectados ficheiros de runtime (`rclone.conf`, `cookies.txt`, `drives.enc`, perfis de browser TeraBox, `.venv`, etc.).
- Exclusões reforçadas no instalador/zip (`chrome-rdrive-isolated-profile`, `extensions`, cookies de browser).

### Nota para quem testou 0.2.1

O asset `RDrive-0.2.1-semi-stable-windows.zip` foi auditado e **substituído/removido** por precaução. A sessão TeraBox no mesmo PC vem de `%LOCALAPPDATA%\RDrive\`, não do zip — mesmo assim, **revogue a sessão TeraBox** se partilhou o PC ou suspeita de exposição.

### Test plan

1. Extrair `RDrive-0.2.2-semi-stable-windows.zip` numa pasta **nova** (outro utilizador Windows ou VM).
2. `Iniciar.bat` — não deve aparecer conta TeraBox sem configurar.
3. `.\scripts\build\validate_release.ps1 -Path dist\RDrive-0.2.2-semi-stable-windows.zip` → OK.
