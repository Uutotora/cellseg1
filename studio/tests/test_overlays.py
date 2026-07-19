"""Headless wiring tests for studio/overlays.py's LogsConsole -- the real,
live log stream (studio/log_bus.py) rendered with a level filter, text
search, autoscroll, clear, and export. Offscreen Qt only; no napari/torch.

Every test constructs its own private LogBus (never the real
log_bus.get_log_bus() singleton) for isolation, the same convention
test_project_controller.py/test_train_controller.py use tmp_path stores for.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
overlays = pytest.importorskip("studio.overlays")

from PyQt6.QtWidgets import QApplication, QWidget

from studio import theme
from studio.log_bus import LogBus


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def parent(app):
    w = QWidget()
    w.resize(1200, 900)
    w.show()
    return w


@pytest.fixture
def bus():
    return LogBus()


def _console(parent, bus):
    c = overlays.LogsConsole(parent, theme.DARK, bus=bus)
    c.setParent(parent)
    c.resize(760, overlays.LogsConsole.HEIGHT)
    c.show()
    QApplication.processEvents()
    return c


# ── construction / backfill ──────────────────────────────────────────────────
def test_uses_the_injected_bus_not_the_global_singleton(parent, bus):
    from studio.log_bus import get_log_bus
    console = _console(parent, bus)
    assert console._bus is bus
    assert console._bus is not get_log_bus()


def test_backfills_from_bus_history_at_construction(parent, bus):
    bus.info("already here", source="segment")
    console = _console(parent, bus)
    assert "already here" in console._text.toPlainText()
    assert console._badge.text() == "1"


def test_starts_hidden(parent, bus):
    c = overlays.LogsConsole(parent, theme.DARK, bus=bus)
    assert c.isHidden()


# ── live updates ─────────────────────────────────────────────────────────────
def test_new_records_appear_live(parent, bus):
    console = _console(parent, bus)
    bus.info("fresh line", source="segment")
    assert "fresh line" in console._text.toPlainText()
    assert console._badge.text() == "1"


def test_badge_counts_errors_and_warnings(parent, bus):
    console = _console(parent, bus)
    bus.warning("careful")
    bus.error("boom")
    bus.error("boom again")
    assert console._badge.text() == "3 · 2 err · 1 warn"


def test_badge_omits_zero_counts(parent, bus):
    console = _console(parent, bus)
    bus.info("all quiet")
    assert console._badge.text() == "1"


# ── level filter ─────────────────────────────────────────────────────────────
def test_default_filter_hides_debug_but_shows_info(parent, bus):
    bus.debug("noisy breadcrumb")
    bus.info("normal line")
    console = _console(parent, bus)
    text = console._text.toPlainText()
    assert "normal line" in text
    assert "noisy breadcrumb" not in text


def test_level_filter_hides_lines_below_threshold(parent, bus):
    console = _console(parent, bus)
    bus.info("plain info")
    bus.error("a real problem")
    console._on_level_selected("Error")
    text = console._text.toPlainText()
    assert "a real problem" in text
    assert "plain info" not in text
    console._on_level_selected("All")
    text = console._text.toPlainText()
    assert "plain info" in text and "a real problem" in text


def test_level_filter_applies_to_new_live_records_too(parent, bus):
    console = _console(parent, bus)
    console._on_level_selected("Error")
    bus.info("should stay hidden")
    bus.error("should show up")
    text = console._text.toPlainText()
    assert "should show up" in text
    assert "should stay hidden" not in text


# ── text search ──────────────────────────────────────────────────────────────
def test_search_filters_by_message_and_source(parent, bus):
    console = _console(parent, bus)
    bus.info("loading model checkpoint", source="studio.segment")
    bus.info("baking tuned agent", source="studio.assistant")
    console._search.setText("checkpoint")
    text = console._text.toPlainText()
    assert "loading model checkpoint" in text
    assert "baking tuned agent" not in text
    console._search.setText("assistant")
    text = console._text.toPlainText()
    assert "baking tuned agent" in text
    assert "loading model checkpoint" not in text


def test_clearing_the_search_box_restores_everything(parent, bus):
    console = _console(parent, bus)
    bus.info("alpha")
    bus.info("beta")
    console._search.setText("alpha")
    assert "beta" not in console._text.toPlainText()
    console._search.setText("")
    text = console._text.toPlainText()
    assert "alpha" in text and "beta" in text


# ── autoscroll ───────────────────────────────────────────────────────────────
def test_autoscroll_on_by_default_snaps_to_bottom_on_new_lines(parent, bus):
    console = _console(parent, bus)
    assert console._autoscroll.is_on()
    for i in range(60):
        bus.info(f"line {i}")
    sb = console._text.verticalScrollBar()
    assert sb.maximum() > 0
    assert sb.value() == sb.maximum()


def test_autoscroll_off_does_not_move_the_scrollbar(parent, bus):
    console = _console(parent, bus)
    console._autoscroll.set_on(False)
    for i in range(60):
        bus.info(f"line {i}")
    sb = console._text.verticalScrollBar()
    assert sb.maximum() > 0
    sb.setValue(0)
    bus.info("one more after manually scrolling up")
    assert sb.value() == 0


def test_toggling_autoscroll_back_on_jumps_to_bottom_immediately(parent, bus):
    console = _console(parent, bus)
    for i in range(60):
        bus.info(f"line {i}")
    sb = console._text.verticalScrollBar()
    sb.setValue(0)
    console._on_autoscroll_toggled(True)
    assert sb.value() == sb.maximum()


# ── clear ────────────────────────────────────────────────────────────────────
def test_clear_empties_the_view_and_the_bus(parent, bus):
    console = _console(parent, bus)
    bus.info("one")
    bus.error("two")
    console._on_clear()
    assert console._text.toPlainText().strip() == ""
    assert console._badge.text() == "0"
    assert bus.snapshot() == []


# ── export ───────────────────────────────────────────────────────────────────
def test_export_writes_the_currently_filtered_lines(parent, bus, tmp_path, monkeypatch):
    console = _console(parent, bus)
    bus.info("excluded info line")
    bus.error("included error line")
    console._on_level_selected("Error")
    out = tmp_path / "out.txt"
    monkeypatch.setattr(overlays.QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    console._export()
    content = out.read_text()
    assert "included error line" in content
    assert "excluded info line" not in content  # excluded by the active level filter


def test_export_cancelled_writes_nothing(parent, bus, tmp_path, monkeypatch):
    console = _console(parent, bus)
    bus.info("keep me")
    out = tmp_path / "should_not_exist.txt"
    monkeypatch.setattr(overlays.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    console._export()  # must not raise
    assert not out.exists()


# ── cross-thread / teardown safety ──────────────────────────────────────────
def test_safe_emit_record_guards_against_a_deleted_widget(parent, bus):
    from PyQt6 import sip
    console = _console(parent, bus)
    emit = console._safe_emit_record
    rec = bus.info("queued before teardown")
    sip.delete(console)
    emit(rec)  # must not raise


def test_destroyed_widget_unsubscribes_from_the_bus(parent, bus):
    from PyQt6 import sip
    console = _console(parent, bus)
    assert len(bus._subscribers) == 1
    sip.delete(console)
    assert len(bus._subscribers) == 0


def test_a_record_emitted_from_a_worker_thread_still_reaches_the_console(parent, bus):
    import threading
    console = _console(parent, bus)
    t = threading.Thread(target=lambda: bus.info("from a worker thread", source="train"))
    t.start()
    t.join()
    QApplication.processEvents()
    assert "from a worker thread" in console._text.toPlainText()


# ── place() geometry (unchanged contract test_app_wiring.py relies on) ──────
def test_place_anchors_to_the_bottom_spanning_the_remaining_width(parent, bus):
    from studio.components import Sidebar
    console = overlays.LogsConsole(parent, theme.DARK, bus=bus)
    console.setParent(parent)
    console.place()
    geom = console.geometry()
    assert geom.x() == Sidebar.WIDTH
    assert geom.height() == overlays.LogsConsole.HEIGHT
    assert geom.y() == parent.height() - overlays.LogsConsole.HEIGHT
    assert geom.width() == parent.width() - Sidebar.WIDTH
