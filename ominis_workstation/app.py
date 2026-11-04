"""Application bootstrap for the Ominis investigation workstation."""

from __future__ import annotations

import ctypes
import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QMessageBox

from ominis_src import __version__ as engine_version

from . import backend, theme
from .main_window import APP_NAME, APP_VERSION, ORG_NAME, MainWindow


def resource_path(name: str) -> Path:
    """Resolve a bundled resource both from source and from a frozen exe."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "ominis_workstation" / "assets" / name
    return Path(__file__).resolve().parent / "assets" / name


def _configure_windows() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "WinterGate.OminisWorkstation.1")
    except Exception:
        pass


def apply_dark_title_bar(window: QMainWindow | QDialog) -> None:
    """Ask Windows 10/11 to draw the non-client area dark."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
        value = ctypes.c_int(1)
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE on current Windows builds.
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


class _TitleBarFilter(QObject):
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Show and isinstance(watched, (QMainWindow, QDialog)):
            apply_dark_title_bar(watched)
        return False


def _install_excepthook() -> None:
    log_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Ominis"
    log_path = log_dir / "workstation.log"

    def handler(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except OSError:
            pass
        QMessageBox.critical(
            None, "Ominis workstation",
            "An unexpected error occurred.\n\n"
            f"{exc_type.__name__}: {exc}\n\n"
            f"Details were written to:\n{log_path}")

    sys.excepthook = handler


def _load_icon() -> QIcon:
    for name in ("icon.ico", "icon.png"):
        path = resource_path(name)
        if path.exists():
            return QIcon(str(path))
    return QIcon()


def _asset_rules() -> str:
    """Stylesheet rules that need an absolute path to a bundled asset."""
    chevron = resource_path("chevron.png")
    if not chevron.exists():
        return ""
    path = chevron.as_posix()
    return (
        f'\nQComboBox::down-arrow {{ image: url("{path}"); '
        f'width: 12px; height: 7px; }}\n'
        f'QComboBox::drop-down {{ subcontrol-position: center right; '
        f'width: 24px; border: 0; }}\n'
        f'QDateEdit::down-arrow {{ image: url("{path}"); '
        f'width: 10px; height: 6px; }}\n'
    )


def _run_smoke(app: QApplication, window: MainWindow, target: str) -> None:
    """Write a render or a report, then quit with a status code."""
    path = Path(target)
    ok = True
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".png":
            ok = window.grab().save(str(path))
        else:
            checks = backend.doctor_checks()
            failures = [check for check in checks if not check.get("ok")]
            lines = [
                f"{APP_NAME} {APP_VERSION}",
                f"engine: {engine_version}",
                f"window: {window.width()}x{window.height()}",
                f"tabs: {window.tabs.count()}",
                f"title: " + window.windowTitle().replace(
                    "\u00b7", "-").encode("ascii", "replace").decode(),
                f"icon: {'ok' if not window.windowIcon().isNull() else 'missing'}",
                f"stylesheet: {'ok' if app.styleSheet() else 'missing'}",
                f"checks: {len(checks) - len(failures)} passed, "
                f"{len(failures)} failed",
            ]
            for check in failures:
                lines.append(f"failed: {check.get('label')}: {check.get('detail')}")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            # A missing network route is an environment condition, not a
            # broken bundle. Only the window itself gates the exit code.
            ok = (not window.windowIcon().isNull()
                  and window.tabs.count() >= 4
                  and bool(app.styleSheet()))
    except OSError:
        ok = False
    app.exit(0 if ok else 2)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    smoke = ""
    if "--smoke" in args:
        index = args.index("--smoke")
        if index + 1 < len(args):
            smoke = args[index + 1]
            del args[index:index + 2]
        else:
            del args[index:]
    _configure_windows()
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(args)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setWindowIcon(_load_icon())
    app.setStyleSheet(theme.STYLESHEET + _asset_rules())

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(theme.BG))
    palette.setColor(QPalette.Base, QColor(theme.PANEL))
    palette.setColor(QPalette.Text, QColor(theme.INK))
    palette.setColor(QPalette.WindowText, QColor(theme.INK))
    palette.setColor(QPalette.Button, QColor(theme.PANEL_ALT))
    palette.setColor(QPalette.ButtonText, QColor(theme.INK))
    palette.setColor(QPalette.Highlight, QColor("#14304f"))
    palette.setColor(QPalette.HighlightedText, QColor(theme.INK))
    app.setPalette(palette)

    _install_excepthook()
    app.installEventFilter(_TitleBarFilter(app))

    window = MainWindow()
    window.setWindowIcon(_load_icon())
    window.show()
    if smoke:
        QTimer.singleShot(900, lambda: _run_smoke(app, window, smoke))
    return app.exec()
