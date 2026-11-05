"""Reusable widgets for the investigation workstation."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from . import theme


def _esc(value: object) -> str:
    return html.escape(str(value or ""))


# How a profile was detected. The label is what the operator sees, the note is
# the plain-language explanation shown in the inspector, and the strength
# decides the tint used in tables.
SIGNALS: dict[str, dict[str, str]] = {
    "metadata": {
        "label": "Page metadata",
        "color": theme.GLOW,
        "strength": "strong",
        "note": ("The page's title or Open Graph metadata named this handle, "
                 "and the handle matched at a word boundary."),
    },
    "canonical": {
        "label": "Canonical URL",
        "color": theme.GREEN,
        "strength": "strong",
        "note": ("The canonical URL declared by the page points at this "
                 "handle, which a soft 404 would not do."),
    },
    "redirect": {
        "label": "Redirect",
        "color": theme.EMBER,
        "strength": "strong",
        "note": ("The platform redirected the template URL to this handle's "
                 "profile instead of returning a not-found page."),
    },
    "structured": {
        "label": "Structured data",
        "color": theme.VIOLET,
        "strength": "strong",
        "note": ("JSON-LD or another structured block on the page identified "
                 "this handle as the profile owner."),
    },
    "body": {
        "label": "Page content",
        "color": "#8db8ff",
        "strength": "medium",
        "note": ("The handle appears in the page's visible profile content, "
                 "not only in a footer or a mention."),
    },
    "url": {
        "label": "URL pattern",
        "color": theme.MUTED,
        "strength": "medium",
        "note": ("Detected from the URL shape using the platform registry. "
                 "The page itself was not inspected for this lead."),
    },
    "registry": {
        "label": "Platform registry",
        "color": theme.INK,
        "strength": "medium",
        "note": "Matched a host and path shape in the curated platform registry.",
    },
    "styxnet": {
        "label": "StyxNet candidate",
        "color": theme.EMBER,
        "strength": "candidate",
        "note": ("Returned by the StyxNet pool. Treat it as an unverified "
                 "candidate: confidence is capped until the profile is opened."),
    },
    "error": {
        "label": "Request error",
        "color": theme.RED,
        "strength": "error",
        "note": ("The check did not complete, so this template is neither a "
                 "match nor a confirmed absence. Retry before drawing a "
                 "conclusion."),
    },
    "checked": {
        "label": "No match",
        "color": theme.MUTED,
        "strength": "none",
        "note": ("The page loaded but no visible or metadata signal matched "
                 "the handle, so it is treated as a miss."),
    },
    "": {
        "label": "Unconfirmed",
        "color": theme.MUTED,
        "strength": "none",
        "note": "No detection signal was recorded for this row.",
    },
}

TONE_BACKGROUNDS = {
    "strong": "#0e2a22",
    "medium": "#10243f",
    "candidate": "#2a2110",
    "error": "#2a1420",
    "none": "",
}


def signal_key(value: object) -> str:
    key = str(value or "").strip().lower()
    return key if key in SIGNALS else ""


def signal_label(value: object) -> str:
    return SIGNALS[signal_key(value)]["label"]


def signal_color(value: object) -> str:
    return SIGNALS[signal_key(value)]["color"]


def signal_note(value: object) -> str:
    return SIGNALS[signal_key(value)]["note"]


def signal_strength(value: object) -> str:
    return SIGNALS[signal_key(value)]["strength"]


def profile_signal(profile: dict[str, Any]) -> str:
    """Pick the detection signal for a profile from any payload shape."""
    for key in ("match", "source"):
        key_value = signal_key(profile.get(key))
        if key_value:
            return key_value
    return "url" if profile.get("profile_url") else ""


def tone_background(strength: str) -> str:
    return TONE_BACKGROUNDS.get(strength, "")


class ConfidenceMeter(QWidget):
    """Small labelled bar that makes a confidence score readable at a glance."""

    def __init__(self, value: int = 0, color: str = theme.GREEN,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QProgressBar

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(max(0, min(100, int(value))))
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: {theme.BG}; border: 1px solid "
            f"{theme.LINE}; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}")
        self.value_label = QLabel(f"{int(value)}%")
        self.value_label.setStyleSheet(
            f"color: {color}; font-weight: 700; font-size: 9pt;")
        self.value_label.setFixedWidth(40)
        layout.addWidget(self.bar, 1)
        layout.addWidget(self.value_label)



class Pill(QLabel):
    def __init__(self, text: str = "", kind: str = "") -> None:
        super().__init__(text)
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        name = {"good": "PillGood", "warn": "PillWarn"}.get(kind, "Pill")
        self.setObjectName(name)
        self.style().unpolish(self)
        self.style().polish(self)


class MetricCard(QFrame):
    def __init__(self, label: str, value: str = "0",
                 accent: str = theme.GREEN) -> None:
        super().__init__()
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(2)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("CardValue")
        self.value_label.setStyleSheet(f"color: {accent};")
        self.label = QLabel(label)
        self.label.setObjectName("CardLabel")
        layout.addWidget(self.value_label)
        layout.addWidget(self.label)
        self.setMinimumHeight(86)

    def set_value(self, value: object) -> None:
        self.value_label.setText(str(value))


class SectionTitle(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setObjectName("SectionLabel")


class Hairline(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Hairline")
        self.setFixedHeight(1)


class SortItem(QTableWidgetItem):
    """A cell that sorts by a hidden value instead of its display text."""

    def __init__(self, text: object, sort_value: object = None) -> None:
        super().__init__(str(text if text is not None else ""))
        value = sort_value if sort_value is not None else text
        if not isinstance(value, (int, float)):
            value = str(value).casefold()
        self.setData(Qt.UserRole, value)

    def __lt__(self, other: QTableWidgetItem) -> bool:  # type: ignore[override]
        mine = self.data(Qt.UserRole)
        theirs = other.data(Qt.UserRole)
        if isinstance(mine, (int, float)) and isinstance(theirs, (int, float)):
            return mine < theirs
        return str(mine) < str(theirs)


class DataTable(QTableWidget):
    """Read-only, sortable table with a link column."""

    link_column = -1
    stretch_column = -1
    default_sort: tuple[int, Qt.SortOrder] | None = None
    allow_sorting = True

    def __init__(self, headers: list[str], widths: dict[int, int] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setWordWrap(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(42)
        self.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.setSortingEnabled(self.allow_sorting)
        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(False)
        for index, width in (widths or {}).items():
            self.setColumnWidth(index, width)
        if self.stretch_column >= 0:
            header.setSectionResizeMode(
                self.stretch_column, QHeaderView.Stretch)
        self.itemDoubleClicked.connect(self._open_row)

    def _open_row(self, item: QTableWidgetItem) -> None:
        url = ""
        if self.link_column >= 0:
            url_item = self.item(item.row(), self.link_column)
            if url_item is not None:
                url = url_item.data(Qt.UserRole + 1) or ""
        if not url:
            url = item.data(Qt.UserRole + 1) or ""
        if url:
            QDesktopServices.openUrl(QUrl(str(url)))

    def link_cell(self, text: str, url: str) -> QTableWidgetItem:
        item = SortItem(text, text)
        item.setData(Qt.UserRole + 1, url)
        item.setForeground(QColor("#8db8ff"))
        item.setToolTip(url)
        return item

    def fill(self, rows: list[list[QTableWidgetItem]]) -> None:
        self.setSortingEnabled(False)
        self.setRowCount(0)
        for values in rows:
            row = self.rowCount()
            self.insertRow(row)
            for column, item in enumerate(values):
                self.setItem(row, column, item)
        # Enabling sorting immediately applies the header's indicator, so the
        # default order has to be set afterwards or every fresh payload would
        # arrive in whatever order the last click left behind.
        self.setSortingEnabled(self.allow_sorting)
        if self.allow_sorting and self.default_sort is not None:
            column, order = self.default_sort
            self.horizontalHeader().setSortIndicator(column, order)
            self.sortItems(column, order)
        self.resizeRowsToContents()

    def selected_url(self) -> str:
        items = self.selectedItems()
        if not items:
            return ""
        row = items[0].row()
        if self.link_column >= 0:
            item = self.item(row, self.link_column)
            if item is not None:
                return str(item.data(Qt.UserRole + 1) or "")
        return ""

    def row_payload(self, row: int) -> dict[str, Any] | None:
        item = self.item(row, 0)
        if item is None:
            return None
        data = item.data(Qt.UserRole + 2)
        return data if isinstance(data, dict) else None

    def selected_payload(self) -> dict[str, Any] | None:
        items = self.selectedItems()
        if not items:
            return None
        return self.row_payload(items[0].row())


class ResultsTable(DataTable):
    link_column = 2
    stretch_column = 2
    default_sort = (0, Qt.AscendingOrder)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(["#", "Engine", "Result", "Snippet"],
                         {0: 46, 1: 132, 3: 360}, parent)
        self._signal_mode = False

    @staticmethod
    def _normalise(url: object) -> str:
        return str(url or "").strip().rstrip("/").casefold()

    def set_signal_mode(self, enabled: bool) -> None:
        """Relabel the columns when rows describe checks, not engines."""
        self._signal_mode = bool(enabled)
        labels = (["#", "Signal", "Checked URL", "Detail"] if enabled
                  else ["#", "Engine", "Result", "Snippet"])
        self.setHorizontalHeaderLabels(labels)

    def load(self, records: list[dict[str, Any]],
             profile_map: dict[str, str] | None = None) -> None:
        """Fill the table and mark rows that are detected profiles.

        ``profile_map`` maps a normalised URL to a platform name. A search
        result that resolves to a known profile is marked with a diamond so a
        run reads as intelligence instead of a list of links.
        """
        profiles = {self._normalise(url): name
                    for url, name in (profile_map or {}).items()}
        rows = []
        for record in records:
            url = str(record.get("url") or "")
            normalised = self._normalise(url)
            platform = (profiles.get(normalised, "")
                        or str(record.get("profile_platform") or ""))
            signal = signal_key(record.get("signal"))
            matched = bool(record.get("matched"))
            errored = bool(record.get("error"))

            position = SortItem(int(record.get("position") or 0))
            position.setTextAlignment(Qt.AlignCenter)

            if signal:
                engine_text = signal_label(signal)
                engine = SortItem(engine_text, engine_text)
                engine.setForeground(QColor(signal_color(signal)))
                engine.setToolTip(signal_note(signal))
            else:
                engine_text = str(record.get("engine") or "web")
                engine = SortItem(engine_text, engine_text)

            title = str(record.get("title") or url)
            if matched:
                title = "✓ " + title
            elif errored:
                title = "✗ " + title
            elif platform:
                title = "◆ " + title
            elif signal:
                title = "· " + title

            title_item = self.link_cell(title, url)
            if matched:
                title_item.setForeground(QColor(theme.GREEN))
            elif errored:
                title_item.setForeground(QColor(theme.RED))
            elif platform:
                title_item.setForeground(QColor(theme.GLOW))
            elif signal:
                title_item.setForeground(QColor(signal_color(signal)))
            if platform:
                title_item.setToolTip(
                    f"{url}\n\nDetected {platform} profile")

            snippet = SortItem(record.get("detail")
                               or record.get("snippet") or "")
            snippet.setForeground(QColor(theme.MUTED))
            cells = [position, engine, title_item, snippet]

            # Tint by the strength of the evidence. A checked miss stays
            # neutral so confirmed rows are the ones that stand out.
            if errored:
                strength = "error"
            elif matched:
                strength = "strong"
            elif signal:
                strength = signal_strength(signal)
            elif platform:
                strength = "strong"
            else:
                strength = ""
            tint = tone_background(strength)
            if tint:
                for cell in cells:
                    cell.setBackground(QBrush(QColor(tint)))
            stored = {**record, "profile_platform": platform,
                      "signal_mode": self._signal_mode}
            cells[0].setData(Qt.UserRole + 2, stored)
            rows.append(cells)
        self.fill(rows)


class ProfilesTable(DataTable):
    link_column = 3
    stretch_column = 3
    default_sort = (4, Qt.DescendingOrder)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(["Platform", "Category", "Signal", "Profile", "Conf."],
                         {0: 140, 1: 96, 2: 150, 4: 64}, parent)

    def load(self, profiles: list[dict[str, Any]]) -> None:
        rows = []
        for profile in profiles:
            signal = profile_signal(profile)
            strength = signal_strength(signal)
            signal_item = SortItem(signal_label(signal), signal)
            signal_item.setForeground(QColor(signal_color(signal)))
            signal_item.setToolTip(signal_note(signal))
            if tone_background(strength):
                signal_item.setBackground(QBrush(
                    QColor(tone_background(strength))))

            confidence = int(profile.get("confidence") or 0)
            confidence_item = SortItem(
                "—" if confidence <= 0 else confidence, confidence)
            confidence_item.setTextAlignment(Qt.AlignCenter)
            if confidence <= 0:
                confidence_item.setToolTip(
                    "No confidence was recorded for this host.")
            confidence_item.setForeground(QColor(
                theme.GREEN if confidence >= 85
                else theme.GLOW if confidence >= 70
                else theme.EMBER if confidence >= 50 else theme.MUTED))
            font = confidence_item.font()
            font.setBold(True)
            confidence_item.setFont(font)
            if tone_background(strength):
                confidence_item.setBackground(QBrush(
                    QColor(tone_background(strength))))

            cells = [
                SortItem(profile.get("platform") or "Unknown",
                         profile.get("platform") or ""),
                SortItem(profile.get("category") or "other",
                         profile.get("category") or ""),
                signal_item,
                self.link_cell(str(profile.get("profile_url") or ""),
                               str(profile.get("profile_url") or "")),
                confidence_item,
            ]
            cells[0].setData(Qt.UserRole + 2, profile)
            rows.append(cells)
        self.fill(rows)



class ActivityView(QPlainTextEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setMaximumBlockCount(5000)
        self.setPlaceholderText("Activity appears here.")

    def append_event(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.appendPlainText(f"{stamp}  {message}")

    def clear_log(self) -> None:
        self.clear()


class Inspector(QFrame):
    """Right-hand detail panel for the selected row."""

    openRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Inspector")
        self.setMinimumWidth(280)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)
        outer.addWidget(SectionTitle("Inspector"))

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.viewport().setAutoFillBackground(False)
        self.body = QWidget()
        self.body.setObjectName("InspectorBody")
        self.body.setAutoFillBackground(False)
        self.layout_body = QVBoxLayout(self.body)
        self.layout_body.setContentsMargins(0, 0, 0, 0)
        self.layout_body.setSpacing(8)
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll, 1)

        self.open_button = QPushButton("Open in default browser")
        self.open_button.setObjectName("Primary")
        self.open_button.clicked.connect(self._open)
        self.open_button.setEnabled(False)
        outer.addWidget(self.open_button)

        self._url = ""
        self.clear()

    def _clear_body(self) -> None:
        while self.layout_body.count():
            item = self.layout_body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def clear(self) -> None:
        self._clear_body()
        self._url = ""
        hint = QLabel("Select a result or a profile to inspect it.\n\n"
                      "Double-click any row to open its link.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        self.layout_body.addWidget(hint)
        self.layout_body.addStretch(1)
        self.open_button.setEnabled(False)

    def _label(self, text: str, name: str = "") -> QLabel:
        label = QLabel(text)
        if name:
            label.setObjectName(name)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return label

    def _meta_row(self, key: str, value: object) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        name = QLabel(key)
        name.setObjectName("Hint")
        name.setFixedWidth(86)
        value_label = self._label(str(value or "-"))
        row.addWidget(name)
        row.addWidget(value_label, 1)
        wrapper = QWidget()
        wrapper.setLayout(row)
        self.layout_body.addWidget(wrapper)

    def _badges(self, pills: list[QLabel]) -> None:
        row = QHBoxLayout()
        row.setSpacing(6)
        for pill in pills:
            row.addWidget(pill)
        row.addStretch(1)
        wrapper = QWidget()
        wrapper.setLayout(row)
        self.layout_body.addWidget(wrapper)

    def _signal_pill(self, signal: str) -> QLabel:
        color = signal_color(signal)
        background = tone_background(signal_strength(signal)) or theme.PANEL_ALT
        pill = Pill(signal_label(signal))
        pill.setStyleSheet(
            f"color: {color}; border: 1px solid {color};"
            f" background: {background}; border-radius: 9px;"
            f" padding: 2px 8px; font-size: 8pt;")
        pill.setToolTip(signal_note(signal))
        return pill

    def _title_label(self, text: str) -> QLabel:
        label = self._label(text)
        font = label.font()
        font.setPointSize(font.pointSize() + 4)
        font.setBold(True)
        label.setFont(font)
        return label

    def _show_signal_note(self, signal: str) -> None:
        if not signal:
            return
        self.layout_body.addWidget(SectionTitle("Why this lead"))
        note = QLabel(signal_note(signal))
        note.setObjectName("Hint")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {signal_color(signal)};")
        self.layout_body.addWidget(note)

    def show_result(self, record: dict[str, Any]) -> None:
        self._clear_body()
        url = str(record.get("url") or "")
        self._url = url
        signal = signal_key(record.get("signal"))
        platform = str(record.get("profile_platform") or "")
        if platform and not signal:
            signal = "url"
        errored = bool(record.get("error"))

        if errored:
            eyebrow = "REQUEST ERROR"
        elif platform:
            eyebrow = "DETECTED PROFILE"
        elif signal:
            eyebrow = signal_label(signal).upper()
        else:
            eyebrow = str(record.get("engine") or "web").upper()
        eyebrow_label = self._label(eyebrow, "Eyebrow")
        eyebrow_label.setStyleSheet(
            f"color: {theme.RED if errored else theme.EMBER};")
        self.layout_body.addWidget(eyebrow_label)

        title_text = str(record.get("title") or url)
        if title_text.startswith(("✓ ", "✗ ", "◆ ", "· ")):
            title_text = title_text[2:]
        self.layout_body.addWidget(self._title_label(title_text))
        link = self._label(f"<a href=\"{_esc(url)}\" style='color:#8db8ff'>{_esc(url)}</a>")
        link.setOpenExternalLinks(True)
        self.layout_body.addWidget(link)

        pills: list[QLabel] = []
        if platform:
            pills.append(Pill(f"◆ {platform}", "good"))
        if signal:
            pills.append(self._signal_pill(signal))
        if pills:
            self._badges(pills)

        self.layout_body.addWidget(Hairline())
        self._meta_row("Position", record.get("position"))
        if not record.get("signal_mode"):
            self._meta_row("Engine", record.get("engine"))
        if signal:
            self._meta_row("Signal", signal_label(signal))
        if platform:
            self._meta_row("Profile", platform)
        if record.get("status"):
            self._meta_row("HTTP", record.get("status"))
        final_url = str(record.get("final_url") or "")
        if final_url and final_url.rstrip("/") != url.rstrip("/"):
            self._meta_row("Resolved", final_url)
        if errored:
            self.layout_body.addWidget(SectionTitle("Error"))
            error_label = QLabel(str(record.get("error")))
            error_label.setObjectName("Hint")
            error_label.setWordWrap(True)
            error_label.setStyleSheet(f"color: {theme.RED};")
            self.layout_body.addWidget(error_label)

        page_title = str(record.get("page_title") or "")
        if page_title and page_title != str(record.get("title") or ""):
            self.layout_body.addWidget(SectionTitle("Page title"))
            self.layout_body.addWidget(self._label(page_title, "Hint"))
        detail = str(record.get("detail") or "")
        if detail:
            self.layout_body.addWidget(SectionTitle("Page evidence"))
            self.layout_body.addWidget(self._label(detail, "Hint"))

        snippet_text = str(record.get("snippet") or "")
        if snippet_text:
            self.layout_body.addWidget(SectionTitle("Snippet"))
            self.layout_body.addWidget(self._label(snippet_text, "Hint"))
        self._show_signal_note(signal)
        self.layout_body.addStretch(1)
        self.open_button.setEnabled(bool(url))

    def show_profile(self, profile: dict[str, Any]) -> None:
        self._clear_body()
        url = str(profile.get("profile_url") or "")
        self._url = url
        signal = profile_signal(profile)
        strength = signal_strength(signal)
        confidence = int(profile.get("confidence") or 0)
        candidate = strength == "candidate"

        eyebrow = self._label(
            "CANDIDATE PROFILE" if candidate else "PROFILE DETECTED",
            "Eyebrow")
        eyebrow.setStyleSheet(
            f"color: {theme.EMBER if candidate else theme.GREEN};")
        self.layout_body.addWidget(eyebrow)
        self.layout_body.addWidget(self._title_label(
            str(profile.get("platform") or "Unknown platform")))
        link = self._label(f"<a href=\"{_esc(url)}\" style='color:#8db8ff'>{_esc(url)}</a>")
        link.setOpenExternalLinks(True)
        self.layout_body.addWidget(link)

        verdict = (Pill("CANDIDATE", "warn") if candidate
                   else Pill("DETECTED", "good") if confidence >= 70
                   else Pill("WEAK MATCH", "warn"))
        self._badges([verdict, self._signal_pill(signal)])

        self.layout_body.addWidget(Hairline())
        self.layout_body.addWidget(SectionTitle("Confidence"))
        meter_color = (theme.EMBER if candidate
                       else theme.GREEN if confidence >= 85
                       else theme.GLOW if confidence >= 70
                       else theme.MUTED)
        self.layout_body.addWidget(ConfidenceMeter(confidence, meter_color))

        self._meta_row("Category", profile.get("category"))
        if profile.get("status"):
            self._meta_row("HTTP", profile.get("status"))
        title_text = str(profile.get("title") or "")
        if title_text:
            self.layout_body.addWidget(SectionTitle("Page title"))
            self.layout_body.addWidget(self._label(title_text, "Hint"))
        description = str(profile.get("description") or "")
        if description:
            self.layout_body.addWidget(SectionTitle("Description"))
            self.layout_body.addWidget(self._label(description, "Hint"))
        self._show_signal_note(signal)
        self.layout_body.addStretch(1)
        self.open_button.setEnabled(bool(url))


    def _open(self) -> None:
        if self._url:
            QDesktopServices.openUrl(QUrl(self._url))


class EmptyState(QWidget):
    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName("PageTitle")
        text = QLabel(body)
        text.setObjectName("Hint")
        text.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(text)
        layout.addStretch(1)
