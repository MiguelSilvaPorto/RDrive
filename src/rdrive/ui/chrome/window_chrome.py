from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from PyQt6.QtCore import QAbstractNativeEventFilter, QPoint, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QConicalGradient, QPainter, QPen
from rdrive.ui.foundation.text_selection import disable_label_text_selection

from PyQt6.QtWidgets import (
    QBoxLayout,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from rdrive.ui.foundation.app_icon import apply_window_icon
from rdrive.ui.chrome.theme import (
    CHROME_TOKENS,
    THEME_BG,
    TOOLBAR_MIN_HEIGHT,
    apply_dark_title_bar,
    apply_windows_round_corners,
)

if TYPE_CHECKING:
    from ctypes import c_void_p

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32

    _GWL_STYLE = -16
    _WS_THICKFRAME = 0x00040000
    _WS_CAPTION = 0x00C00000
    _WS_SYSMENU = 0x00080000
    _WS_MINIMIZEBOX = 0x00020000
    _WS_MAXIMIZEBOX = 0x00010000

    _WM_NCHITTEST = 0x0084
    _HTCAPTION = 2
    _HTLEFT = 10
    _HTRIGHT = 11
    _HTTOP = 12
    _HTTOPLEFT = 13
    _HTTOPRIGHT = 14
    _HTBOTTOM = 15
    _HTBOTTOMLEFT = 16
    _HTBOTTOMRIGHT = 17


class _TitleBarButton(QPushButton):
    def __init__(self, label: str, object_name: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setObjectName(object_name)
        self.setFixedSize(40, 28)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)


class CustomTitleBar(QWidget):
    """Minimal drag region with window controls (Windows frameless)."""

    def __init__(self, window: QWidget, title: str) -> None:
        super().__init__(window)
        self._window = window
        self._drag_origin: QPoint | None = None
        self.setObjectName("customTitleBar")
        self.setFixedHeight(int(CHROME_TOKENS["title_bar_height"]))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 6, 0)
        layout.setSpacing(6)

        # Icon only via setWindowIcon on the native caption (WS_CAPTION); no duplicate here.
        self._title_label = QLabel(title)
        self._title_label.setObjectName("customTitleLabel")
        disable_label_text_selection(self._title_label)
        layout.addWidget(self._title_label)
        layout.addStretch(1)

        self._min_button = _TitleBarButton("−", "titleBarButtonMin")
        self._max_button = _TitleBarButton("□", "titleBarButtonMax")
        self._close_button = _TitleBarButton("×", "titleBarButtonClose")
        self._min_button.clicked.connect(window.showMinimized)
        self._max_button.clicked.connect(self._toggle_maximize)
        self._close_button.clicked.connect(window.close)
        layout.addWidget(self._min_button)
        layout.addWidget(self._max_button)
        layout.addWidget(self._close_button)

    def set_title(self, title: str) -> None:
        self._title_label.setText(title)

    def _toggle_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
            self._max_button.setText("□")
        else:
            self._window.showMaximized()
            self._max_button.setText("❐")

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            target = self.childAt(event.position().toPoint())
            if isinstance(target, QPushButton):
                super().mousePressEvent(event)
                return
            self._drag_origin = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if self._window.isMaximized():
                self._window.showNormal()
                self._max_button.setText("□")
            self._window.move(event.globalPosition().toPoint() - self._drag_origin)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class _BorderGlowHost(QWidget):
    """Shell that paints the animated conical gradient perimeter and inner surface."""

    def __init__(self, parent: QWidget | None = None, *, animate: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("infiniteBorderHost")
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(int(CHROME_TOKENS["border_anim_ms"]))
        self._timer.timeout.connect(self._advance_phase)
        self._animation_disabled = not bool(animate)
        if not self._animation_disabled:
            self._timer.start()

    def set_animation_paused(self, paused: bool) -> None:
        """Pausa o repaint contínuo da borda (ex.: janela minimizada)."""
        if paused:
            self._timer.stop()
            return
        if self._animation_disabled:
            return
        if not self._timer.isActive():
            self._timer.start()

    def set_animation_enabled(self, enabled: bool) -> None:
        """Liga/desliga permanentemente a animação (modo leve / preferência do utilizador)."""
        self._animation_disabled = not bool(enabled)
        if self._animation_disabled:
            self._timer.stop()
        elif not self._timer.isActive():
            self._timer.start()

    def _advance_phase(self) -> None:
        self._phase = (self._phase + float(CHROME_TOKENS["border_anim_step"])) % 360.0
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        border = float(CHROME_TOKENS["border_width"])
        radius = float(CHROME_TOKENS["window_radius"])
        outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        inner = outer.adjusted(border, border, -border, -border)
        inner_radius = max(0.0, radius - border)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(THEME_BG))
        painter.drawRoundedRect(inner, inner_radius, inner_radius)

        center = outer.center()
        gradient = QConicalGradient(center, self._phase)
        gradient.setColorAt(0.0, QColor(str(CHROME_TOKENS["border_glow_a"])))
        gradient.setColorAt(0.35, QColor(str(CHROME_TOKENS["border_glow_b"])))
        gradient.setColorAt(0.65, QColor(str(CHROME_TOKENS["border_glow_c"])))
        gradient.setColorAt(1.0, QColor(str(CHROME_TOKENS["border_glow_a"])))

        pen = QPen(QBrush(gradient), border * 2.0)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(outer, radius, radius)


