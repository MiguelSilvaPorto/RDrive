## RDrive Semi-stable 0.2.1

Correção crítica de arranque no Windows (CTk):

- **Crash imediato após bootstrap** — ícones SVG de provedores usavam PyQt6 (`QPainter`/`QSvgRenderer`) sem `QGuiApplication`, provocando encerramento nativo (`0xC0000409`) ao abrir a janela CTk.
- **Duas consolas no arranque** — `Iniciar.bat` delegava ao `log_launcher.ps1` mantendo a consola do duplo-clique aberta; agora delega com `start` e uma única consola visível na 1.ª execução.
- **`pip install -e .`** — garante o pacote `rdrive` no venv de releases extraídas.

### Test plan

1. Extrair `RDrive-0.2.1-semi-stable-windows.zip` numa pasta limpa.
2. Executar `Iniciar.bat` — 1.ª vez: uma consola com bootstrap; depois ícone na bandeja/janela CTk.
3. Confirmar `logs\launcher.log` termina com exit code 0 e `logs\human.log` regista bandeja visível.
