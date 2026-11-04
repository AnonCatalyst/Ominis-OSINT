"""Render the workstation screenshots from captured payloads.

Run from the repository root on Windows:

    python ominis_workstation/tools/render_shots.py

The payloads come from ``docs/workstation/captures`` and are produced by
``capture_reports.py``. The window is a real Qt window rendered by Qt itself;
nothing is mocked and no browser is involved.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ominis_workstation import theme  # noqa: E402
from ominis_workstation.app import (  # noqa: E402
    _asset_rules, _load_icon, apply_dark_title_bar,
)
from ominis_workstation.main_window import (  # noqa: E402
    AboutDialog, DoctorDialog, MainWindow, SettingsDialog, SignalsDialog,
)

WIDTH = 1500
HEIGHT = 940


def load(captures: Path, name: str) -> dict[str, Any]:
    return json.loads((captures / f"{name}.json").read_text(encoding="utf-8"))


def settle(app: QApplication) -> None:
    for _ in range(3):
        app.processEvents()
    loop = QEventLoop()
    QTimer.singleShot(120, loop.quit)
    loop.exec()


def save(widget, path: Path, app: QApplication) -> None:
    settle(app)
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(path))
    print(path)


def prepare(window: MainWindow, payload: dict[str, Any]) -> None:
    window.target.setText(payload["target"])
    window.mode.setCurrentText(payload["mode"])
    # Keep the capture free of any local account path.
    window.case_panel.out_dir.setText("C:\\Ominis Cases")
    window._on_finished(payload)
    window.overview.mode_pill.set_kind(
        "warn" if payload["mode"] == "StyxNet" else "good")


def select_result(window: MainWindow, predicate) -> None:
    for row in range(window.results_table.rowCount()):
        payload = window.results_table.row_payload(row)
        if payload and predicate(payload):
            window.results_table.selectRow(row)
            window.results_table.scrollToItem(
                window.results_table.item(row, 0))
            return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", default=str(
        ROOT / "docs" / "workstation" / "captures"))
    parser.add_argument("--out", default=str(
        ROOT / "docs" / "workstation" / "screenshots"))
    args = parser.parse_args()
    captures = Path(args.captures)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.png"):
        stale.unlink()

    # Captures should not depend on whatever proxy the build machine has.
    for name in ("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY",
                 "all_proxy", "http_proxy", "https_proxy"):
        os.environ.pop(name, None)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(_load_icon())
    app.setStyleSheet(theme.STYLESHEET + _asset_rules())

    window = MainWindow()
    window.setWindowIcon(_load_icon())
    window.target.clear()
    window.resize(WIDTH, HEIGHT)
    window.show()
    apply_dark_title_bar(window)
    save(window, out / "00-welcome.png", app)

    search = load(captures, "local-search")
    prepare(window, search)
    window.tabs.setCurrentIndex(0)
    if search.get("profiles"):
        window.inspector.show_profile(search["profiles"][0])
    save(window, out / "01-overview.png", app)

    window.tabs.setCurrentIndex(1)
    select_result(window, lambda record: bool(record.get("profile_platform")))
    if not window.results_table.selectedItems():
        window.results_table.selectRow(0)
    save(window, out / "02-results.png", app)

    window.tabs.setCurrentIndex(2)
    if window.profiles_table.rowCount():
        window.profiles_table.selectRow(0)
    save(window, out / "03-profiles.png", app)

    username = load(captures, "username")
    prepare(window, username)
    window.tabs.setCurrentIndex(0)
    if username.get("profiles"):
        window.inspector.show_profile(username["profiles"][0])
    save(window, out / "04-username-overview.png", app)
    window.tabs.setCurrentIndex(2)
    if window.profiles_table.rowCount():
        window.profiles_table.selectRow(0)
    save(window, out / "05-username-profiles.png", app)

    window.tabs.setCurrentIndex(1)
    select_result(window, lambda record: bool(record.get("matched")))
    if not window.results_table.selectedItems():
        window.results_table.selectRow(0)
    save(window, out / "06-username-checks.png", app)

    styx = load(captures, "styxnet")
    prepare(window, styx)
    window.tabs.setCurrentIndex(0)
    if styx.get("profiles"):
        window.inspector.show_profile(styx["profiles"][0])
    save(window, out / "07-styxnet-overview.png", app)
    window.tabs.setCurrentIndex(2)
    if window.profiles_table.rowCount():
        window.profiles_table.selectRow(0)
    save(window, out / "08-styxnet-profiles.png", app)

    settings = SettingsDialog(window)
    settings.resize(560, 580)
    settings.show()
    apply_dark_title_bar(settings)
    save(settings, out / "09-settings.png", app)
    settings.close()

    about = AboutDialog(window)
    about.resize(580, 470)
    about.show()
    apply_dark_title_bar(about)
    save(about, out / "10-about.png", app)
    about.close()

    signals = SignalsDialog(window)
    signals.resize(840, 760)
    signals.show()
    apply_dark_title_bar(signals)
    save(signals, out / "12-signals.png", app)
    signals.close()

    doctor = DoctorDialog(window)
    doctor.resize(640, 660)
    doctor.show()
    apply_dark_title_bar(doctor)
    loop = QEventLoop()
    doctor.worker.finished.connect(loop.quit)
    QTimer.singleShot(20000, loop.quit)
    loop.exec()
    settle(app)
    save(doctor, out / "11-doctor.png", app)
    doctor.close()

    window.hide()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