def _transfer_layout_items(source: QLayout, dest: QVBoxLayout) -> None:
    dest.setContentsMargins(source.contentsMargins())
    dest.setSpacing(source.spacing())
    while source.count():
        stretch = source.stretch(0) if isinstance(source, QBoxLayout) else 0
        item = source.takeAt(0)
        if item is None:
            continue
        if item.widget() is not None:
            dest.addWidget(item.widget(), stretch)
        elif item.layout() is not None:
            dest.addLayout(item.layout())
        elif item.spacerItem() is not None:
            dest.addItem(item.spacerItem())


class InfiniteBorderFrame:
    """Shared infinite-border chrome for top-level windows (main window and dialogs)."""

    def __init__(self) -> None:
        self._chrome_ready = False
        self._title_bar: CustomTitleBar | None = None
        self._border_host: _BorderGlowHost | None = None
        self._native_filter: _WindowsChromeNativeFilter | None = None

    def _initial_border_animate(self) -> bool:
        """Subclasses substituem para arrancar com a animação já desligada (modo leve)."""
        return True

    def finalize_infinite_border_chrome(self) -> None:
        if self._chrome_ready:
            return
        apply_window_icon(self)  # type: ignore[arg-type]
        if sys.platform == "win32":
            self._install_windows_chrome()
        else:
            self._install_linux_fallback()
        self._chrome_ready = True

    def setWindowTitle(self, title: str) -> None:  # noqa: N802 — Qt API
        QWidget.setWindowTitle(self, title)  # type: ignore[arg-type]
        if self._title_bar is not None:
            self._title_bar.set_title(title)

    def _toolbar_should_be_visible(self) -> bool:
        return True

    def set_border_animation_paused(self, paused: bool) -> None:
        """Pausa a animação da borda para poupar CPU/GPU quando a janela está em segundo plano."""
        host = getattr(self, "_border_host", None)
        if host is not None:
            host.set_animation_paused(paused)

    def set_border_animation_enabled(self, enabled: bool) -> None:
        """Liga/desliga permanentemente a animação (preferência «Modo leve»)."""
        host = getattr(self, "_border_host", None)
        if host is not None:
            host.set_animation_enabled(enabled)

    def refresh_chrome_layout(self) -> None:
        if not self._chrome_ready:
            return
        toolbar = self._resolve_main_toolbar()
        if toolbar is not None:
            parent = toolbar.parent()
            if isinstance(parent, QWidget):
                self._prepare_toolbar_for_chrome(toolbar, parent)
            sync_visibility = getattr(self, "_sync_main_toolbar_visibility", None)
            if callable(sync_visibility):
                sync_visibility()
            else:
                visible = self._toolbar_should_be_visible()
                toolbar.setVisible(visible)
                if visible:
                    toolbar.show()
                toolbar.updateGeometry()
        if self._border_host is not None:
            self._border_host.updateGeometry()
        self.update()  # type: ignore[attr-defined]

    def showEvent(self, event) -> None:  # type: ignore[override]
        QWidget.showEvent(self, event)  # type: ignore[arg-type]
        if sys.platform == "win32" and self._chrome_ready:
            self._apply_windows_frame_styles()
            self._install_native_filter()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._remove_native_filter()
        QWidget.closeEvent(self, event)  # type: ignore[arg-type]

    def changeEvent(self, event) -> None:  # type: ignore[override]
        QWidget.changeEvent(self, event)  # type: ignore[arg-type]
        if (
            sys.platform == "win32"
            and self._title_bar is not None
            and event.type() == event.Type.WindowStateChange
        ):
            self._title_bar._max_button.setText("❐" if self.isMaximized() else "□")  # type: ignore[attr-defined]

    def _install_native_filter(self) -> None:
        if sys.platform != "win32" or not self._chrome_ready or self._native_filter is not None:
            return
        from PyQt6.QtWidgets import QApplication

        qt_app = QApplication.instance()
        if qt_app is None:
            return
        self._native_filter = _WindowsChromeNativeFilter(self)
        try:
            self._native_filter._hwnd = int(self.winId())  # type: ignore[attr-defined]
        except Exception:
            self._native_filter._hwnd = 0
        qt_app.installNativeEventFilter(self._native_filter)

    def _remove_native_filter(self) -> None:
        if self._native_filter is None:
            return
        from PyQt6.QtWidgets import QApplication

        qt_app = QApplication.instance()
        if qt_app is not None:
            qt_app.removeNativeEventFilter(self._native_filter)
        self._native_filter = None

    def _resolve_main_toolbar(self) -> QToolBar | None:
        stored = getattr(self, "_main_toolbar", None)
        if isinstance(stored, QToolBar):
            return stored
        return self.findChild(QToolBar, "mainToolBar")  # type: ignore[attr-defined]

    def _prepare_toolbar_for_chrome(self, toolbar: QToolBar, parent: QWidget) -> None:
        if isinstance(self, QMainWindow) and self.toolBarArea(toolbar) != Qt.ToolBarArea.NoToolBarArea:
            self.removeToolBar(toolbar)
        toolbar.setParent(parent)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setOrientation(Qt.Orientation.Horizontal)
        visible = self._toolbar_should_be_visible()
        toolbar.setVisible(visible)
        toolbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        toolbar.setMinimumHeight(TOOLBAR_MIN_HEIGHT)
        toolbar.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def _extract_dialog_content(self) -> QWidget:
        old_layout = self.layout()  # type: ignore[attr-defined]
        content = QWidget()
        new_layout = QVBoxLayout(content)
        if old_layout is not None:
            _transfer_layout_items(old_layout, new_layout)
            orphan = QWidget()
            orphan.setLayout(old_layout)
        return content

    def _acquire_content_for_chrome(self) -> tuple[QWidget | None, QToolBar | None]:
        raise NotImplementedError

    def _attach_chrome_host(self, border_host: _BorderGlowHost) -> None:
        raise NotImplementedError

    def _install_windows_chrome(self) -> None:
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)  # type: ignore[attr-defined]
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)  # type: ignore[attr-defined]

        content, toolbar = self._acquire_content_for_chrome()
        if content is None:
            content = QWidget()

        self._border_host = _BorderGlowHost(animate=self._initial_border_animate())
        self._title_bar = CustomTitleBar(self, self.windowTitle())  # type: ignore[arg-type]

        shell_layout = QVBoxLayout(self._border_host)
        shell_layout.setContentsMargins(
            int(CHROME_TOKENS["chrome_padding"]),
            int(CHROME_TOKENS["chrome_padding"]),
            int(CHROME_TOKENS["chrome_padding"]),
            int(CHROME_TOKENS["chrome_padding"]),
        )
        shell_layout.setSpacing(0)

        inner = QWidget()
        inner.setObjectName("infiniteBorderInner")
        inner_layout = QVBoxLayout(inner)
        # Inset content so rounded window corners do not clip side navigation.
        content_inset = max(6, int(CHROME_TOKENS["window_radius"]) // 2)
        inner_layout.setContentsMargins(content_inset, 0, content_inset, content_inset)
        inner_layout.setSpacing(0)
        inner_layout.addWidget(self._title_bar)
        if toolbar is not None:
            self._prepare_toolbar_for_chrome(toolbar, inner)
            if isinstance(self, InfiniteBorderMainWindow):
                self._chrome_toolbar = toolbar  # type: ignore[attr-defined]
            inner_layout.addWidget(toolbar)
        inner_layout.addWidget(content, 1)

        shell_layout.addWidget(inner, 1)
        self._attach_chrome_host(self._border_host)

        sync_visibility = getattr(self, "_sync_main_toolbar_visibility", None)
        if callable(sync_visibility):
            sync_visibility()

    def _install_linux_fallback(self) -> None:
        radius = int(CHROME_TOKENS["window_radius"])
        glow = str(CHROME_TOKENS["border_glow_b"])
        selector = "QDialog" if isinstance(self, QDialog) else "QMainWindow"
        self.setStyleSheet(  # type: ignore[attr-defined]
            self.styleSheet()  # type: ignore[attr-defined]
            + f"""
            {selector} {{
                border: 1px solid {glow};
                border-radius: {radius}px;
            }}
            """
        )

    def _apply_windows_frame_styles(self) -> None:
        apply_dark_title_bar(self)  # type: ignore[arg-type]
        apply_windows_round_corners(self)  # type: ignore[arg-type]
        try:
            hwnd = int(self.winId())  # type: ignore[attr-defined]
            style = _user32.GetWindowLongW(hwnd, _GWL_STYLE)
            style |= _WS_THICKFRAME | _WS_CAPTION | _WS_SYSMENU | _WS_MINIMIZEBOX | _WS_MAXIMIZEBOX
            _user32.SetWindowLongW(hwnd, _GWL_STYLE, style)
        except Exception:
            pass

    def _windows_native_hit_test(self, message: c_void_p) -> tuple[bool, int]:
        class _POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        class _MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt", _POINT),
            ]

        msg = _MSG.from_address(int(message))
        if msg.message != _WM_NCHITTEST:
            return False, 0

        x = ctypes.c_int16(msg.lParam & 0xFFFF).value
        y = ctypes.c_int16((msg.lParam >> 16) & 0xFFFF).value
        global_pos = QPoint(x, y)
        local = self.mapFromGlobal(global_pos)  # type: ignore[attr-defined]
        width, height = self.width(), self.height()  # type: ignore[attr-defined]
        border = int(CHROME_TOKENS["resize_border"])

        if not self.rect().contains(local):  # type: ignore[attr-defined]
            return False, 0

        on_left = local.x() <= border
        on_right = local.x() >= width - border
        on_top = local.y() <= border
        on_bottom = local.y() >= height - border

        if on_top and on_left:
            return True, _HTTOPLEFT
        if on_top and on_right:
            return True, _HTTOPRIGHT
        if on_bottom and on_left:
            return True, _HTBOTTOMLEFT
        if on_bottom and on_right:
            return True, _HTBOTTOMRIGHT
        if on_left:
            return True, _HTLEFT
        if on_right:
            return True, _HTRIGHT
        if on_top:
            return True, _HTTOP
        if on_bottom:
            return True, _HTBOTTOM

        if self._title_bar is not None:
            title_local = self._title_bar.mapFromGlobal(global_pos)
            if self._title_bar.rect().contains(title_local):
                child = self._title_bar.childAt(title_local)
                if not isinstance(child, QPushButton):
                    return True, _HTCAPTION

        return False, 0


