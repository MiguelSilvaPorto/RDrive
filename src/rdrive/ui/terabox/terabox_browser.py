"""Navegador integrado TeraBox — captura automática de cookies de sessão.

Usa um ``QWebEngineProfile`` dedicado (perfil persistente) para manter a sessão
entre aberturas. O utilizador faz login no site; o RDrive lê os cookies do perfil
sem F12 / DevTools.

TeraBox bloqueia o User-Agent predefinido do QtWebEngine — aplicamos UA Chrome-like
e activamos ``QWebEngineSettings`` essenciais (JS, localStorage).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from platformdirs import user_data_dir
from PyQt6.QtCore import QEvent, QEventLoop, QObject, QTimer, QUrl, Qt
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rdrive.core.logging.app_logger import get_app_logger
from rdrive.core.cloud.terabox_setup import (
    TERABOX_LOGIN_URL,
    TERABOX_LOGIN_URL_FALLBACKS,
    TERABOX_MAIN_URL,
    cookie_contains_ndus,
    open_terabox_login,
    validate_terabox_cookie,
)

if TYPE_CHECKING:
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile

_PROFILE_NAME = "rdrive-terabox-browser"
_WEBENGINE_IMPORT_OK: bool | None = None
_WEBENGINE_RENDER_OK: bool | None = None
_AUTO_CAPTURE_DEBOUNCE_MS = 1500
_SESSION_PROBE_MS = 450
_BLANK_PAGE_TIMEOUT_MS = 30_000
_WEBENGINE_RENDER_PROBE_MS = 5_000
_PROGRESS_STUCK_MS = 12_000
_TERABOX_LOAD_TIMEOUT_MS = 35_000
_MAX_LOAD_FAILURES_BEFORE_SYSTEM_BROWSER = 2
_PROBE_HTML = (
    "<html><head><meta charset='utf-8'></head>"
    "<body><p id='rdrive-probe'>RDrive WebEngine probe</p></body></html>"
)
_PROBE_JS = (
    "(document.body && document.body.innerText.trim().length > 5) || "
    "document.getElementById('rdrive-probe') !== null"
)
WEBENGINE_BROKEN_MESSAGE_PT = (
    "PyQt6-WebEngine não instalado ou incompleto — "
    "a página integrada fica em branco."
)
WEBENGINE_REINSTALL_HINT_PT = (
    "Reinstale no venv:\n"
    "  .venv\\Scripts\\python.exe -m pip install --upgrade \"PyQt6-WebEngine>=6.6.0\"\n"
    "Ou execute: scripts\\verify_webengine.ps1"
)

# TeraBox (e CDNs) rejeitam o UA QtWebEngine; Chrome recente evita página em branco.
CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

SESSION_INCOMPLETE_NO_NDUS_PT = (
    "Sessão incompleta no navegador integrado — falta o cookie «ndus» (login não concluído). "
    "Conclua o login aqui até ver «Meus ficheiros», ou importe cookies.txt exportado "
    "do Chrome (extensão de exportação — não use F12 no TeraBox)."
)

CHROME_IMPORT_GUIDE_PT = (
    "No Windows, a página integrada do TeraBox costuma ficar em branco — isto é uma limitação "
    "do motor WebEngine, não da sua conta.\n\n"
    "Como já está logado no Chrome:\n"
    "1. Instale a extensão «Get cookies.txt LOCALLY» (Chrome Web Store).\n"
    "2. Abra terabox.com no Chrome (sessão ativa).\n"
    "3. Exporte cookies para um ficheiro .txt.\n"
    "4. Clique «Importar cookies.txt» abaixo.\n\n"
    "Não use F12 no site TeraBox — o site bloqueia e fecha a página."
)

INTEGRATED_BROWSER_BLANK_PT = (
    "O navegador integrado pode ficar em branco no Windows. "
    "Use a importação do Chrome acima — é o método recomendado."
)

TERABOX_ANTI_DEVTOOLS_HINT_PT = (
    "O site TeraBox bloqueia ferramentas de desenvolvedor (F12) — "
    "use sempre o navegador integrado do RDrive."
)

MANUAL_COOKIE_FALLBACK_HINT_PT = (
    "Chrome logado: instale «Get cookies.txt LOCALLY» (ou similar), exporte terabox.com, "
    "clique «Importar cookies.txt». Ou cole ndus= manualmente. Não use F12 no TeraBox."
)

SYSTEM_BROWSER_FALLBACK_HINT_PT = (
    "Site aberto no browser do sistema — faça login, volte a esta janela e "
    "tente «Capturar manualmente» ou recarregue o integrado (perfil persistente). "
    "Se ainda falhar, cole abaixo um cookie exportado de outro browser."
)


def parse_cookie_header_pairs(header: str) -> dict[str, str]:
    """Extrai pares nome=valor de um cabeçalho Cookie (sem registar valores)."""
    normalized = header.strip()
    if normalized.lower().startswith("cookie:"):
        normalized = normalized.split(":", 1)[1].strip()
    pairs: dict[str, str] = {}
    for part in normalized.split(";"):
        chunk = part.strip()
        if not chunk or "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        name = name.strip()
        if name:
            pairs[name] = value.strip()
    return pairs


def build_cookie_header_from_pairs(pairs: dict[str, str]) -> str:
    """Monta cabeçalho Cookie a partir de pares nome=valor."""
    return "; ".join(f"{name}={value}" for name, value in pairs.items() if name)


def read_terabox_cookie_pairs_from_sqlite() -> dict[str, str]:
    """Lê cookies TeraBox do ficheiro Chromium ``Cookies`` do perfil integrado."""
    import sqlite3

    cookies_path = terabox_browser_storage_dir() / "Cookies"
    if not cookies_path.is_file():
        return {}
    pairs: dict[str, str] = {}
    try:
        conn = sqlite3.connect(f"file:{cookies_path.as_posix()}?mode=ro", uri=True)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name, value FROM cookies "
                "WHERE host_key LIKE '%terabox%' AND value IS NOT NULL AND TRIM(value) != ''"
            )
            for name, value in cur.fetchall():
                key = str(name or "").strip()
                if key:
                    pairs[key] = str(value or "").strip()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        get_app_logger().warning(
            f"[WEBUI] TeraBox: falha a ler Cookies.sqlite ({exc})",
            module="webui",
        )
    return pairs


def parse_netscape_cookie_file(text: str) -> dict[str, str]:
    """Analisa ficheiro cookies.txt (formato Netscape) — linhas com host terabox."""
    pairs: dict[str, str] = {}
    for line in text.splitlines():
        chunk = line.strip()
        if not chunk or chunk.startswith("#"):
            continue
        parts = chunk.split("\t")
        if len(parts) < 7:
            continue
        host = parts[0].lower()
        if "terabox" not in host:
            continue
        name = parts[5].strip()
        value = parts[6].strip()
        if name:
            pairs[name] = value
    return pairs


def diagnose_terabox_profile_session() -> dict[str, Any]:
    """Estado da sessão no perfil integrado (sem abrir diálogo)."""
    pairs = read_terabox_cookie_pairs_from_sqlite()
    header = build_cookie_header_from_pairs(pairs)
    has_ndus = cookie_contains_ndus(header)
    return {
        "has_cookies": bool(pairs),
        "has_ndus": has_ndus,
        "cookie_count": len(pairs),
        "names": sorted(pairs.keys()),
        "header_len": len(header),
    }


class _BlockDevToolsEventFilter(QObject):
    """Bloqueia atalhos de DevTools na vista WebEngine (TeraBox fecha se abrir)."""

    _BLOCKED_KEYS = frozenset({Qt.Key.Key_F12})

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(watched, event)
        key_event = event
        key = key_event.key()
        mods = key_event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if key in self._BLOCKED_KEYS:
            return True
        if ctrl and shift and key in (
            Qt.Key.Key_I,
            Qt.Key.Key_J,
            Qt.Key.Key_C,
            Qt.Key.Key_U,
        ):
            return True
        return super().eventFilter(watched, event)


def _create_terabox_request_interceptor(on_cookie_header: Any, parent: QObject | None) -> Any:
    """Observa pedidos a terabox.com e extrai Cookie dos cabeçalhos (httpOnly)."""
    from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInterceptor

    class _Interceptor(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info: object) -> None:  # noqa: N802
            try:
                url = info.requestUrl().toString()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                return
            if "terabox" not in url.lower():
                return
            try:
                raw = bytes(info.httpHeader(b"Cookie")).decode("utf-8", errors="replace")  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                return
            if raw.strip():
                on_cookie_header(raw)

    return _Interceptor(parent)


def terabox_browser_storage_dir() -> Path:
    path = Path(user_data_dir("RDrive")) / "terabox-browser"
    path.mkdir(parents=True, exist_ok=True)
    return path


def clear_terabox_browser_storage(*, cache_only: bool = False) -> None:
    """Limpa cache/perfil WebEngine TeraBox (workaround página em branco)."""
    storage = terabox_browser_storage_dir()
    cache = storage / "cache"
    if cache.exists():
        shutil.rmtree(cache, ignore_errors=True)
    if cache_only:
        return
    for name in ("Cookies", "Cookies-journal", "Network Persistent State", "Visited Links"):
        target = storage / name
        if target.is_file():
            target.unlink(missing_ok=True)


def _ensure_webengine_imported() -> bool:
    """Importa PyQt6-WebEngine sob demanda (evita falha de arranque se DLLs faltarem)."""
    global _WEBENGINE_IMPORT_OK
    if _WEBENGINE_IMPORT_OK is not None:
        return _WEBENGINE_IMPORT_OK
    try:
        import PyQt6.QtWebEngineCore  # noqa: F401
        import PyQt6.QtWebEngineWidgets  # noqa: F401
    except Exception:  # noqa: BLE001
        _WEBENGINE_IMPORT_OK = False
    else:
        _WEBENGINE_IMPORT_OK = True
    return _WEBENGINE_IMPORT_OK


def webengine_import_ok() -> bool:
    """Importação PyQt6-WebEngine disponível (não garante renderização)."""
    return _ensure_webengine_imported()


def locate_qtwebengine_process() -> Path | None:
    """Caminho para QtWebEngineProcess.exe no pacote PyQt6 (None se em falta)."""
    if not webengine_import_ok():
        return None
    try:
        import PyQt6

        pkg = Path(PyQt6.__file__).resolve().parent
        for candidate in pkg.rglob("QtWebEngineProcess.exe"):
            if candidate.is_file():
                return candidate
    except Exception:  # noqa: BLE001
        return None
    return None


def webengine_binaries_ok() -> bool:
    """Verifica processo auxiliar e recursos .pak do WebEngine."""
    if not webengine_import_ok():
        return False
    if locate_qtwebengine_process() is None:
        return False
    try:
        import PyQt6

        pkg = Path(PyQt6.__file__).resolve().parent
        return any(pkg.rglob("qtwebengine_resources.pak"))
    except Exception:  # noqa: BLE001
        return False


def probe_webengine_render(*, timeout_ms: int = _WEBENGINE_RENDER_PROBE_MS) -> tuple[bool, str]:
    """Teste rápido de renderização (setHtml) — executar na thread GUI com QApplication."""
    if not webengine_import_ok():
        return False, "import_failed"
    if not webengine_binaries_ok():
        return False, "binaries_missing"

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    if QApplication.instance() is None:
        return False, "no_qapplication"

    view = QWebEngineView()
    loop = QEventLoop()
    result = {"ok": False, "reason": "timeout"}

    def finish(*, ok: bool, reason: str) -> None:
        if result["reason"] != "timeout":
            return
        result["ok"] = ok
        result["reason"] = reason
        if loop.isRunning():
            loop.quit()

    def on_probe(has_content: object) -> None:
        finish(ok=has_content is True, reason="render_ok" if has_content else "blank_dom")

    def on_load(ok: bool) -> None:
        if not ok:
            finish(ok=False, reason="load_failed")
            return
        QTimer.singleShot(350, lambda: view.page().runJavaScript(_PROBE_JS, on_probe))

    view.loadFinished.connect(on_load)
    QTimer.singleShot(timeout_ms, lambda: finish(ok=False, reason="timeout"))
    view.setHtml(_PROBE_HTML)
    loop.exec()
    view.deleteLater()
    return result["ok"], result["reason"]


def webengine_render_ok(*, force: bool = False) -> bool:
    """Renderização local OK (cacheada após primeira sonda)."""
    global _WEBENGINE_RENDER_OK
    if not force and _WEBENGINE_RENDER_OK is not None:
        return _WEBENGINE_RENDER_OK
    ok, _reason = probe_webengine_render()
    _WEBENGINE_RENDER_OK = ok
    return ok


def get_webengine_status(*, probe_render: bool = False) -> dict[str, Any]:
    """Estado WebEngine: import vs binários vs renderização."""
    import_ok = webengine_import_ok()
    binaries_ok = webengine_binaries_ok() if import_ok else False
    render_ok: bool | None = None
    render_reason = ""
    if probe_render and import_ok and binaries_ok:
        render_ok, render_reason = probe_webengine_render()
    elif _WEBENGINE_RENDER_OK is not None:
        render_ok = _WEBENGINE_RENDER_OK
    fully_ok = import_ok and binaries_ok and (render_ok is not False)
    return {
        "import_ok": import_ok,
        "binaries_ok": binaries_ok,
        "render_ok": render_ok,
        "render_reason": render_reason,
        "available": fully_ok,
        "process_path": str(locate_qtwebengine_process() or ""),
    }


def webengine_available() -> bool:
    """Import OK (rápido). Use ``get_webengine_status(probe_render=True)`` para render."""
    return webengine_import_ok()


def verify_webengine_script_path() -> Path:
    from rdrive.core.paths.project_paths import resolve_project_root

    return resolve_project_root() / "scripts" / "verify_webengine.ps1"


def show_webengine_broken_dialog(parent: QWidget | None = None) -> None:
    """Diálogo com instruções e botão para executar verify_webengine.ps1."""
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Icon.Warning)
    msg.setWindowTitle("RDrive — WebEngine")
    msg.setText(WEBENGINE_BROKEN_MESSAGE_PT)
    msg.setInformativeText(
        f"{WEBENGINE_REINSTALL_HINT_PT}\n\n"
        "Enquanto isso, use «Abrir no browser do sistema» para login TeraBox "
        "e cole o cookie exportado (sem F12 no terabox.com)."
    )
    verify_btn = msg.addButton("Executar verificação", QMessageBox.ButtonRole.ActionRole)
    docs_btn = msg.addButton("Abrir README", QMessageBox.ButtonRole.ActionRole)
    msg.addButton(QMessageBox.StandardButton.Ok)

    msg.exec()
    clicked = msg.clickedButton()
    if clicked is verify_btn:
        script = verify_webengine_script_path()
        if script.is_file():
            subprocess.Popen(  # noqa: S603
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                ],
                cwd=str(script.parent.parent),
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
        else:
            QMessageBox.warning(
                parent,
                "RDrive",
                f"Script não encontrado:\n{script}",
            )
    elif clicked is docs_btn:
        from PyQt6.QtGui import QDesktopServices

        readme = verify_webengine_script_path().parent.parent / "README.md"
        if readme.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(readme.resolve())))


def webengine_broken_result(*, reason: str = "") -> dict[str, Any]:
    """Payload padrão quando WebEngine não renderiza."""
    detail = WEBENGINE_BROKEN_MESSAGE_PT
    if reason == "binaries_missing":
        detail = "PyQt6-WebEngine incompleto (QtWebEngineProcess.exe ou recursos em falta)."
    elif reason == "import_failed":
        detail = "PyQt6-WebEngine não instalado."
    return {
        "ok": False,
        "webengine_broken": True,
        "error": detail,
        "hint": WEBENGINE_REINSTALL_HINT_PT,
        "fallback": True,
        "verify_script": str(verify_webengine_script_path()),
    }


def configure_terabox_webengine_profile(profile: QWebEngineProfile) -> None:
    """Perfil persistente com UA e idioma compatíveis com terabox.com."""
    from PyQt6.QtWebEngineCore import QWebEngineProfile

    default = QWebEngineProfile.defaultProfile()
    profile.setHttpUserAgent(CHROME_USER_AGENT)
    profile.setHttpAcceptLanguage(
        default.httpAcceptLanguage() or "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    )
    profile.setPersistentCookiesPolicy(
        profile.PersistentCookiesPolicy.ForcePersistentCookies
    )
    profile.setSpellCheckEnabled(False)


def configure_terabox_webengine_settings(page: QWebEnginePage) -> None:
    """Activa capacidades mínimas para SPA de login TeraBox."""
    from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings

    settings = page.settings()
    default_settings = QWebEngineProfile.defaultProfile().settings()

    attrs = QWebEngineSettings.WebAttribute
    enabled = (
        "JavascriptEnabled",
        "LocalStorageEnabled",
        "AutoLoadImages",
        "ErrorPageEnabled",
        "JavascriptCanOpenWindows",
        "AllowWindowActivationFromJavaScript",
    )
    disabled = (
        "WebGLEnabled",
        "Accelerated2dCanvasEnabled",
    )
    for name in enabled:
        attr = getattr(attrs, name, None)
        if attr is not None:
            try:
                value = default_settings.testAttribute(attr)
            except Exception:  # noqa: BLE001
                value = True
            settings.setAttribute(attr, value)
    for name in disabled:
        attr = getattr(attrs, name, None)
        if attr is not None:
            settings.setAttribute(attr, False)


class TeraboxWebEnginePage:
    """Factory — subclasse real definida após import WebEngine."""

    @staticmethod
    def create(profile: QWebEngineProfile, parent: QWidget | None, log: Any) -> QWebEnginePage:
        from PyQt6.QtWebEngineCore import QWebEnginePage

        class _Page(QWebEnginePage):
            def certificateError(self, error: object) -> bool:  # noqa: N802
                try:
                    log.warning(
                        "[WEBUI] TeraBox: erro certificado SSL — a aceitar",
                        module="webui",
                    )
                    error.acceptCertificate()  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    pass
                return True

        return _Page(profile, parent)


class TeraboxCookieImportDialog(QDialog):
    """Captura cookie via importação Chrome — sem WebEngine (recomendado no Windows)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._result_cookie: str | None = None
        self._use_integrated = False
        self.setWindowTitle("RDrive — Cookie TeraBox (importar do Chrome)")
        self.resize(640, 420)
        self.setMinimumSize(520, 360)

        layout = QVBoxLayout(self)
        guide = QLabel(CHROME_IMPORT_GUIDE_PT)
        guide.setWordWrap(True)
        layout.addWidget(guide)

        row = QHBoxLayout()
        self._cookie_input = QPlainTextEdit()
        self._cookie_input.setPlaceholderText("Ou cole aqui o cabeçalho Cookie (ndus=…)")
        self._cookie_input.setMaximumHeight(80)
        row.addWidget(self._cookie_input, 1)
        layout.addLayout(row)

        actions = QHBoxLayout()
        import_btn = QPushButton("Importar cookies.txt")
        import_btn.setDefault(True)
        import_btn.clicked.connect(self._import_file)
        actions.addWidget(import_btn)
        paste_btn = QPushButton("Usar texto colado")
        paste_btn.clicked.connect(self._accept_pasted)
        actions.addWidget(paste_btn)
        layout.addLayout(actions)

        integrated_btn = QPushButton("Tentar navegador integrado (experimental)")
        integrated_btn.setToolTip(INTEGRATED_BROWSER_BLANK_PT)
        integrated_btn.clicked.connect(self._choose_integrated)
        layout.addWidget(integrated_btn)

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    def cookie_result(self) -> str | None:
        return self._result_cookie

    def wants_integrated_browser(self) -> bool:
        return self._use_integrated

    def _import_file(self) -> None:
        from PyQt6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar cookies TeraBox",
            "",
            "Cookies (*.txt);;Todos (*.*)",
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            QMessageBox.warning(self, "TeraBox", f"Não foi possível ler o ficheiro:\n{exc}")
            return
        pairs = parse_netscape_cookie_file(text)
        header = build_cookie_header_from_pairs(pairs) if pairs else text.strip()
        self._apply_cookie(header)

    def _accept_pasted(self) -> None:
        self._apply_cookie(self._cookie_input.toPlainText().strip())

    def _apply_cookie(self, raw: str) -> None:
        if not raw:
            QMessageBox.warning(self, "TeraBox", "Selecione um ficheiro ou cole o cookie.")
            return
        ok, msg = validate_terabox_cookie(raw)
        if not ok:
            QMessageBox.warning(self, "TeraBox", msg or "Cookie inválido (falta ndus=).")
            return
        self._result_cookie = raw.strip()
        self.accept()

    def _choose_integrated(self) -> None:
        self._use_integrated = True
        self.reject()


