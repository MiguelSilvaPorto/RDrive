"""Captura cookie TeraBox pelo navegador integrado RDrive (sem abrir a app completa).

Uso:
  .venv\\Scripts\\python.exe scripts\\capture_terabox_cookie_gui.py
  ou duplo clique em Capturar-Cookie-TeraBox.bat
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _configure_webengine() -> None:
    if os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip():
        return
    if sys.platform == "win32":
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
            "--disable-gpu --disable-gpu-compositing --disable-software-rasterizer"
        )


def _resolve_rclone() -> Path | None:
    env = os.environ.get("RDRIVE_RCLONE_EXE", "").strip()
    if env:
        path = Path(env)
        if path.is_file():
            return path
    bundled = ROOT / "tools" / "rclone-extra" / "rclone.exe"
    if bundled.is_file():
        return bundled
    return None


def _configure_rclone_remote(rclone: Path, remote: str, cookie: str) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [
                str(rclone),
                "config",
                "create",
                remote,
                "terabox",
                "cookie",
                cookie,
                "--non-interactive",
                "--obscure",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"código {proc.returncode}"
        return False, err
    return True, ""


def _test_remote(rclone: Path, remote: str) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [str(rclone), "lsd", f"{remote}:", "--timeout", "2m"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"código {proc.returncode}"
        return False, err
    return True, (proc.stdout or "").strip()


def main() -> int:
    os.chdir(ROOT)
    _configure_webengine()

    from PyQt6.QtWidgets import QApplication, QMessageBox

    from rdrive.ui.foundation.app_icon import app_icon, configure_windows_app_identity
    from rdrive.ui.terabox.terabox_browser import (
        capture_terabox_cookie_via_browser,
        probe_terabox_cookie_from_profile,
    )

    configure_windows_app_identity()
    app = QApplication(sys.argv)
    app.setWindowIcon(app_icon())

    cookie = ""
    source = ""

    probed = probe_terabox_cookie_from_profile()
    if probed.get("ok") and probed.get("cookie"):
        use = QMessageBox.question(
            None,
            "RDrive — TeraBox",
            "Foi encontrada uma sessão guardada no navegador integrado.\n\n"
            "Usar este cookie?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if use == QMessageBox.StandardButton.Yes:
            cookie = str(probed["cookie"])
            source = "perfil_guardado"

    if not cookie:
        result = capture_terabox_cookie_via_browser(auto_capture=True)
        if result.get("cancelled"):
            return 0
        if not result.get("ok") or not result.get("cookie"):
            hint = str(result.get("hint") or result.get("error") or "Captura cancelada.")
            QMessageBox.warning(None, "RDrive — TeraBox", hint)
            return 1
        cookie = str(result["cookie"])
        source = "navegador_integrado"

    ndus = "ndus=" in cookie.lower()
    QMessageBox.information(
        None,
        "RDrive — TeraBox",
        f"Cookie capturado ({source}).\n"
        f"Contém ndus=: {'sim' if ndus else 'não'}\n\n"
        "Pode configurar o remote rclone agora.",
    )

    rclone = _resolve_rclone()
    if rclone is None:
        QMessageBox.warning(
            None,
            "RDrive — TeraBox",
            "rclone-extra não encontrado em tools\\rclone-extra\\.\n"
            "O cookie foi capturado — use Adicionar unidade no RDrive ou "
            "Configurar-TeraBox.bat com o cookie colado.",
        )
        return 0

    remote = "terabox_pessoal"
    configure = QMessageBox.question(
        None,
        "RDrive — TeraBox",
        f"Configurar remote «{remote}» no rclone e testar ligação?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    if configure != QMessageBox.StandardButton.Yes:
        return 0

    ok, err = _configure_rclone_remote(rclone, remote, cookie)
    if not ok:
        QMessageBox.critical(
            None,
            "RDrive — TeraBox",
            f"Falha ao criar remote:\n{err}",
        )
        return 1

    ok, out = _test_remote(rclone, remote)
    if not ok:
        QMessageBox.critical(
            None,
            "RDrive — TeraBox",
            f"Remote criado mas teste falhou:\n{out}",
        )
        return 1

    preview = "\n".join(out.splitlines()[:8]) if out else "(raiz listada)"
    QMessageBox.information(
        None,
        "RDrive — TeraBox",
        f"Ligação OK — remote «{remote}:»\n\n{preview}\n\n"
        "No RDrive: Adicionar unidade → TeraBox → Ligar e guardar.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