class _WindowsChromeNativeFilter(QAbstractNativeEventFilter):
    """Handle WM_NCHITTEST without overriding nativeEvent (PyQt6/Win crash)."""

    def __init__(self, window: InfiniteBorderFrame) -> None:
        super().__init__()
        self._window = window
        self._hwnd = 0

    def nativeEventFilter(self, eventType: bytes | bytearray | memoryview, message: int) -> tuple[bool, int]:  # type: ignore[override]
        if sys.platform != "win32" or not self._window._chrome_ready:
            return False, 0
        if eventType != b"windows_generic_MSG":
            return False, 0
        try:
            class _MSG(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM),
                    ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD),
                    ("pt", wintypes.POINT),
                ]

            msg = _MSG.from_address(int(message))
        except Exception:
            return False, 0
        if self._hwnd and msg.hwnd != self._hwnd:
            return False, 0
        handled, code = self._window._windows_native_hit_test(message)
        if handled:
            return True, code
        return False, 0


class InfiniteBorderMainWindow(InfiniteBorderFrame, QMainWindow):
    """QMainWindow base with frameless infinite-border chrome on Windows."""

    def __init__(self, *args, **kwargs) -> None:
        InfiniteBorderFrame.__init__(self)
        QMainWindow.__init__(self, *args, **kwargs)
        self._chrome_toolbar: QToolBar | None = None

    def _acquire_content_for_chrome(self) -> tuple[QWidget | None, QToolBar | None]:
        toolbar = self._resolve_main_toolbar()
        return self.takeCentralWidget(), toolbar

    def _attach_chrome_host(self, border_host: _BorderGlowHost) -> None:
        self.setCentralWidget(border_host)


class InfiniteBorderDialog(InfiniteBorderFrame, QDialog):
    """QDialog base with frameless infinite-border chrome on Windows."""

    def __init__(self, *args, **kwargs) -> None:
        InfiniteBorderFrame.__init__(self)
        QDialog.__init__(self, *args, **kwargs)

    def finalize_infinite_border_chrome(self) -> None:
        self.setSizeGripEnabled(False)
        super().finalize_infinite_border_chrome()

    def _acquire_content_for_chrome(self) -> tuple[QWidget | None, QToolBar | None]:
        return self._extract_dialog_content(), None

    def _attach_chrome_host(self, border_host: _BorderGlowHost) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(border_host)