def open_terabox_cookie_import_dialog(parent: QWidget | None = None) -> dict[str, Any]:
    """Fluxo recomendado Windows: importar cookie do Chrome sem WebEngine."""
    dialog = TeraboxCookieImportDialog(parent)
    code = dialog.exec()
    if dialog.wants_integrated_browser():
        return {"ok": False, "use_integrated": True}
    if code != QDialog.DialogCode.Accepted:
        return {"ok": False, "cancelled": True}
    cookie = dialog.cookie_result() or ""
    return {
        "ok": bool(cookie),
        "cookie": cookie,
        "ndus": cookie_contains_ndus(cookie),
        "source": "chrome_import",
        "hint": "Cookie importado do Chrome — pode testar a ligação.",
    }


class TeraboxBrowserDialog(QDialog):
    """Janela com WebEngine para login TeraBox e captura de cookie."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        auto_capture: bool = True,
        skip_startup_probe: bool | None = None,
    ) -> None:
        super().__init__(parent)
        if not _ensure_webengine_imported():
            raise RuntimeError("PyQt6-WebEngine indisponível")

        from PyQt6.QtWebEngineCore import QWebEngineProfile
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        import sys

        self._log = get_app_logger()
        self._auto_capture = auto_capture
        if skip_startup_probe is None:
            skip_startup_probe = sys.platform == "win32"
        self._skip_startup_probe = skip_startup_probe
        self.setWindowTitle("RDrive — Login TeraBox (integrado)")
        self.resize(1080, 760)
        self.setMinimumSize(800, 560)

        self._result_cookie: str | None = None
        self._cookies: dict[str, QNetworkCookie] = {}
        self._intercepted_cookie_pairs: dict[str, str] = {}
        self._on_main_page = False
        self._capture_in_flight = False
        self._load_ok = False
        self._load_started = False
        self._initial_url_loaded = False
        self._max_load_progress = 0
        self._load_failure_count = 0
        self._login_url_index = 0
        self._current_login_url = TERABOX_LOGIN_URL
        self._startup_probe_active = False

        self._auto_capture_timer = QTimer(self)
        self._auto_capture_timer.setSingleShot(True)
        self._auto_capture_timer.timeout.connect(self._on_auto_capture_debounced)

        self._blank_timeout_timer = QTimer(self)
        self._blank_timeout_timer.setSingleShot(True)
        self._blank_timeout_timer.timeout.connect(self._on_blank_or_probe_timeout)

        self._progress_stuck_timer = QTimer(self)
        self._progress_stuck_timer.setSingleShot(True)
        self._progress_stuck_timer.timeout.connect(self._on_progress_stuck)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        hint = QLabel(
            f"{INTEGRATED_BROWSER_BLANK_PT}\n\n"
            "Se a página abaixo carregar: faça login até «Meus ficheiros» — "
            "captura automática do cookie."
        )
        hint.setWordWrap(True)
        hint.setObjectName("teraboxBrowserHint")
        layout.addWidget(hint)

        self._manual_cookie_widget = QWidget(self)
        manual_layout = QVBoxLayout(self._manual_cookie_widget)
        manual_layout.setContentsMargins(0, 0, 0, 0)
        manual_layout.setSpacing(4)
        manual_hint = QLabel(MANUAL_COOKIE_FALLBACK_HINT_PT)
        manual_hint.setWordWrap(True)
        manual_layout.addWidget(manual_hint)
        manual_row = QHBoxLayout()
        self._manual_cookie_input = QPlainTextEdit()
        self._manual_cookie_input.setPlaceholderText("ndus=… ou Cookie: ndus=…")
        self._manual_cookie_input.setMaximumHeight(72)
        manual_row.addWidget(self._manual_cookie_input, 1)
        self._paste_cookie_btn = QPushButton("Usar cookie colado")
        self._paste_cookie_btn.clicked.connect(self._accept_pasted_cookie)
        manual_row.addWidget(self._paste_cookie_btn)
        self._import_cookie_btn = QPushButton("Importar cookies.txt")
        self._import_cookie_btn.setToolTip(
            "Exporte do Chrome com extensão (ex. «Get cookies.txt LOCALLY») "
            "enquanto estiver logado em terabox.com"
        )
        self._import_cookie_btn.clicked.connect(self._import_cookie_file)
        manual_row.addWidget(self._import_cookie_btn)
        manual_layout.addLayout(manual_row)
        self._manual_cookie_widget.setVisible(True)
        layout.addWidget(self._manual_cookie_widget)

        self._status_label = QLabel("A preparar navegador…")
        self._status_label.setWordWrap(True)
        self._status_label.setObjectName("teraboxBrowserStatus")
        layout.addWidget(self._status_label)

        toolbar = QHBoxLayout()
        self._url_label = QLabel(TERABOX_LOGIN_URL)
        self._url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        toolbar.addWidget(self._url_label, 1)

        self._reload_btn = QPushButton("Recarregar")
        self._reload_btn.setToolTip("Tentar carregar a página de login novamente")
        self._reload_btn.clicked.connect(self._reload_login_page)
        self._reload_btn.setVisible(False)
        toolbar.addWidget(self._reload_btn)

        self._open_system_btn = QPushButton("Abrir no browser do sistema")
        self._open_system_btn.setToolTip(
            "Abre terabox.com no browser predefinido se a página integrada ficar em branco. "
            "Após login, volte aqui — o perfil persistente pode capturar a sessão."
        )
        self._open_system_btn.clicked.connect(self._open_system_browser)
        self._open_system_btn.setVisible(False)
        toolbar.addWidget(self._open_system_btn)

        self._clear_cache_btn = QPushButton("Limpar cache integrado")
        self._clear_cache_btn.setToolTip(
            r"Apaga %APPDATA%\RDrive\terabox-browser\cache e tenta de novo"
        )
        self._clear_cache_btn.clicked.connect(self._clear_cache_and_reload)
        self._clear_cache_btn.setVisible(False)
        toolbar.addWidget(self._clear_cache_btn)

        self._open_main_btn = QPushButton("Abrir área principal")
        self._open_main_btn.setToolTip(TERABOX_MAIN_URL)
        self._open_main_btn.clicked.connect(self._load_main_page)
        toolbar.addWidget(self._open_main_btn)

        self._capture_btn = QPushButton("Capturar manualmente")
        self._capture_btn.setEnabled(False)
        self._capture_btn.setToolTip("Use só se a captura automática não correr")
        self._capture_btn.clicked.connect(lambda: self._capture_and_accept(auto=False))
        toolbar.addWidget(self._capture_btn)

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        toolbar.addWidget(cancel_btn)

        layout.addLayout(toolbar)

        storage = terabox_browser_storage_dir()
        self._profile = QWebEngineProfile(_PROFILE_NAME, self)
        self._profile.setPersistentStoragePath(str(storage))
        self._profile.setCachePath(str(storage / "cache"))
        configure_terabox_webengine_profile(self._profile)

        interceptor = _create_terabox_request_interceptor(
            self._on_intercepted_cookie_header,
            self._profile,
        )
        self._profile.setUrlRequestInterceptor(interceptor)

        self._page = TeraboxWebEnginePage.create(self._profile, self, self._log)
        configure_terabox_webengine_settings(self._page)
        self._view = QWebEngineView(self)
        self._view.setPage(self._page)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._devtools_blocker = _BlockDevToolsEventFilter(self)
        self._view.installEventFilter(self._devtools_blocker)
        self.installEventFilter(self._devtools_blocker)
        layout.addWidget(self._view, 1)

        cookie_store = self._profile.cookieStore()
        cookie_store.cookieAdded.connect(self._on_cookie_added)
        QTimer.singleShot(0, cookie_store.loadAllCookies)
        QTimer.singleShot(_SESSION_PROBE_MS, self._probe_existing_session)

        self._view.urlChanged.connect(self._on_url_changed)
        self._view.loadStarted.connect(self._on_load_started)
        self._view.loadProgress.connect(self._on_load_progress)
        self._view.loadFinished.connect(self._on_load_finished)

        session = diagnose_terabox_profile_session()
        if session.get("has_cookies") and not session.get("has_ndus"):
            self._set_status(SESSION_INCOMPLETE_NO_NDUS_PT, error=True)

        if self._skip_startup_probe:
            QTimer.singleShot(0, self._load_login_page)
        else:
            QTimer.singleShot(0, self._run_view_startup_probe)

    def _import_cookie_file(self) -> None:
        from PyQt6.QtWidgets import QFileDialog

        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Importar cookies TeraBox",
            "",
            "Cookies (*.txt);;Todos (*.*)",
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            QMessageBox.warning(self, "TeraBox", f"Não foi possível ler o ficheiro:\n{exc}")
            return
        pairs = parse_netscape_cookie_file(text)
        if pairs:
            header = build_cookie_header_from_pairs(pairs)
            self._manual_cookie_input.setPlainText(header)
        else:
            self._manual_cookie_input.setPlainText(text.strip())
        self._manual_cookie_widget.setVisible(True)
        self._accept_pasted_cookie()

    def _run_view_startup_probe(self) -> None:
        """Sonda renderização no perfil real antes de carregar terabox.com."""
        self._startup_probe_active = True
        self._set_status("A verificar motor WebEngine…")
        self._blank_timeout_timer.start(_WEBENGINE_RENDER_PROBE_MS)
        self._view.setHtml(_PROBE_HTML)

    def _on_startup_probe_timeout(self) -> None:
        if not getattr(self, "_startup_probe_active", False):
            return
        self._startup_probe_active = False
        self._show_webengine_inline_failure("timeout")

    def _finish_startup_probe(self, *, ok: bool, reason: str = "") -> None:
        if not getattr(self, "_startup_probe_active", False):
            return
        self._startup_probe_active = False
        self._disarm_blank_timeout()
        if ok:
            self._load_login_page()
            return
        self._show_webengine_inline_failure(reason)

    def _show_webengine_inline_failure(self, reason: str = "") -> None:
        self._log.warning(
            f"[WEBUI] TeraBox: WebEngine não renderiza ({reason or 'probe'})",
            module="webui",
        )
        self._show_recovery_actions(True)
        self._manual_cookie_widget.setVisible(True)
        self._set_status(
            f"{WEBENGINE_BROKEN_MESSAGE_PT} "
            "Use «Abrir no browser do sistema» ou execute scripts\\verify_webengine.ps1.",
            error=True,
        )
        QTimer.singleShot(0, lambda: show_webengine_broken_dialog(self))

    def cookie_result(self) -> str | None:
        return self._result_cookie

    def _set_status(self, text: str, *, error: bool = False) -> None:
        self._status_label.setText(text)
        self._status_label.setProperty("error", error)
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)

    def _show_recovery_actions(self, visible: bool) -> None:
        self._reload_btn.setVisible(visible)
        self._open_system_btn.setVisible(visible)
        self._clear_cache_btn.setVisible(visible)
        self._manual_cookie_widget.setVisible(visible)
        if visible:
            self._open_system_btn.setStyleSheet("font-weight: bold;")

    def _arm_blank_timeout(self) -> None:
        self._blank_timeout_timer.start(_BLANK_PAGE_TIMEOUT_MS)

    def _disarm_blank_timeout(self) -> None:
        self._blank_timeout_timer.stop()

    def _arm_progress_watchdog(self) -> None:
        self._max_load_progress = 0
        self._progress_stuck_timer.start(_PROGRESS_STUCK_MS)

    def _disarm_progress_watchdog(self) -> None:
        self._progress_stuck_timer.stop()

    def _resolve_login_url(self, index: int | None = None) -> str:
        idx = self._login_url_index if index is None else index
        urls = TERABOX_LOGIN_URL_FALLBACKS
        if idx < 0:
            idx = 0
        if idx >= len(urls):
            idx = len(urls) - 1
        return urls[idx]

    def _load_login_page(self, *, next_fallback: bool = False) -> None:
        self._disarm_blank_timeout()
        self._disarm_progress_watchdog()
        self._load_ok = False
        self._load_started = False
        self._max_load_progress = 0

        if next_fallback and self._login_url_index < len(TERABOX_LOGIN_URL_FALLBACKS) - 1:
            self._login_url_index += 1

        self._current_login_url = self._resolve_login_url()
        self._url_label.setText(self._current_login_url)
        self._show_recovery_actions(False)
        self._set_status("A carregar página de login…")
        self._view.load(QUrl(self._current_login_url))
        self._arm_blank_timeout()
        self._arm_progress_watchdog()

    def _reload_login_page(self) -> None:
        self._log.info("[WEBUI] TeraBox: recarregar página de login", module="webui")
        if self._load_failure_count >= 1:
            clear_terabox_browser_storage(cache_only=True)
        self._load_login_page()

    def _clear_cache_and_reload(self) -> None:
        clear_terabox_browser_storage(cache_only=True)
        self._log.info("[WEBUI] TeraBox: cache integrado limpo", module="webui")
        self._load_failure_count = 0
        self._login_url_index = 0
        self._load_login_page()

    def _open_system_browser(self) -> None:
        url = open_terabox_login()
        self._log.info(f"[WEBUI] TeraBox: browser do sistema ({url})", module="webui")
        self._show_recovery_actions(True)
        self._set_status(SYSTEM_BROWSER_FALLBACK_HINT_PT, error=False)

    def _handle_load_failure(self, message: str, *, reason: str = "") -> None:
        self._load_failure_count += 1
        self._disarm_blank_timeout()
        self._disarm_progress_watchdog()
        self._show_recovery_actions(True)
        self._set_status(message, error=True)
        if reason:
            self._log.warning(
                f"[WEBUI] TeraBox: falha de carregamento ({reason}) "
                f"tentativa={self._load_failure_count}",
                module="webui",
            )

        if self._load_failure_count == 1 and self._login_url_index < len(TERABOX_LOGIN_URL_FALLBACKS) - 1:
            self._log.info(
                f"[WEBUI] TeraBox: a tentar URL alternativa "
                f"{self._resolve_login_url(self._login_url_index + 1)}",
                module="webui",
            )
            QTimer.singleShot(400, lambda: self._load_login_page(next_fallback=True))
            return

        if self._load_failure_count >= _MAX_LOAD_FAILURES_BEFORE_SYSTEM_BROWSER:
            clear_terabox_browser_storage(cache_only=True)
            self._open_system_browser()

    def _accept_pasted_cookie(self) -> None:
        raw = self._manual_cookie_input.toPlainText().strip()
        if not raw:
            QMessageBox.warning(self, "TeraBox", "Cole o cookie (valor ndus) no campo acima.")
            return
        ok, msg = validate_terabox_cookie(raw)
        if not ok:
            QMessageBox.warning(self, "TeraBox", msg or "Cookie inválido.")
            self._set_status(msg or "Cookie inválido.", error=True)
            return
        self._result_cookie = raw.strip()
        self._log.info(
            "[WEBUI] TeraBox: cookie colado manualmente (ndus presente)",
            module="webui",
        )
        self._set_status("Cookie colado — a fechar…")
        QTimer.singleShot(200, self.accept)

    def _on_intercepted_cookie_header(self, header: str) -> None:
        """Fallback: cookies enviados em pedidos HTTP (inclui httpOnly ausentes do store)."""
        pairs = parse_cookie_header_pairs(header)
        if not pairs:
            return
        changed = False
        for name, value in pairs.items():
            if self._intercepted_cookie_pairs.get(name) != value:
                self._intercepted_cookie_pairs[name] = value
                changed = True
        if changed:
            self._update_capture_state()

    def _on_cookie_added(self, cookie: QNetworkCookie) -> None:
        domain = ""
        if cookie.domain():
            domain = bytes(cookie.domain()).decode("utf-8", errors="replace")
        if "terabox" not in domain.lower():
            return
        name = bytes(cookie.name()).decode("utf-8", errors="replace")
        path = bytes(cookie.path()).decode("utf-8", errors="replace") if cookie.path() else "/"
        key = f"{domain}|{path}|{name}"
        self._cookies[key] = cookie
        self._update_capture_state()

    def _on_url_changed(self, url: QUrl) -> None:
        text = url.toString()
        self._url_label.setText(text)
        self._on_main_page = "/main" in urlparse(text).path.lower()
        self._update_capture_state()

    def _on_blank_or_probe_timeout(self) -> None:
        if getattr(self, "_startup_probe_active", False):
            self._on_startup_probe_timeout()
            return
        self._on_blank_page_timeout()

    def _on_load_started(self) -> None:
        if getattr(self, "_startup_probe_active", False):
            return
        self._load_started = True
        self._load_ok = False
        self._arm_blank_timeout()
        self._arm_progress_watchdog()
        url = self._view.url().toString() or self._current_login_url
        if "/main" in urlparse(url).path.lower():
            self._set_status("A carregar «Meus ficheiros»…")
        else:
            self._set_status("A carregar página de login…")

    def _on_load_progress(self, progress: int) -> None:
        if progress > self._max_load_progress:
            self._max_load_progress = progress
        if progress > 0:
            self._disarm_progress_watchdog()
            if progress < 100:
                self._arm_progress_watchdog()
        if progress <= 0 or progress >= 100:
            return
        url = self._view.url().toString()
        if "/main" in urlparse(url).path.lower():
            self._set_status(f"A carregar «Meus ficheiros»… ({progress}%)")
        else:
            self._set_status(f"A carregar página de login… ({progress}%)")

    def _on_load_finished(self, ok: bool) -> None:
        if getattr(self, "_startup_probe_active", False):
            self._disarm_blank_timeout()
            if not ok:
                self._finish_startup_probe(ok=False, reason="load_failed")
                return
            QTimer.singleShot(
                350,
                lambda: self._page.runJavaScript(_PROBE_JS, self._on_startup_probe_js),
            )
            return
        self._disarm_blank_timeout()
        self._disarm_progress_watchdog()
        self._load_ok = ok
        self._initial_url_loaded = True

        if not ok:
            self._handle_load_failure(
                "Falha ao carregar a página — verifique a ligação e clique «Recarregar» "
                "ou «Abrir no browser do sistema».",
                reason="load_finished_false",
            )
            return

        self._show_recovery_actions(False)
        url = self._view.url().toString()
        self._on_main_page = "/main" in urlparse(url).path.lower()
        if self._on_main_page:
            self._set_status("«Meus ficheiros» carregado — complete o login se necessário.")
        else:
            self._set_status("Faça login na sua conta TeraBox.")
        self._update_capture_state()
        QTimer.singleShot(2000, self._probe_page_content)

    def _on_startup_probe_js(self, has_content: object) -> None:
        self._finish_startup_probe(ok=has_content is True, reason="blank_dom")

    def _probe_page_content(self) -> None:
        """Detecta SPA em branco (HTTP 200 mas sem DOM útil — comum com UA bloqueado)."""
        if self._result_cookie or self._capture_in_flight or not self._load_ok:
            return
        self._page.runJavaScript(
            "(document.body && document.body.innerText.trim().length > 40) || "
            "document.querySelector('input, button, form') !== null",
            self._on_content_probe_result,
        )

    def _on_content_probe_result(self, has_content: object) -> None:
        if self._result_cookie or self._capture_in_flight:
            return
        if has_content is True:
            return
        self._handle_load_failure(
            "A página ficou em branco — clique «Recarregar» ou use "
            "«Abrir no browser do sistema».",
            reason="empty_dom",
        )

    def _on_blank_page_timeout(self) -> None:
        if self._result_cookie or self._capture_in_flight:
            return
        if self._load_ok:
            return
        header = self._build_cookie_header().strip()
        if header and cookie_contains_ndus(header):
            ok, _msg = validate_terabox_cookie(header)
            if ok:
                self._capture_and_accept(auto=True)
                return
        self._handle_load_failure(
            "A página demorou demasiado ou ficou em branco — clique «Recarregar» "
            "ou use «Abrir no browser do sistema».",
            reason="blank_timeout",
        )

    def _on_progress_stuck(self) -> None:
        if self._result_cookie or self._capture_in_flight or self._load_ok:
            return
        if self._max_load_progress > 0:
            return
        self._handle_load_failure(
            "WebEngine não conseguiu carregar — use «Abrir no browser do sistema» "
            "e volte aqui, ou cole um cookie exportado abaixo.",
            reason="progress_stuck_zero",
        )

    def _probe_existing_session(self) -> None:
        """Perfil persistente pode já ter sessão — valida sem saltar para /main."""
        header = self._build_cookie_header()
        if not cookie_contains_ndus(header):
            if self._initial_url_loaded and self._load_ok:
                self._set_status("Faça login na sua conta TeraBox.")
            elif not self._load_started:
                self._set_status("A carregar página de login…")
            self._update_capture_state()
            return

        ok, msg = validate_terabox_cookie(header)
        if not ok:
            self._set_status(msg or "Sessão incompleta — faça login novamente.", error=True)
            self._update_capture_state()
            return

        current = self._view.url().toString()
        on_main = "/main" in urlparse(current).path.lower()
        if on_main:
            self._set_status("Sessão guardada detetada — a capturar…")
        else:
            self._set_status(
                "Sessão guardada detetada — pode capturar ou abrir «Meus ficheiros»."
            )
        self._schedule_auto_capture()
        self._update_capture_state()

    def _load_main_page(self) -> None:
        self._set_status("A carregar «Meus ficheiros»…")
        self._view.load(QUrl(TERABOX_MAIN_URL))

    def _build_cookie_header(self) -> str:
        pairs: dict[str, str] = dict(self._intercepted_cookie_pairs)
        for cookie in self._cookies.values():
            name = bytes(cookie.name()).decode("utf-8", errors="replace")
            value = bytes(cookie.value()).decode("utf-8", errors="replace")
            if name:
                pairs[name] = value
        return build_cookie_header_from_pairs(pairs)

    def _update_capture_state(self) -> None:
        if self._result_cookie or self._capture_in_flight:
            return

        header = self._build_cookie_header().strip()
        has_ndus = cookie_contains_ndus(header)
        url = self._view.url().toString()
        on_main = "/main" in urlparse(url).path.lower() or self._on_main_page
        self._on_main_page = on_main

        can_capture = on_main or has_ndus
        self._capture_btn.setEnabled(can_capture)

        if on_main and has_ndus:
            ok, msg = validate_terabox_cookie(header)
            if ok:
                if self._auto_capture:
                    self._set_status("Sessão detetada — a capturar…")
                    self._schedule_auto_capture()
                else:
                    self._set_status("Sessão detetada — clique «Capturar manualmente».")
            else:
                self._set_status(msg or "Cookie incompleto — complete o login.", error=True)
        elif has_ndus:
            self._set_status(
                "Sessão detetada — clique «Capturar manualmente» ou abra «Meus ficheiros»."
            )
        elif on_main:
            self._set_status("Página principal — a aguardar cookies de sessão…")
        elif self._status_label.text().startswith("A preparar"):
            self._set_status("A carregar página de login…")

    def _schedule_auto_capture(self) -> None:
        if not self._auto_capture or self._result_cookie or self._capture_in_flight:
            return
        header = self._build_cookie_header()
        ok, _ = validate_terabox_cookie(header)
        if not ok:
            return
        if not self._auto_capture_timer.isActive():
            self._auto_capture_timer.start(_AUTO_CAPTURE_DEBOUNCE_MS)

    def _on_auto_capture_debounced(self) -> None:
        self._capture_and_accept(auto=True)

    def _capture_and_accept(self, *, auto: bool = False) -> None:
        if self._capture_in_flight or self._result_cookie:
            return
        self._capture_in_flight = True
        self._auto_capture_timer.stop()
        self._disarm_blank_timeout()
        self._disarm_progress_watchdog()

        header = self._build_cookie_header().strip()
        if not header:
            self._capture_in_flight = False
            self._set_status(
                "Ainda não há cookies TeraBox — faça login e aguarde «Meus ficheiros».",
                error=True,
            )
            if not auto:
                QMessageBox.warning(
                    self,
                    "TeraBox",
                    "Ainda não há cookies TeraBox neste navegador.\n\n"
                    "Faça login no site e aguarde carregar «Meus ficheiros».",
                )
            return

        ok, msg = validate_terabox_cookie(header)
        if not ok:
            self._capture_in_flight = False
            self._set_status(msg or "Cookie inválido.", error=True)
            if not auto:
                QMessageBox.warning(self, "TeraBox", msg)
            return

        self._result_cookie = header
        self._log.info(
            "[WEBUI] TeraBox: cookie capturado pelo navegador integrado (ndus presente)",
            module="webui",
        )
        if auto:
            self._set_status("Cookie capturado — a fechar…")
            QTimer.singleShot(350, self.accept)
        else:
            self.accept()


def probe_terabox_cookie_from_profile(*, timeout_ms: int = 2500) -> dict[str, Any]:
    """Lê cookies do perfil persistente sem abrir o diálogo (requer QApplication)."""
    if not webengine_import_ok():
        return {"ok": False, "error": "webengine_import_failed"}
    from PyQt6.QtWebEngineCore import QWebEngineProfile

    collected: dict[str, QNetworkCookie] = {}

    def _on_cookie_added(cookie: QNetworkCookie) -> None:
        domain = ""
        if cookie.domain():
            domain = bytes(cookie.domain()).decode("utf-8", errors="replace")
        if "terabox" not in domain.lower():
            return
        name = bytes(cookie.name()).decode("utf-8", errors="replace")
        path = bytes(cookie.path()).decode("utf-8", errors="replace") if cookie.path() else "/"
        collected[f"{domain}|{path}|{name}"] = cookie

    storage = terabox_browser_storage_dir()
    profile = QWebEngineProfile(_PROFILE_NAME)
    profile.setPersistentStoragePath(str(storage))
    profile.setCachePath(str(storage / "cache"))
    configure_terabox_webengine_profile(profile)

    store = profile.cookieStore()
    store.cookieAdded.connect(_on_cookie_added)
    store.loadAllCookies()

    loop = QEventLoop()
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()

    pairs: dict[str, str] = {}
    for cookie in collected.values():
        name = bytes(cookie.name()).decode("utf-8", errors="replace")
        value = bytes(cookie.value()).decode("utf-8", errors="replace")
        if name:
            pairs[name] = value
    if not pairs:
        pairs = read_terabox_cookie_pairs_from_sqlite()
    header = build_cookie_header_from_pairs(pairs)
    if not header:
        return {"ok": False, "error": "no_terabox_cookies", "cookie": ""}
    if not cookie_contains_ndus(header):
        return {
            "ok": False,
            "error": "session_incomplete_no_ndus",
            "cookie": header,
            "ndus": False,
            "hint": SESSION_INCOMPLETE_NO_NDUS_PT,
            "profile_names": sorted(pairs.keys()),
        }
    ok, msg = validate_terabox_cookie(header)
    if not ok:
        return {"ok": False, "error": msg or "invalid_cookie", "cookie": header, "ndus": False}
    return {
        "ok": True,
        "cookie": header,
        "ndus": True,
        "source": "persistent_profile",
        "hint": "Sessão lida do perfil integrado RDrive (sem novo login).",
    }


def capture_terabox_cookie_via_browser(
    parent: QWidget | None = None,
    *,
    auto_capture: bool = True,
    prefer_integrated: bool = False,
) -> dict[str, Any]:
    """Abre o diálogo e devolve ``{ok, cookie, cancelled, on_main, ...}``."""
    import sys

    if sys.platform == "win32" and not prefer_integrated:
        import_flow = open_terabox_cookie_import_dialog(parent)
        if import_flow.get("ok"):
            return import_flow
        if import_flow.get("cancelled") and not import_flow.get("use_integrated"):
            return {"ok": False, "cancelled": True}
        if not import_flow.get("use_integrated"):
            return import_flow
    status = get_webengine_status(probe_render=True)
    if not status["import_ok"]:
        show_webengine_broken_dialog(parent)
        return webengine_broken_result(reason="import_failed")
    if not status["binaries_ok"]:
        show_webengine_broken_dialog(parent)
        return webengine_broken_result(reason="binaries_missing")

    from PyQt6.QtWidgets import QApplication

    if QApplication.instance() is not None:
        stored = probe_terabox_cookie_from_profile()
        if stored.get("ok") and stored.get("cookie"):
            return {
                **stored,
                "cancelled": False,
                "on_main": True,
                "main_url": TERABOX_MAIN_URL,
                "auto_captured": True,
            }

    dialog = TeraboxBrowserDialog(parent, auto_capture=auto_capture)
    code = dialog.exec()
    if code != QDialog.DialogCode.Accepted:
        return {"ok": False, "cancelled": True}

    cookie = dialog.cookie_result() or ""
    on_main = dialog._on_main_page  # noqa: SLF001 — metadado útil para UI
    result = {
        "ok": bool(cookie),
        "cookie": cookie,
        "ndus": cookie_contains_ndus(cookie),
        "on_main": on_main,
        "main_url": TERABOX_MAIN_URL,
        "hint": "Cookie capturado automaticamente — pode testar a ligação.",
        "auto_captured": auto_capture,
    }
    return result
