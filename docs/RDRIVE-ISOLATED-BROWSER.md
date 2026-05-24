# Browser isolado RDrive (Microsoft Edge)

Perfil descartável: `%LOCALAPPDATA%\RDrive\chrome-rdrive-isolated-profile`

(O nome da pasta mantém-se por compatibilidade; o browser lançado é **sempre Microsoft Edge**.)

## Usos

| Fluxo | Entrada UI |
|-------|------------|
| TeraBox | **Ligar conta TeraBox** |
| OAuth (Drive, OneDrive, …) | **Configuração automática** |

## Comportamento

- Login/autorização **manual** no Edge aberto pelo RDrive via **subprocess** (`msedge.exe` + perfil isolado).
- OAuth (Drive, OneDrive, …): **nunca** Playwright — evita bloqueio Google «navegador não seguro».
- TeraBox: login no Edge real; Playwright só para exportação automática da extensão (sem `enable-automation`).
- Após sucesso: credenciais ficam no **rclone** / campo cookie do RDrive; o **perfil Edge é apagado** (cache, senhas, «manter sessão»).
- TeraBox: `cookies.txt` exportado só em `%TEMP%\RDrive\cookie-export\<sessão>\` e removido após leitura.
- Playwright (quando usado) usa `channel="msedge"` e `ignore_default_args=["--enable-automation"]`.

## CLI

```powershell
.venv\Scripts\python.exe scripts\terabox\run_terabox_cookie_agent.py
```

Atalho manual: `scripts\launchers\Abrir-Edge-TeraBox.bat`

## Migração

O perfil antigo `chrome-terabox-profile` é removido no próximo reset/wipe.

Se o Microsoft Edge não estiver instalado, o `Iniciar.bat` e os fluxos TeraBox/OAuth tentam instalar via winget (`Microsoft.Edge`).
