"""The Ominis investigation workstation window."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, QSettings, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ominis_src import __version__ as engine_version

from . import __version__ as workstation_version
from . import backend, theme
from .backend import MODE_SEARCH, MODE_STYXNET, MODE_USERNAME, MODES, InvestigationRequest
from .widgets import (
    ActivityView, DataTable, Hairline, Inspector, MetricCard, Pill,
    ProfilesTable, ResultsTable, SectionTitle, SortItem, SIGNALS,
    profile_signal, signal_color, signal_label, signal_strength,
)

APP_VERSION = workstation_version
APP_NAME = "Ominis Investigation Workstation"
ORG_NAME = "WinterGate"
DOCS_URL = "https://github.com/AnonCatalyst/Ominis-OSINT"
SERVICE_URL = "https://wintergate.org/styxnet/"
DISCORD_URL = "https://discord.gg/tu5CynxjZq"


class CasePanel(QFrame):
    """Left column: everything that shapes one run."""

    settingsRequested = Signal()
    modeChanged = Signal(str)
    proxyChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SidePanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        head = SectionTitle("Case file")
        layout.addWidget(head)
        hint = QLabel("Options apply to the next run.")
        hint.setObjectName("Hint")
        layout.addWidget(hint)

        self.mode = QComboBox()
        self.mode.addItems(list(MODES))
        layout.addWidget(self._field("Mode", self.mode))

        # Web search engines
        self.engine_group = QGroupBox("Engines")
        engine_layout = QVBoxLayout(self.engine_group)
        engine_layout.setSpacing(6)
        self.engine_boxes: dict[str, QCheckBox] = {}
        for name, label in (("duckduckgo", "DuckDuckGo"),
                            ("bing", "Bing"),
                            ("serpbase", "SerpBase (API key)")):
            box = QCheckBox(label)
            box.setChecked(name in ("duckduckgo", "bing"))
            self.engine_boxes[name] = box
            engine_layout.addWidget(box)
        self.engine_note = QLabel("Scraped locally. Proxies are off by default.")
        self.engine_note.setObjectName("Hint")
        self.engine_note.setWordWrap(True)
        engine_layout.addWidget(self.engine_note)
        layout.addWidget(self.engine_group)

        self.scan_group = QGroupBox("Page inspection")
        scan_layout = QVBoxLayout(self.scan_group)
        scan_layout.setSpacing(6)
        self.scan_pages = QCheckBox("Read result pages and verify profiles")
        self.scan_pages.setChecked(True)
        self.scan_pages.setToolTip(
            "Fetch each result page and record whether its metadata, "
            "canonical URL, structured data, or visible text matches the "
            "query. This is the same evidence the username checker uses.")
        scan_layout.addWidget(self.scan_pages)
        self.scan_limit = QSpinBox()
        self.scan_limit.setRange(1, 100)
        self.scan_limit.setValue(10)
        self.scan_limit.setToolTip("How many of the top results to inspect.")
        scan_row = QHBoxLayout()
        scan_row.addWidget(QLabel("Pages to inspect"))
        scan_row.addWidget(self.scan_limit, 1)
        scan_layout.addLayout(scan_row)
        self.scan_pages.toggled.connect(self.scan_limit.setEnabled)
        layout.addWidget(self.scan_group)

        self.proxy_group = QGroupBox("Proxies (optional)")
        proxy_layout = QVBoxLayout(self.proxy_group)
        proxy_layout.setSpacing(6)
        self.proxy_toggle = QCheckBox("Route through a proxy pool")
        proxy_layout.addWidget(self.proxy_toggle)
        self.proxy_edit = QPlainTextEdit()
        self.proxy_edit.setPlaceholderText(
            "One endpoint per line, for example\n"
            "http://host:8080\n"
            "socks5://host:1080")
        self.proxy_edit.setFixedHeight(64)
        self.proxy_edit.setEnabled(False)
        proxy_layout.addWidget(self.proxy_edit)
        self.env_proxy = QCheckBox("Use system proxy environment")
        self.env_proxy.setToolTip(
            "Honour HTTP_PROXY, HTTPS_PROXY and ALL_PROXY. Off by default so "
            "a stale proxy variable cannot silently empty a run.")
        self.env_proxy.setEnabled(False)
        proxy_layout.addWidget(self.env_proxy)
        proxy_note = QLabel(
            "Off by default. Entries are used for this session only and are "
            "never written to a report or the activity log.")
        proxy_note.setObjectName("Hint")
        proxy_note.setWordWrap(True)
        proxy_layout.addWidget(proxy_note)
        self.proxy_toggle.toggled.connect(self._proxy_toggled)
        layout.addWidget(self.proxy_group)

        self.max_results = QSpinBox()
        self.max_results.setRange(1, 1000)
        self.max_results.setValue(25)
        self.max_field = self._field("Max results", self.max_results)
        layout.addWidget(self.max_field)

        self.filters_group = QGroupBox("Filters")
        filter_layout = QGridLayout(self.filters_group)
        filter_layout.setContentsMargins(10, 12, 10, 8)
        filter_layout.setSpacing(8)
        self.language = QLineEdit()
        self.language.setPlaceholderText("en")
        self.language.setMaxLength(8)
        self.country = QLineEdit()
        self.country.setPlaceholderText("US")
        self.country.setMaxLength(8)
        filter_layout.addWidget(QLabel("Language"), 0, 0)
        filter_layout.addWidget(self.language, 0, 1)
        filter_layout.addWidget(QLabel("Country"), 1, 0)
        filter_layout.addWidget(self.country, 1, 1)
        self.date_toggle = QCheckBox("Date range")
        self.since = QDateEdit(QDate.currentDate().addMonths(-6))
        self.until = QDateEdit(QDate.currentDate())
        for widget in (self.since, self.until):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("yyyy-MM-dd")
            widget.setEnabled(False)
        self.date_toggle.toggled.connect(self.since.setEnabled)
        self.date_toggle.toggled.connect(self.until.setEnabled)
        filter_layout.addWidget(self.date_toggle, 2, 0, 1, 2)
        filter_layout.addWidget(QLabel("From"), 3, 0)
        filter_layout.addWidget(self.since, 3, 1)
        filter_layout.addWidget(QLabel("To"), 4, 0)
        filter_layout.addWidget(self.until, 4, 1)
        layout.addWidget(self.filters_group)

        # Username options
        self.username_group = QGroupBox("Username check")
        username_layout = QVBoxLayout(self.username_group)
        username_layout.setSpacing(6)
        self.include_all = QCheckBox("Include every checked URL in the report")
        self.include_all.setChecked(True)
        username_layout.addWidget(self.include_all)
        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 32)
        self.concurrency.setValue(8)
        concurrency_row = QHBoxLayout()
        concurrency_row.addWidget(QLabel("Parallel checks"))
        concurrency_row.addWidget(self.concurrency, 1)
        username_layout.addLayout(concurrency_row)
        layout.addWidget(self.username_group)

        # StyxNet options
        self.styxnet_group = QGroupBox("StyxNet")
        styx_layout = QVBoxLayout(self.styxnet_group)
        styx_layout.setSpacing(6)
        self.styxnet_engines = QSpinBox()
        self.styxnet_engines.setRange(1, 200)
        self.styxnet_engines.setValue(35)
        styx_layout.addWidget(self._field("Engine cap", self.styxnet_engines))
        styx_layout.addWidget(QLabel("Scopes"))
        self.scope_boxes: dict[str, QCheckBox] = {}
        for scope in ("surface", "onion", "deep"):
            box = QCheckBox(scope.title())
            box.setChecked(True)
            self.scope_boxes[scope] = box
            styx_layout.addWidget(box)
        key_row = QHBoxLayout()
        self.key_status = Pill("No key saved")
        key_row.addWidget(self.key_status)
        key_row.addStretch(1)
        key_button = QPushButton("Configure")
        key_button.clicked.connect(self.settingsRequested)
        key_row.addWidget(key_button)
        styx_layout.addLayout(key_row)
        note = QLabel(f"Access is free. Request it in the WinterGate Discord: "
                      f"<a href='{DISCORD_URL}'>discord.gg/tu5CynxjZq</a>")
        note.setOpenExternalLinks(True)
        note.setWordWrap(True)
        note.setObjectName("Hint")
        styx_layout.addWidget(note)
        layout.addWidget(self.styxnet_group)

        output = QGroupBox("Report")
        output_layout = QVBoxLayout(output)
        output_layout.setSpacing(6)
        self.out_dir = QLineEdit()
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.out_dir, 1)
        dir_row.addWidget(browse)
        output_layout.addLayout(dir_row)
        self.save_report = QCheckBox("Save report files")
        self.save_report.setChecked(True)
        self.save_report.setToolTip(
            "Uncheck to keep results in the window only. No files are written "
            "and no report folder is created.")
        output_layout.addWidget(self.save_report)
        output_layout.addWidget(QLabel("Formats"))
        format_row = QGridLayout()
        self.format_boxes: dict[str, QCheckBox] = {}
        for index, name in enumerate(("txt", "json", "md", "csv")):
            box = QCheckBox(name.upper())
            box.setChecked(name in ("txt", "json", "md"))
            self.format_boxes[name] = box
            format_row.addWidget(box, index // 2, index % 2)
        output_layout.addLayout(format_row)
        self.save_report.toggled.connect(self._report_toggled)
        layout.addWidget(output)

        layout.addStretch(1)

        self.mode.currentTextChanged.connect(self._mode_changed)
        self._mode_changed(self.mode.currentText())

    def _field(self, label: str, widget: QWidget) -> QWidget:
        wrapper = QWidget()
        box = QVBoxLayout(wrapper)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        name = QLabel(label)
        name.setObjectName("Hint")
        box.addWidget(name)
        box.addWidget(widget)
        return wrapper

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose a report folder", self.out_dir.text())
        if folder:
            self.out_dir.setText(folder)

    def _mode_changed(self, mode: str) -> None:
        is_username = mode == MODE_USERNAME
        is_styxnet = mode == MODE_STYXNET
        self.engine_group.setVisible(not is_username and not is_styxnet)
        self.scan_group.setVisible(not is_username)
        self.max_field.setVisible(not is_username)
        self.max_results.setEnabled(not is_username)
        self.filters_group.setVisible(not is_username)
        self.username_group.setVisible(is_username)
        self.styxnet_group.setVisible(is_styxnet)
        self.date_toggle.setEnabled(not is_username)
        for widget in (self.since, self.until):
            widget.setEnabled(not is_username and self.date_toggle.isChecked())
        if is_username:
            self.engine_note.setText("Each template is checked over HTTPS.")
        elif is_styxnet:
            self.engine_note.setText("One request to the WinterGate pool.")
        else:
            self.engine_note.setText("Scraped locally. Proxies are off by default.")
        self.modeChanged.emit(mode)

    def selected_engines(self) -> tuple[str, ...]:
        return tuple(name for name, box in self.engine_boxes.items()
                     if box.isChecked())

    def selected_formats(self) -> tuple[str, ...]:
        if not self.save_report.isChecked():
            return ()
        return tuple(name for name, box in self.format_boxes.items()
                     if box.isChecked())

    def selected_proxies(self) -> tuple[str, ...]:
        if not self.proxy_toggle.isChecked():
            return ()
        entries: list[str] = []
        for line in self.proxy_edit.toPlainText().splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                entries.append(line)
        return tuple(dict.fromkeys(entries))

    def _proxy_toggled(self, enabled: bool) -> None:
        self.proxy_edit.setEnabled(enabled)
        self.env_proxy.setEnabled(enabled)
        self.proxyChanged.emit()

    def _report_toggled(self, enabled: bool) -> None:
        for box in self.format_boxes.values():
            box.setEnabled(enabled)
        self.out_dir.setEnabled(enabled)

    def selected_scopes(self) -> tuple[str, ...]:
        return tuple(name for name, box in self.scope_boxes.items()
                     if box.isChecked())

    def set_key_status(self, text: str, ok: bool) -> None:
        self.key_status.setText(text)
        self.key_status.set_kind("good" if ok else "")

    def set_running(self, running: bool) -> None:
        self.setEnabled(not running)

    def load_values(self, settings: QSettings) -> None:
        mode = settings.value("run/mode", MODE_SEARCH, type=str)
        index = self.mode.findText(mode)
        if index >= 0:
            self.mode.setCurrentIndex(index)
        self.max_results.setValue(settings.value("run/max_results", 25, type=int))
        self.language.setText(settings.value("run/language", "", type=str))
        self.country.setText(settings.value("run/country", "", type=str))
        saved_dir = settings.value("run/out_dir", "", type=str)
        self.out_dir.setText(saved_dir or str(_default_cases_dir()))
        self.out_dir.setCursorPosition(0)
        saved = settings.value("run/engines", "duckduckgo,bing", type=str).split(",")
        for name, box in self.engine_boxes.items():
            box.setChecked(name in saved)
        self.include_all.setChecked(
            settings.value("run/include_all", True, type=bool))
        self.scan_pages.setChecked(
            settings.value("run/scan_pages", True, type=bool))
        self.scan_limit.setValue(
            settings.value("run/scan_limit", 10, type=int))
        self.save_report.setChecked(
            settings.value("run/save_report", True, type=bool))
        self._report_toggled(self.save_report.isChecked())
        self.concurrency.setValue(
            settings.value("run/concurrency", 8, type=int))
        self.styxnet_engines.setValue(
            settings.value("run/styxnet_engines", 35, type=int))
        scopes = settings.value("run/scopes", "surface,onion,deep",
                                type=str).split(",")
        for name, box in self.scope_boxes.items():
            box.setChecked(name in scopes)

    def save_values(self, settings: QSettings) -> None:
        settings.setValue("run/mode", self.mode.currentText())
        settings.setValue("run/max_results", self.max_results.value())
        settings.setValue("run/language", self.language.text().strip())
        settings.setValue("run/country", self.country.text().strip())
        settings.setValue("run/out_dir", self.out_dir.text().strip())
        settings.setValue("run/engines", ",".join(self.selected_engines()))
        settings.setValue("run/include_all", self.include_all.isChecked())
        settings.setValue("run/scan_pages", self.scan_pages.isChecked())
        settings.setValue("run/scan_limit", self.scan_limit.value())
        settings.setValue("run/save_report", self.save_report.isChecked())
        settings.setValue("run/concurrency", self.concurrency.value())
        settings.setValue("run/styxnet_engines", self.styxnet_engines.value())
        settings.setValue("run/scopes", ",".join(self.selected_scopes()))


def _default_cases_dir() -> Path:
    documents = Path.home() / "Documents"
    return documents / "Ominis Cases"


class OverviewPage(QWidget):
    resultActivated = Signal(dict)
    profileActivated = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = QLabel("Ready for a new case")
        self.title.setObjectName("PageTitle")
        self.subtitle = QLabel("Enter a target above and choose a mode.")
        self.subtitle.setObjectName("Hint")
        self.subtitle.setWordWrap(True)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        head.addLayout(titles, 1)
        self.mode_pill = Pill("idle")
        head.addWidget(self.mode_pill, 0, Qt.AlignTop)
        layout.addLayout(head)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self.card_a = MetricCard("Results")
        self.card_b = MetricCard("Profiles", accent=theme.GLOW)
        self.card_c = MetricCard("Engines", accent=theme.EMBER)
        self.card_d = MetricCard("Elapsed", "0 ms", accent=theme.VIOLET)
        for card in (self.card_a, self.card_b, self.card_c, self.card_d):
            metrics.addWidget(card)
        layout.addLayout(metrics)

        self.mentions = QLabel("")
        self.mentions.setObjectName("Hint")
        self.mentions.setWordWrap(True)
        layout.addWidget(self.mentions)

        self.detections = QLabel("")
        self.detections.setObjectName("Hint")
        self.detections.setWordWrap(True)
        self.detections.setTextFormat(Qt.RichText)
        layout.addWidget(self.detections)

        leads_head = QHBoxLayout()
        leads_head.addWidget(SectionTitle("Top leads"))
        leads_head.addStretch(1)
        self.leads_note = QLabel("")
        self.leads_note.setObjectName("Hint")
        leads_head.addWidget(self.leads_note)
        layout.addLayout(leads_head)

        self.leads = QListWidget()
        self.leads.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.leads.itemActivated.connect(self._lead_chosen)
        self.leads.itemClicked.connect(self._lead_chosen)
        layout.addWidget(self.leads, 1)

        self.hint = QLabel(
            "Reports are written automatically when a run finishes. "
            "Select any row to inspect it, or double-click to open the link. "
            "Marks: ◆ detected profile · ✓ confirmed match · ✗ request error.")
        self.hint.setObjectName("Hint")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        self._payload: dict[str, Any] | None = None

    def reset(self) -> None:
        self._payload = None
        self.title.setText("Running...")
        self.subtitle.setText("The engine is working. Activity streams in the log.")
        self.mode_pill.setText("running")
        self.mode_pill.set_kind("warn")
        self.card_a.set_value("-")
        self.card_b.set_value("-")
        self.card_c.set_value("-")
        self.card_d.set_value("-")
        self.mentions.setText("")
        self.detections.setText("")
        self.leads.clear()
        self.leads_note.setText("")

    def clear(self) -> None:
        self._payload = None
        self.title.setText("Ready for a new case")
        self.subtitle.setText("Enter a target above and choose a mode.")
        self.mode_pill.setText("idle")
        self.mode_pill.set_kind("")
        self.card_a.label.setText("Results")
        self.card_b.label.setText("Profiles")
        self.card_c.label.setText("Engines")
        self.card_a.set_value("0")
        self.card_b.set_value("0")
        self.card_c.set_value("0")
        self.card_d.set_value("0 ms")
        self.mentions.setText("")
        self.detections.setText("")
        self.leads.clear()
        self.leads_note.setText("")

    def load(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        mode = payload.get("mode") or MODE_SEARCH
        target = payload.get("target") or ""
        summary = payload.get("summary") or {}
        elapsed = int(payload.get("elapsed_ms") or 0)
        self.title.setText(target)
        self.mode_pill.setText(str(mode).lower())
        self.mode_pill.set_kind("good" if mode != MODE_STYXNET else "warn")

        if mode == MODE_USERNAME:
            self.card_a.label.setText("Checked")
            self.card_b.label.setText("Matches")
            self.card_c.label.setText("Errors")
            self.card_a.set_value(summary.get("checked", 0))
            self.card_b.set_value(summary.get("found", 0))
            self.card_c.set_value(summary.get("errors", 0))
            self.subtitle.setText(
                f"{summary.get('found', 0)} confirmed profiles across "
                f"{summary.get('checked', 0)} checked templates.")
            self.mentions.setText("")
        else:
            self.card_a.label.setText("Results")
            self.card_b.label.setText("Profiles")
            self.card_c.label.setText("Engines")
            self.card_a.set_value(summary.get("results", 0))
            self.card_b.set_value(summary.get("profiles", 0))
            engines = summary.get("engines") or []
            meta = summary.get("styxnet_meta") or {}
            if mode == MODE_STYXNET and meta.get("engines"):
                self.card_c.set_value(meta.get("engines"))
            else:
                self.card_c.set_value(len(engines) if engines else 0)
            mentions = summary.get("mentions") or {}
            if mentions:
                parts = [f"<b>{_esc(k)}</b> &times;{_esc(v)}"
                         for k, v in mentions.items()]
                self.mentions.setText("Mentions: " + " &nbsp; ".join(parts))
            else:
                self.mentions.setText("No mention counts were produced.")
            if mode == MODE_STYXNET:
                engines = meta.get("engines")
                note = f" · {engines} engines pooled" if engines else ""
                self.subtitle.setText(
                    f"StyxNet returned {summary.get('results', 0)} organic "
                    f"result(s) and {summary.get('profiles', 0)} candidate "
                    f"profile(s)" + note + ".")
            else:
                self.subtitle.setText(
                    f"{summary.get('results', 0)} results from "
                    f"{', '.join(engines) or 'no engines'}.")
        self.card_d.set_value(f"{elapsed} ms")
        self.detections.setText(self._detection_summary(payload))

        self.leads.clear()
        leads: list[tuple[str, dict[str, Any], str]] = []
        if mode == MODE_USERNAME:
            for profile in payload.get("profiles", [])[:8]:
                leads.append(("profile", profile,
                              f"{profile.get('platform') or 'Unknown'}  ·  "
                              f"{profile.get('confidence', 0)}%  ·  "
                              f"{signal_label(profile_signal(profile))}"))
        else:
            for record in payload.get("results", [])[:6]:
                leads.append(("result", record,
                              f"{record.get('title') or record.get('url')}"))
            for profile in payload.get("profiles", [])[:4]:
                leads.append(("profile", profile,
                              f"{profile.get('platform') or 'Unknown'}  ·  "
                              f"{profile.get('confidence', 0)}%  ·  "
                              f"{signal_label(profile_signal(profile))}"))
        for kind, data, label in leads:
            item = QListWidgetItem(_ellipsis(label, 110))
            item.setData(Qt.UserRole, kind)
            item.setData(Qt.UserRole + 1, data)
            self.leads.addItem(item)
        if not leads:
            item = QListWidgetItem("No leads in this run.")
            item.setFlags(Qt.NoItemFlags)
            self.leads.addItem(item)
        written = payload.get("paths") or {}
        if written:
            self.leads_note.setText(
                f"{len(written)} report file(s) written")
        else:
            self.leads_note.setText("")

    def _detection_summary(self, payload: dict[str, Any]) -> str:
        profiles = payload.get("profiles") or []
        results = payload.get("results") or []
        mode = payload.get("mode")
        chunks: list[str] = []
        if profiles:
            counts: dict[str, int] = {}
            for profile in profiles:
                key = profile_signal(profile)
                counts[key] = counts.get(key, 0) + 1
            rank = {"strong": 4, "medium": 3, "candidate": 2,
                    "error": 1, "none": 0}
            order = sorted(counts, key=lambda key: (
                -rank.get(signal_strength(key), 0), signal_label(key)))
            parts = [
                f"<span style='color:{signal_color(key)}'>"
                f"<b>{_esc(signal_label(key))}</b> &times;{counts[key]}</span>"
                for key in order
            ]
            chunks.append(
                f"{len(profiles)} profile lead"
                f"{'s' if len(profiles) != 1 else ''}: "
                + " &nbsp;&middot;&nbsp; ".join(parts))
        if mode != MODE_USERNAME and profiles and results:
            known = {str(profile.get("profile_url") or "").rstrip("/").casefold()
                     for profile in profiles}
            hits = sum(
                1 for record in results
                if str(record.get("url") or "").rstrip("/").casefold() in known)
            if hits:
                chunks.append(
                    f"{hits} of {len(results)} results resolve to a detected profile")
        if not chunks:
            return ""
        return "Detection: " + " &nbsp;|&nbsp; ".join(chunks)

    def _lead_chosen(self, item: QListWidgetItem) -> None:
        kind = item.data(Qt.UserRole)
        data = item.data(Qt.UserRole + 1)
        if not isinstance(data, dict):
            return
        if kind == "profile":
            self.profileActivated.emit(data)
        else:
            self.resultActivated.emit(data)


def _esc(value: object) -> str:
    import html

    return html.escape(str(value or ""))


def _ellipsis(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Workstation settings")
        self.setObjectName("Sheet")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        eyebrow = QLabel("SETTINGS")
        eyebrow.setObjectName("Eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Settings")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        body = QLabel(
            "StyxNet is optional. Access is free right now but needs a key. "
            "Request one in the WinterGate Discord; keys are issued by hand. "
            "Saved keys stay on this machine and are never displayed again.")
        body.setObjectName("Hint")
        body.setWordWrap(True)
        layout.addWidget(body)

        link = QLabel(f"<a href='{DISCORD_URL}'>{DISCORD_URL}</a>")
        link.setOpenExternalLinks(True)
        layout.addWidget(link)

        self.status = QLabel(backend.key_status())
        self.status.setObjectName("Mono")
        layout.addWidget(self.status)

        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.Password)
        self.key_input.setPlaceholderText("sgn_...")
        layout.addWidget(self.key_input)

        buttons = QHBoxLayout()
        save = QPushButton("Save key")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        clear = QPushButton("Remove saved key")
        clear.setObjectName("Danger")
        clear.clicked.connect(self._clear)
        buttons.addWidget(save)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        note = QLabel(
            "The workstation reads STYXNET_ACCESS_KEY or OMINIS_STYXNET_KEY "
            "if either is set, otherwise it uses the key file under "
            "~/.config/ominis. It writes only that key file.")
        note.setObjectName("Hint")
        note.setWordWrap(True)
        layout.addWidget(note)

        layout.addWidget(Hairline())
        desktop = QLabel("DESKTOP")
        desktop.setObjectName("Eyebrow")
        layout.addWidget(desktop)
        desktop_note = QLabel(
            "The installer creates a Desktop shortcut. For the portable "
            "build, or after moving the folder, create the shortcuts here.")
        desktop_note.setObjectName("Hint")
        desktop_note.setWordWrap(True)
        layout.addWidget(desktop_note)
        shortcut = QPushButton("Create Desktop and Start menu shortcuts")
        shortcut.clicked.connect(self._install_shortcut)
        layout.addWidget(shortcut)
        link_row = QHBoxLayout()
        docs = QPushButton("Open the StyxNet page")
        docs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(SERVICE_URL)))
        repo = QPushButton("Project documentation")
        repo.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(DOCS_URL)))
        link_row.addWidget(docs)
        link_row.addWidget(repo)
        link_row.addStretch(1)
        layout.addLayout(link_row)

        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        close.accepted.connect(self.accept)
        layout.addWidget(close)

        for button in close.buttons():
            button.setAutoDefault(False)

    def _refresh(self) -> None:
        self.status.setText(backend.key_status())

    def _install_shortcut(self) -> None:
        try:
            created = backend.create_shortcuts()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Shortcut not created", str(exc))
            return
        QMessageBox.information(
            self, "Shortcut created",
            "Created:\n" + "\n".join(str(path) for path in created))

    def _save(self) -> None:
        try:
            backend.save_key(self.key_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Key not saved", str(exc))
            return
        self.key_input.clear()
        self._refresh()
        QMessageBox.information(self, "Key saved",
                                "The StyxNet key is saved for this account.")

    def _clear(self) -> None:
        if backend.clear_key():
            self._refresh()
            QMessageBox.information(self, "Key removed",
                                    "The saved StyxNet key was deleted.")
        else:
            QMessageBox.information(self, "No saved key",
                                    "There was no saved key to remove.")


class DoctorDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Environment check")
        self.setObjectName("Sheet")
        self.setMinimumSize(620, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        eyebrow = QLabel("DIAGNOSTICS")
        eyebrow.setObjectName("Eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Environment check")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        self.note = QLabel("Running checks...")
        self.note.setObjectName("Hint")
        layout.addWidget(self.note)

        self.table = DataTable(["Check", "State", "Detail"], {0: 190, 1: 90})
        self.table.allow_sorting = False
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)

        self.worker = backend.DoctorWorker(self)
        self.worker.finished.connect(self._loaded)
        self.worker.start()

    def _loaded(self, checks: list[dict[str, Any]]) -> None:
        # Failures first: the operator should not have to scroll to find the
        # one line that needs action.
        ordered = sorted(checks, key=lambda check: bool(check.get("ok")))
        rows = []
        failed: list[str] = []
        for check in ordered:
            ok = bool(check.get("ok"))
            if not ok:
                failed.append(str(check.get("label") or "check"))
            state = SortItem("PASS" if ok else "FAIL")
            state.setForeground(QColor(theme.GREEN if ok else theme.RED))
            rows.append([
                SortItem(check.get("label") or ""),
                state,
                SortItem(check.get("detail") or ""),
            ])
        self.table.fill(rows)
        if not failed:
            self.note.setText("All checks passed.")
        else:
            self.note.setText(
                f"{len(failed)} check(s) need attention: " + ", ".join(failed))


class SignalsDialog(QDialog):
    """Reference for every detection label used in the tables."""

    ORDER = ("metadata", "canonical", "redirect", "structured", "body",
             "url", "registry", "styxnet", "checked", "error")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Detection signals")
        self.setObjectName("Sheet")
        self.setMinimumSize(780, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 16)
        layout.setSpacing(10)
        eyebrow = QLabel("REFERENCE")
        eyebrow.setObjectName("Eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Detection signals")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        intro = QLabel(
            "Every profile row records how it was found. Strong signals come "
            "from the page itself; the URL pattern is a lead until the page "
            "is opened. Hover any signal, or select a row, to see the same "
            "explanation in the inspector.")
        intro.setObjectName("Hint")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        table = DataTable(["Signal", "Strength", "What it means"],
                          {0: 170, 1: 95})
        table.allow_sorting = False
        table.horizontalHeader().setStretchLastSection(True)
        rows = []
        for key in self.ORDER:
            entry = SIGNALS[key]
            label = SortItem(entry["label"])
            label.setForeground(QColor(entry["color"]))
            label.setToolTip(entry["note"])
            strength = SortItem(entry["strength"].title())
            strength.setForeground(QColor(
                theme.RED if entry["strength"] == "error"
                else theme.EMBER if entry["strength"] == "candidate"
                else theme.GREEN if entry["strength"] == "strong"
                else theme.MUTED))
            note = SortItem(entry["note"])
            note.setToolTip(entry["note"])
            rows.append([label, strength, note])
        table.fill(rows)
        layout.addWidget(table, 1)

        marks = QLabel(
            "Marks: ✓ confirmed match · ✗ request error · · checked miss · "
            "◆ detected profile. Rows are tinted by signal strength; a checked "
            "miss stays neutral.")
        marks.setObjectName("Hint")
        marks.setWordWrap(True)
        layout.addWidget(marks)

        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setObjectName("Sheet")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(10)
        eyebrow = QLabel("WINTERGATE INTELLIGENCE COLLECTIVE")
        eyebrow.setObjectName("Eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel(APP_NAME)
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        version = QLabel(f"Workstation {APP_VERSION} · engine {engine_version} · "
                         f"Python {sys.version.split()[0]}")
        version.setObjectName("Hint")
        layout.addWidget(version)

        body = QLabel(
            "A native Windows investigation desk for the Ominis engine. "
            "This is a real Qt window application, not a browser page. "
            "Search the public web, check a username across platform "
            "templates, or query WinterGate's StyxNet pool without leaving "
            "one window.")
        body.setWordWrap(True)
        layout.addWidget(body)

        layout.addWidget(Hairline())
        identity = QLabel(
            "MIT licensed. Maintained by AnonCatalyst with the WinterGate "
            "Intelligence Collective. The collective is independent and "
            "unincorporated. This build is unsigned; no signing is claimed.")
        identity.setWordWrap(True)
        identity.setObjectName("Hint")
        layout.addWidget(identity)

        links = QHBoxLayout()
        for label, url in (("wintergate.org", "https://wintergate.org"),
                           ("GitHub", DOCS_URL),
                           ("StyxNet", SERVICE_URL),
                           ("Discord", DISCORD_URL)):
            button = QPushButton(label)
            button.clicked.connect(
                lambda _=False, target=url: QDesktopServices.openUrl(QUrl(target)))
            links.addWidget(button)
        links.addStretch(1)
        layout.addLayout(links)

        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} · WinterGate IC")
        self.setMinimumSize(QSize(1180, 760))
        self.resize(1460, 920)
        self.settings = QSettings(ORG_NAME, "OminisWorkstation")
        self.worker: backend.InvestigationWorker | None = None
        self.payload: dict[str, Any] | None = None

        self._build_actions()
        self._build_ui()
        self._restore()

    # ------------------------------------------------------------------ UI
    def _build_actions(self) -> None:
        self.act_run = QAction("Run investigation", self)
        self.act_run.setShortcut("Ctrl+Return")
        self.act_run.triggered.connect(self.run_investigation)
        self.act_stop = QAction("Stop", self)
        self.act_stop.setShortcut("Esc")
        self.act_stop.triggered.connect(self.stop_investigation)
        self.act_settings = QAction("StyxNet settings...", self)
        self.act_settings.triggered.connect(self.open_settings)
        self.act_open = QAction("Open report folder", self)
        self.act_open.setShortcut("Ctrl+O")
        self.act_open.triggered.connect(self.open_output)
        self.act_doctor = QAction("Environment check...", self)
        self.act_doctor.setShortcut("Ctrl+D")
        self.act_doctor.triggered.connect(self.open_doctor)
        self.act_shortcut = QAction("Install desktop shortcut...", self)
        self.act_shortcut.triggered.connect(self.install_shortcut)
        self.act_clear = QAction("Clear session", self)
        self.act_clear.setShortcut("Ctrl+L")
        self.act_clear.triggered.connect(self.clear_session)
        self.act_quit = QAction("Exit", self)
        self.act_quit.setShortcut("Ctrl+Q")
        self.act_quit.triggered.connect(self.close)
        self.act_docs = QAction("Documentation", self)
        self.act_docs.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(DOCS_URL)))
        self.act_signals = QAction("Detection signals...", self)
        self.act_signals.setShortcut("F1")
        self.act_signals.triggered.connect(self.open_signals)
        self.act_about = QAction("About...", self)
        self.act_about.triggered.connect(self.open_about)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self.act_run)
        file_menu.addAction(self.act_open)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        tools_menu = self.menuBar().addMenu("Tools")
        tools_menu.addAction(self.act_stop)
        tools_menu.addAction(self.act_clear)
        tools_menu.addSeparator()
        tools_menu.addAction(self.act_settings)
        tools_menu.addAction(self.act_doctor)
        tools_menu.addAction(self.act_shortcut)

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(self.act_signals)
        help_menu.addAction(self.act_docs)
        help_menu.addAction(self.act_about)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 10)
        root.setSpacing(12)

        bar = QFrame()
        bar.setObjectName("CommandBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(14, 12, 14, 12)
        bar_layout.setSpacing(12)

        mark = QLabel("WI")
        mark.setObjectName("BrandMark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(46, 46)
        bar_layout.addWidget(mark)
        brand = QVBoxLayout()
        brand.setSpacing(0)
        name = QLabel("OMINIS")
        name.setObjectName("BrandName")
        sub = QLabel("Investigation Workstation")
        sub.setObjectName("BrandSub")
        brand.addWidget(name)
        brand.addWidget(sub)
        bar_layout.addLayout(brand)
        bar_layout.addSpacing(10)

        self.target = QLineEdit()
        self.target.setObjectName("TargetInput")
        self.target.setPlaceholderText(
            "Target: name, username, domain, or phrase")
        self.target.returnPressed.connect(self.run_investigation)
        self.target.setClearButtonEnabled(True)
        bar_layout.addWidget(self.target, 1)

        self.mode = QComboBox()
        self.mode.addItems(list(MODES))
        self.mode.setMinimumWidth(132)
        self.mode.currentTextChanged.connect(self._mode_changed)
        bar_layout.addWidget(self.mode)

        self.run_button = QPushButton("Run")
        self.run_button.setObjectName("Primary")
        self.run_button.clicked.connect(self.run_investigation)
        bar_layout.addWidget(self.run_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("Danger")
        self.stop_button.clicked.connect(self.stop_investigation)
        self.stop_button.setEnabled(False)
        bar_layout.addWidget(self.stop_button)
        root.addWidget(bar)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)

        self.case_panel = CasePanel()
        self.case_panel.settingsRequested.connect(self.open_settings)
        self.case_panel.modeChanged.connect(self._panel_mode_changed)
        self.case_panel.proxyChanged.connect(self._update_proxy_pill)
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.NoFrame)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        side_scroll.setWidget(self.case_panel)
        side_scroll.setMinimumWidth(300)
        side_scroll.setMaximumWidth(360)
        splitter.addWidget(side_scroll)

        self.tabs = QTabWidget()
        self.overview = OverviewPage()
        self.overview.resultActivated.connect(self._show_result)
        self.overview.profileActivated.connect(self._show_profile)
        self.results_table = ResultsTable()
        self.profiles_table = ProfilesTable()
        self.activity = ActivityView()

        self.results_tab = QWidget()
        results_layout = QVBoxLayout(self.results_tab)
        results_layout.setContentsMargins(14, 12, 14, 14)
        results_layout.setSpacing(8)
        self.results_caption = QLabel("No results yet.")
        self.results_caption.setObjectName("Hint")
        results_layout.addWidget(self.results_caption)
        results_layout.addWidget(self.results_table, 1)

        self.profiles_tab = QWidget()
        profiles_layout = QVBoxLayout(self.profiles_tab)
        profiles_layout.setContentsMargins(14, 12, 14, 14)
        profiles_layout.setSpacing(8)
        self.profiles_caption = QLabel("No profiles yet.")
        self.profiles_caption.setObjectName("Hint")
        profiles_layout.addWidget(self.profiles_caption)
        profiles_layout.addWidget(self.profiles_table, 1)

        self.activity_tab = QWidget()
        activity_layout = QVBoxLayout(self.activity_tab)
        activity_layout.setContentsMargins(0, 0, 0, 0)
        activity_layout.addWidget(self.activity)

        self.tabs.addTab(self.overview, "Overview")
        self.tabs.addTab(self.results_tab, "Results")
        self.tabs.addTab(self.profiles_tab, "Profiles")
        self.tabs.addTab(self.activity_tab, "Activity")
        splitter.addWidget(self.tabs)

        self.inspector = Inspector()
        splitter.addWidget(self.inspector)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([320, 800, 320])
        root.addWidget(splitter, 1)

        self.setCentralWidget(central)

        self.results_table.itemSelectionChanged.connect(
            lambda: self._inspect_selection(self.results_table))
        self.profiles_table.itemSelectionChanged.connect(
            lambda: self._inspect_selection(self.profiles_table))
        status = self.statusBar()
        self.status_label = QLabel("Ready")
        status.addWidget(self.status_label, 1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        status.addPermanentWidget(self.progress)
        self.proxy_pill = Pill("Proxies off")
        status.addPermanentWidget(self.proxy_pill)
        self.key_pill = Pill(backend.key_status())
        status.addPermanentWidget(self.key_pill)

        self.mode.currentTextChanged.connect(self._sync_panel_mode)
        self._sync_panel_mode(self.mode.currentText())
        self._update_key_pills()
        self._update_proxy_pill()

    # -------------------------------------------------------------- helpers
    def _restore(self) -> None:
        geometry = self.settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.case_panel.load_values(self.settings)
        mode = self.case_panel.mode.currentText()
        index = self.mode.findText(mode)
        if index >= 0:
            self.mode.setCurrentIndex(index)
        last_target = self.settings.value("run/target", "", type=str)
        self.target.setText(last_target)

    def _save_window(self) -> None:
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("run/target", self.target.text())
        self.case_panel.save_values(self.settings)

    def _mode_changed(self, mode: str) -> None:
        if mode == MODE_USERNAME:
            self.target.setPlaceholderText("Username, for example AnonCatalyst")
        elif mode == MODE_STYXNET:
            self.target.setPlaceholderText("Query for the WinterGate engine pool")
        else:
            self.target.setPlaceholderText(
                "Target: name, username, domain, or phrase")

    def _panel_mode_changed(self, mode: str) -> None:
        index = self.mode.findText(mode)
        if index >= 0 and self.mode.currentIndex() != index:
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(index)
            self.mode.blockSignals(False)
        self._mode_changed(mode)

    def _sync_panel_mode(self, mode: str) -> None:
        index = self.case_panel.mode.findText(mode)
        if index >= 0 and self.case_panel.mode.currentIndex() != index:
            # The panel updates its own groups and echoes the mode back.
            self.case_panel.mode.setCurrentIndex(index)
        self._mode_changed(mode)

    def _update_key_pills(self) -> None:
        status = backend.key_status()
        self.key_pill.setText(status)
        self.key_pill.set_kind("good" if backend.styxnet.load_key() else "")
        self.case_panel.set_key_status(status, bool(backend.styxnet.load_key()))

    def _update_proxy_pill(self) -> None:
        panel = self.case_panel
        if not panel.proxy_toggle.isChecked():
            text, kind = "Proxies off", ""
        else:
            entries = panel.selected_proxies()
            if entries:
                text, kind = f"{len(entries)} proxy endpoint(s)", "warn"
            elif panel.env_proxy.isChecked():
                text, kind = "System proxy", "warn"
            else:
                text, kind = "Proxy pool empty", "warn"
        self.proxy_pill.setText(text)
        self.proxy_pill.set_kind(kind)

    def install_shortcut(self) -> None:
        try:
            created = backend.create_shortcuts()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Shortcut not created", str(exc))
            return
        self.activity.append_event(
            "Shortcuts: " + ", ".join(path.name for path in created))
        QMessageBox.information(
            self, "Shortcut created",
            "Desktop and Start menu shortcuts now point at this build.")

    def _set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.target.setEnabled(not running)
        self.mode.setEnabled(not running)
        self.case_panel.set_running(running)
        self.act_run.setEnabled(not running)
        self.act_stop.setEnabled(running)
        self.progress.setVisible(running)
        if running:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)

    def _build_request(self) -> InvestigationRequest:
        panel = self.case_panel
        formats = panel.selected_formats()
        mode = self.mode.currentText()
        if mode == MODE_SEARCH and not panel.selected_engines():
            raise ValueError("Choose at least one engine.")
        if mode == MODE_STYXNET and not panel.selected_scopes():
            raise ValueError("Choose at least one StyxNet scope.")
        proxies = panel.selected_proxies()
        if panel.proxy_toggle.isChecked() and not proxies \
                and not panel.env_proxy.isChecked():
            raise ValueError(
                "Proxy pool is enabled but empty. Add an endpoint or turn it off.")
        since = panel.since.date().toString("yyyy-MM-dd") \
            if panel.date_toggle.isChecked() and mode == MODE_SEARCH else ""
        until = panel.until.date().toString("yyyy-MM-dd") \
            if panel.date_toggle.isChecked() and mode == MODE_SEARCH else ""
        return InvestigationRequest(
            mode=mode,
            target=self.target.text().strip(),
            engines=panel.selected_engines() or ("duckduckgo", "bing"),
            max_results=panel.max_results.value(),
            language=panel.language.text().strip(),
            country=panel.country.text().strip(),
            since=since,
            until=until,
            out_dir=Path(panel.out_dir.text().strip() or _default_cases_dir()),
            formats=formats,
            proxies=proxies,
            use_env_proxy=panel.proxy_toggle.isChecked() and panel.env_proxy.isChecked(),
            scan_pages=panel.scan_pages.isChecked(),
            scan_limit=panel.scan_limit.value(),
            concurrency=panel.concurrency.value(),
            include_all=panel.include_all.isChecked(),
            styxnet_engines=panel.styxnet_engines.value(),
            styxnet_scopes=panel.selected_scopes(),
        )

    def _inspect_selection(self, table: DataTable) -> None:
        if table is self.results_table:
            record = self._selected_record()
            if record:
                self.inspector.show_result(record)
        else:
            profile = self._selected_profile()
            if profile:
                self.inspector.show_profile(profile)

    def _selected_record(self) -> dict[str, Any] | None:
        return self.results_table.selected_payload()

    def _selected_profile(self) -> dict[str, Any] | None:
        return self.profiles_table.selected_payload()

    # ---------------------------------------------------------------- run
    def run_investigation(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        try:
            request = self._build_request()
            if not request.target:
                raise ValueError("Enter a target first.")
        except ValueError as exc:
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, "Cannot start", str(exc))
            return

        self.payload = None
        self.results_table.setRowCount(0)
        self.profiles_table.setRowCount(0)
        self.results_caption.setText("No results yet.")
        self.profiles_caption.setText("No profiles yet.")
        self.inspector.clear()
        self.overview.reset()
        self.activity.append_event(f"--- {request.mode}: {request.target} ---")
        self.tabs.setCurrentWidget(self.overview)
        self.status_label.setText("Running...")
        self._set_running(True)

        worker = backend.InvestigationWorker(request, self)
        worker.log.connect(self.activity.append_event)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        self.worker = worker
        worker.start()

    def _on_progress(self, done: int, total: int) -> None:
        if total <= 0:
            self.progress.setRange(0, 0)
            return
        self.progress.setRange(0, total)
        self.progress.setValue(min(done, total))
        self.status_label.setText(f"Running... {done}/{total}")

    def _on_finished(self, payload: dict[str, Any]) -> None:
        self._set_running(False)
        self.worker = None
        self.payload = payload
        self.overview.load(payload)
        mode = payload.get("mode")
        if mode == MODE_USERNAME:
            self._load_username(payload)
        else:
            self._load_search(payload)
        summary = payload.get("summary") or {}
        if mode == MODE_USERNAME:
            parts = [("checked", "checked"), ("found", "matched"),
                     ("errors", "errors")]
        else:
            parts = [("results", "results"), ("profiles", "profiles"),
                     ("engines", "engines")]
        fragments = []
        for key, label in parts:
            value = summary.get(key)
            if key == "engines":
                value = summary.get("styxnet_meta", {}).get("engines") or (
                    len(value) if isinstance(value, list) else value)
            if value is None:
                continue
            if isinstance(value, list):
                value = len(value)
            fragments.append(f"{label}: {value}")
        self.status_label.setText(" | ".join(fragments) or "Done")
        self._update_key_pills()
        paths = payload.get("paths") or {}
        if paths:
            self.activity.append_event(
                "Reports written: " + ", ".join(Path(p).name for p in paths.values()))
        self.act_open.setEnabled(bool(paths))

    def _on_failed(self, message: str) -> None:
        self._set_running(False)
        self.worker = None
        self.status_label.setText("Stopped." if message.startswith("Stopped") else "Failed.")
        self.activity.append_event(f"error  {message}")
        if message.startswith("Stopped"):
            return
        QMessageBox.warning(self, "Investigation failed", message)

    def _load_search(self, payload: dict[str, Any]) -> None:
        records = payload.get("results") or []
        profiles = payload.get("profiles") or []
        profile_map = {
            str(profile.get("profile_url") or ""): str(
                profile.get("platform") or "profile")
            for profile in profiles
            if profile.get("profile_url")
        }
        self.results_table.set_signal_mode(False)
        self.results_table.load(records, profile_map)
        self.profiles_table.load(profiles)
        known = {url.rstrip("/").casefold() for url in profile_map}
        resolved = sum(
            1 for record in records
            if str(record.get("url") or "").rstrip("/").casefold() in known)
        summary = payload.get("summary") or {}
        scanned = int(summary.get("scanned") or 0)
        page_matches = int(summary.get("page_matches") or 0)
        # Once pages have been read, the Signal column is more useful than the
        # engine name: it says what the page itself proved.
        self.results_table.set_signal_mode(bool(scanned))
        self.results_caption.setText(
            f"{len(records)} result(s) · {resolved} resolved to a profile · "
            f"{scanned} page(s) inspected · {page_matches} page match(es) · "
            f"{len(payload.get('errors') or [])} warning(s)")
        if payload.get("mode") == MODE_STYXNET:
            meta = summary.get("styxnet_meta") or {}
            self.profiles_caption.setText(
                f"{len(profiles)} candidate profile(s) · "
                f"{meta.get('engines', '?')} engines · "
                f"archive {meta.get('archive_id', 'n/a')} · "
                "candidates are unverified")
        else:
            self.profiles_caption.setText(
                f"{len(profiles)} detected profile(s) · "
                f"{page_matches} confirmed by page evidence")
        self.tabs.setCurrentWidget(self.overview)

    def _load_username(self, payload: dict[str, Any]) -> None:
        profiles = payload.get("profiles") or []
        hits = payload.get("hits") or []
        self.profiles_table.load(profiles)
        # The Results tab lists every checked template, so an operator can see
        # what was rejected as well as what matched.
        records = []
        for index, hit in enumerate(hits, start=1):
            signal = hit.get("match") or (
                "error" if hit.get("error") else "checked")
            records.append({
                "position": index,
                "engine": signal,
                "signal": signal,
                "signal_mode": True,
                "matched": bool(hit.get("matched")),
                "error": hit.get("error") or "",
                "status": hit.get("status") or 0,
                "confidence": hit.get("confidence") or 0,
                "platform": hit.get("platform") or "",
                "profile_platform": hit.get("platform")
                if hit.get("matched") else "",
                "title": hit.get("platform") or hit.get("url") or "",
                "url": hit.get("url") or "",
                "snippet": hit.get("title") or hit.get("error") or "",
            })
        self.results_table.set_signal_mode(True)
        self.results_table.load(records)
        summary = payload.get("summary") or {}
        self.results_caption.setText(
            f"{summary.get('checked', 0)} checked · "
            f"{summary.get('found', 0)} matched · "
            f"{summary.get('errors', 0)} error(s) · "
            "✓ detected · ✗ error · · checked")
        self.profiles_caption.setText(
            f"{len(profiles)} detected profile(s) · "
            "signal shows how each one was confirmed")
        self.tabs.setCurrentWidget(self.overview)

    # --------------------------------------------------------------- actions
    def stop_investigation(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.status_label.setText("Stopping...")
            self.activity.append_event("stop requested")
            self.worker.cancel()

    def open_output(self) -> None:
        if not self.payload:
            return
        paths = self.payload.get("paths") or {}
        if not paths:
            return
        folder = Path(next(iter(paths.values()))).parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def open_settings(self) -> None:
        dialog = SettingsDialog(self)
        dialog.exec()
        self._update_key_pills()

    def open_doctor(self) -> None:
        DoctorDialog(self).exec()
        self._update_key_pills()

    def open_about(self) -> None:
        AboutDialog(self).exec()

    def open_signals(self) -> None:
        SignalsDialog(self).exec()

    def clear_session(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        self.payload = None
        self.target.clear()
        self.results_table.setRowCount(0)
        self.profiles_table.setRowCount(0)
        self.activity.clear_log()
        self.inspector.clear()
        self.overview.clear()
        self.tabs.setCurrentWidget(self.overview)
        self.results_caption.setText("No results yet.")
        self.profiles_caption.setText("No profiles yet.")
        self.status_label.setText("Ready")

    def _show_result(self, record: dict[str, Any]) -> None:
        self.inspector.show_result(record)
        self.tabs.setCurrentWidget(self.results_tab)
        self._select_matching(self.results_table, record.get("url"))

    def _show_profile(self, profile: dict[str, Any]) -> None:
        self.inspector.show_profile(profile)
        self.tabs.setCurrentWidget(self.profiles_tab)
        self._select_matching(self.profiles_table, profile.get("profile_url"))

    def _select_matching(self, table: DataTable, url: object) -> None:
        if not url:
            return
        for row in range(table.rowCount()):
            item = table.item(row, table.link_column)
            if item is not None and item.data(Qt.UserRole + 1) == url:
                table.selectRow(row)
                table.scrollToItem(item)
                return

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt name
        if self.worker is not None and self.worker.isRunning():
            answer = QMessageBox.question(
                self, "Run in progress",
                "An investigation is still running. Stop it and exit?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.worker.wait(5000)
        self._save_window()
        event.accept()
