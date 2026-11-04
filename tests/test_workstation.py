"""Workstation backend and window smoke tests (headless Qt)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

pytest.importorskip(
    "PySide6.QtCore",
    reason="PySide6 is an optional GUI dependency; install it to run workstation tests.",
    exc_type=ImportError,
)

from PySide6.QtCore import Qt

from ominis_src import report, styxnet, username

from ominis_workstation import backend


class MemorySettings:
    """Stand-in for QSettings so tests never touch the registry."""

    def __init__(self, *args, **kwargs) -> None:
        self.data: dict[str, object] = {}

    def value(self, key, default=None, type=None):  # noqa: A002
        value = self.data.get(key, default)
        if value is None:
            return default
        if type is bool:
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {"1", "true", "yes", "on"}
        if type is int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
        if type is str:
            return str(value)
        return value

    def setValue(self, key, value) -> None:
        self.data[key] = value

    def restoreGeometry(self, *_args):
        return None

    def saveGeometry(self):
        return b""


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


def _search_report() -> report.SearchReport:
    outcome = report.SearchReport(query="acme", engines=["duckduckgo", "bing"])
    outcome.records = [
        report.SearchRecord(title="Acme", url="https://acme.example/",
                            engine="duckduckgo", snippet="official", position=1),
        report.SearchRecord(title="Acme GitHub", url="https://github.com/acme",
                            engine="bing", snippet="code", position=2),
    ]
    outcome.profiles = [
        {"platform": "GitHub", "profile_url": "https://github.com/acme",
         "category": "dev", "confidence": 90},
        {"platform": "X (Twitter)", "profile_url": "https://x.com/acme",
         "category": "social", "confidence": 90},
    ]
    outcome.mentions = {"acme": 4}
    return outcome


def _username_report() -> username.UsernameReport:
    outcome = username.UsernameReport(username="acme")
    outcome.hits = [
        username.Hit(username="acme", url="https://github.com/acme", status=200,
                     title="acme on GitHub", matched=True, match="metadata",
                     platform="GitHub", category="dev", confidence=90),
        username.Hit(username="acme", url="https://gone.example/acme", status=404,
                     error="HTTP 404"),
    ]
    return outcome


def test_request_defaults_keep_proxies_off():
    request = backend.InvestigationRequest(target="acme")
    assert request.engines == ("duckduckgo", "bing")
    assert request.mode == backend.MODE_SEARCH
    assert request.styxnet_key == ""


def test_build_settings_uses_request_values():
    request = backend.InvestigationRequest(
        target="acme", language="de", max_results=12,
        formats=("json",), out_dir=Path("cases"))
    settings = backend.build_settings(request)
    assert settings.query == "acme"
    assert settings.language == "de"
    assert settings.max_results == 12
    assert settings.formats == ("json",)
    assert settings.styxnet is False
    assert settings.proxies == ()


def test_build_settings_requires_a_styxnet_key(monkeypatch):
    monkeypatch.setattr(styxnet, "load_key", lambda explicit="": "")
    request = backend.InvestigationRequest(
        target="acme", mode=backend.MODE_STYXNET)
    with pytest.raises(ValueError, match="StyxNet access"):
        backend.build_settings(request)


def test_build_settings_resolves_a_saved_key(monkeypatch):
    monkeypatch.setattr(styxnet, "load_key",
                        lambda explicit="": "sgn_" + "a" * 40)
    request = backend.InvestigationRequest(
        target="acme", mode=backend.MODE_STYXNET)
    settings = backend.build_settings(request)
    assert settings.styxnet is True
    assert settings.styxnet_key.startswith("sgn_")


def test_search_payload_keeps_summary_and_profiles():
    payload = backend.search_payload(_search_report(), {"json": "acme.json"}, 1234)
    assert payload["summary"]["results"] == 2
    assert payload["summary"]["profiles"] == 2
    assert payload["elapsed_ms"] == 1234
    assert payload["results"][0]["url"] == "https://acme.example/"
    assert payload["profiles"][0]["platform"] == "GitHub"


def test_username_payload_keeps_signals_and_errors():
    payload = backend.username_payload(_username_report(), {"txt": "u.txt"}, 99)
    assert payload["summary"] == {"checked": 2, "found": 1, "errors": 1,
                                  "elapsed_ms": 99}
    assert payload["profiles"][0]["platform"] == "GitHub"
    assert payload["profiles"][0]["source"] == "metadata"
    assert payload["errors"][0]["url"] == "https://gone.example/acme"


def test_friendly_error_explains_rejections():
    assert backend.friendly_error(ValueError("Enter a target first.")) == (
        "Enter a target first.")
    assert "StyxNet" in backend.friendly_error(
        styxnet.StyxNetError("StyxNet is unavailable."))
    assert backend.friendly_error(RuntimeError("boom")) == "RuntimeError: boom"


def test_save_key_writes_only_to_the_key_file(monkeypatch, tmp_path):
    target = tmp_path / "styxnet-key.txt"
    monkeypatch.setattr(backend, "key_file", lambda: target)
    key = "sgn_" + "b" * 40
    assert backend.save_key(key) == target
    assert target.read_text(encoding="utf-8") == key
    monkeypatch.setattr(styxnet, "load_key", lambda explicit="": key)
    status = backend.key_status()
    assert "44 characters" in status
    assert key not in status


def test_save_key_rejects_a_malformed_value(monkeypatch, tmp_path):
    monkeypatch.setattr(backend, "key_file", lambda: tmp_path / "k.txt")
    with pytest.raises(ValueError, match="sgn_"):
        backend.save_key("not-a-key")


def test_window_loads_a_search_payload(qapp, monkeypatch):
    from ominis_workstation import main_window
    from ominis_workstation import theme

    monkeypatch.setattr(main_window, "QSettings", MemorySettings)
    window = main_window.MainWindow()
    window.setStyleSheet(theme.STYLESHEET)
    payload = backend.search_payload(_search_report(), {"json": "x.json"}, 1200)
    window._on_finished(payload)
    assert window.results_table.rowCount() == 2
    assert window.profiles_table.rowCount() == 2
    assert window.overview.title.text() == "acme"
    assert window.status_label.text().startswith("results: 2")
    window.close()


def test_window_mode_switch_updates_the_panel(qapp, monkeypatch):
    from ominis_workstation import main_window

    monkeypatch.setattr(main_window, "QSettings", MemorySettings)
    window = main_window.MainWindow()
    window.mode.setCurrentText(backend.MODE_USERNAME)
    assert window.case_panel.mode.currentText() == backend.MODE_USERNAME
    assert window.case_panel.username_group.isVisibleTo(window)
    window.case_panel.mode.setCurrentText(backend.MODE_STYXNET)
    assert window.mode.currentText() == backend.MODE_STYXNET
    assert window.case_panel.styxnet_group.isVisibleTo(window)
    window.close()


def test_sorted_profile_table_keeps_the_right_payload(qapp, monkeypatch):
    from ominis_workstation import main_window

    monkeypatch.setattr(main_window, "QSettings", MemorySettings)
    window = main_window.MainWindow()
    payload = backend.search_payload(_search_report(), {}, 10)
    window._on_finished(payload)
    from PySide6.QtCore import Qt

    window.profiles_table.sortItems(4, Qt.DescendingOrder)
    window.profiles_table.selectRow(0)
    chosen = window.profiles_table.selected_payload()
    assert chosen is not None
    assert chosen["platform"] in {"GitHub", "X (Twitter)"}
    window.close()


def test_signal_helpers_describe_every_detection_type():
    from ominis_workstation import widgets

    for key in ("metadata", "canonical", "redirect", "body", "structured",
                "url", "styxnet", "error", "checked"):
        assert widgets.signal_label(key) != "Unconfirmed"
        assert widgets.signal_note(key)
        assert widgets.signal_color(key).startswith("#")
    assert widgets.signal_label("nonsense") == "Unconfirmed"
    assert widgets.signal_key("METADATA") == "metadata"


def test_profile_signal_prefers_match_then_source():
    from ominis_workstation import widgets

    assert widgets.profile_signal(
        {"match": "canonical", "source": "styxnet"}) == "canonical"
    assert widgets.profile_signal({"source": "styxnet"}) == "styxnet"
    assert widgets.profile_signal(
        {"profile_url": "https://example.com/u"}) == "url"
    assert widgets.profile_signal({}) == ""


def test_results_table_defaults_to_result_order_and_marks_profiles(
        qapp, monkeypatch):
    from ominis_workstation import main_window

    monkeypatch.setattr(main_window, "QSettings", MemorySettings)
    window = main_window.MainWindow()
    records = [
        {"position": 10, "engine": "bing", "title": "Tenth",
         "url": "https://ten.example/", "snippet": ""},
        {"position": 2, "engine": "bing", "title": "Second",
         "url": "https://github.com/acme", "snippet": ""},
        {"position": 1, "engine": "duckduckgo", "title": "First",
         "url": "https://acme.example/", "snippet": ""},
    ]
    profiles = [{"platform": "GitHub",
                 "profile_url": "https://github.com/acme",
                 "category": "dev", "confidence": 90}]
    window.results_table.load(records, {"https://github.com/acme": "GitHub"})
    window.profiles_table.load(profiles)
    # Default order must be numeric position ascending even after a sort.
    assert [window.results_table.item(row, 0).text()
            for row in range(window.results_table.rowCount())] == ["1", "2", "10"]
    marked_row = next(
        row for row in range(window.results_table.rowCount())
        if window.results_table.row_payload(row).get("profile_platform"))
    assert window.results_table.item(marked_row, 2).text().startswith("◆ ")
    assert window.results_table.row_payload(marked_row)[
        "profile_platform"] == "GitHub"
    # Profile signal cell explains how it was detected.
    assert window.profiles_table.item(0, 2).text() == "URL pattern"
    assert window.profiles_table.item(0, 4).text() == "90"
    window.close()


def test_profiles_table_defaults_to_confidence_order(qapp, monkeypatch):
    from ominis_workstation import main_window

    monkeypatch.setattr(main_window, "QSettings", MemorySettings)
    window = main_window.MainWindow()
    window.profiles_table.load([
        {"platform": "Low", "profile_url": "https://low.example/",
         "category": "other", "confidence": 40},
        {"platform": "High", "profile_url": "https://high.example/",
         "category": "dev", "confidence": 95},
        {"platform": "Top", "profile_url": "https://top.example/",
         "category": "dev", "confidence": 100},
    ])
    assert window.profiles_table.item(0, 0).text() == "Top"
    assert window.profiles_table.item(0, 4).text() == "100"
    window.close()


def test_username_rows_use_signal_headers_and_neutral_misses(qapp, monkeypatch):
    from ominis_workstation import main_window, widgets

    monkeypatch.setattr(main_window, "QSettings", MemorySettings)
    window = main_window.MainWindow()
    table = window.results_table
    table.set_signal_mode(True)
    assert table.horizontalHeaderItem(1).text() == "Signal"
    assert table.horizontalHeaderItem(2).text() == "Checked URL"
    table.load([
        {"position": 1, "signal": "structured", "matched": True,
         "profile_platform": "TikTok",
         "title": "TikTok", "url": "https://tiktok.example/@acme"},
        {"position": 2, "signal": "checked", "matched": False,
         "title": "LinkedIn", "url": "https://linkedin.example/acme"},
        {"position": 3, "signal": "error", "error": "timeout",
         "title": "Reddit", "url": "https://reddit.example/acme"},
    ])
    titles = [table.item(row, 2).text() for row in range(table.rowCount())]
    assert titles[0].startswith("✓ ")
    assert titles[1].startswith("· ")
    assert titles[2].startswith("✗ ")
    # A checked miss must not carry the evidence tint used for matches.
    assert table.item(1, 0).background().style() == Qt.NoBrush
    assert table.item(0, 0).background().color().name() == \
        widgets.tone_background("strong")
    assert table.row_payload(0)["signal_mode"] is True
    assert table.row_payload(0)["profile_platform"] == "TikTok"
    window.close()
