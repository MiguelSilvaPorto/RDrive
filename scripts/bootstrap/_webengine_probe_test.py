"""Teste mínimo de renderização QWebEngine (diagnóstico)."""
from __future__ import annotations

import os
import sys

if sys.platform == "win32" and not os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip():
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --disable-gpu-compositing"

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView

TEST_URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.google.com/"
TIMEOUT_MS = 8000


def main() -> int:
    app = QApplication(sys.argv)
    view = QWebEngineView()
    view.resize(800, 600)
    view.show()
    state = {"done": False, "render_ok": False}

    def finish(code: int, msg: str) -> None:
        if state["done"]:
            return
        state["done"] = True
        print(f"RESULT: {code} — {msg}")
        app.quit()

    def on_load(ok: bool) -> None:
        if not ok:
            finish(2, "load_finished=False")
            return

        def on_probe(has_content: object) -> None:
            if has_content is True:
                finish(0, "render_ok")
            else:
                finish(3, "blank_dom")

        view.page().runJavaScript(
            "(document.body && document.body.innerText.trim().length > 20) || "
            "document.querySelector('input, button, a, img') !== null",
            on_probe,
        )

    view.loadFinished.connect(on_load)
    QTimer.singleShot(TIMEOUT_MS, lambda: finish(4, "timeout"))
    view.load(QUrl(TEST_URL))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
