"""Teste setHtml (probe local sem rede)."""
from __future__ import annotations

import os
import sys

if sys.platform == "win32" and not os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip():
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --disable-gpu-compositing"

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView

TIMEOUT_MS = 6000


def main() -> int:
    app = QApplication(sys.argv)
    view = QWebEngineView()
    view.resize(400, 300)
    view.show()
    state = {"done": False}

    def finish(code: int, msg: str) -> None:
        if state["done"]:
            return
        state["done"] = True
        print(f"RESULT: {code} — {msg}")
        app.quit()

    def on_probe(has_content: object) -> None:
        finish(0 if has_content is True else 3, "render_ok" if has_content else "blank_dom")

    def on_load(ok: bool) -> None:
        if not ok:
            finish(2, "load_failed")
            return
        QTimer.singleShot(400, lambda: view.page().runJavaScript(
            "document.body && document.body.innerText.trim().length > 5",
            on_probe,
        ))

    view.loadFinished.connect(on_load)
    QTimer.singleShot(TIMEOUT_MS, lambda: finish(4, "timeout"))
    view.setHtml("<html><body><p>RDrive WebEngine probe</p></body></html>")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
