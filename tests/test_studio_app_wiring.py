"""Headless wiring/smoke tests for the Studio design skeleton.

Constructs the whole app (sidebar, all screens, overlays, frameless rounded
window) under ``QT_QPA_PLATFORM=offscreen`` with **no napari and no torch** —
the branch is a pure-design skeleton. Skipped in the GUI-less CI job.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
components = pytest.importorskip("napari_app.studio.components")
app_mod = pytest.importorskip("napari_app.studio.app")
paint = pytest.importorskip("napari_app.studio.paint")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from napari_app.studio import theme


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


# ── UI kit ───────────────────────────────────────────────────────────────────
def test_ui_atoms_construct(app):
    t = theme.DARK
    assert components.Chip("x", t, "primary") is not None
    assert components.PillButton("Go", t, "primary", "plus").text() == "Go"
    assert components.PillButton("Ghost", t, "ghost").text() == "Ghost"
    assert components.Badge("0.80", t) is not None
    assert components.SelectBox("512 px", t) is not None
    assert components.Stepper("32", t) is not None
    assert components.StatTile("25.5", "px", "MEDIAN", t) is not None


def test_toggle_flips_state(app):
    tg = components.Toggle(theme.DARK, on=False)
    assert not tg.is_on()
    tg.set_on(True)
    assert tg.is_on()


def test_segcontrol_selection_emits(app):
    seen = []
    seg = components.SegControl(["A", "B", "C"], theme.DARK, active=0)
    seg.changed.connect(seen.append)
    seg._select(2)
    assert seen == [2]
    assert seg._btns[2].isChecked() and not seg._btns[0].isChecked()


def test_accordion_toggles(app):
    acc = components.Accordion("Ground truth", theme.LIGHT, open_=False)
    assert not acc._body.isVisible()
    acc.toggle()
    assert acc._open


def test_sidebar_navigates(app):
    seen = []
    sb = components.Sidebar(app_mod._NAV, theme.DARK)
    sb.navigate.connect(seen.append)
    sb._items["workspace"].click()
    assert seen == ["workspace"]


# ── paint ────────────────────────────────────────────────────────────────────
def test_nuclei_pixmap_renders(app):
    px = paint.nuclei_pixmap(120, 90, seed=7)
    assert not px.isNull()
    assert paint.NucleiView(seed=7) is not None


# ── screens ──────────────────────────────────────────────────────────────────
def test_all_screens_construct(app):
    from napari_app.studio.screens import HomeScreen, ProjectsScreen
    from napari_app.studio.workspace import WorkspaceScreen
    from napari_app.studio.extra_screens import ModelsScreen, DashboardScreen
    t = theme.DARK
    assert HomeScreen(t, lambda k: None, lambda i: None) is not None
    assert ProjectsScreen(t, lambda k: None, lambda i: None) is not None
    assert WorkspaceScreen(t) is not None
    assert ModelsScreen(t) is not None
    assert DashboardScreen(t) is not None


# ── window ───────────────────────────────────────────────────────────────────
def test_window_is_frameless_with_titlebar_and_grips(app):
    from napari_app.studio import window_chrome
    win = app_mod.StudioWindow(theme_name="dark")
    assert win.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert len(win.findChildren(window_chrome.TitleBar)) == 1
    assert len(win._grips) == 4


def test_window_constructs_without_napari_or_store(app):
    # If this imported napari/torch, the light CI job would fail — it must not.
    win = app_mod.StudioWindow(theme_name="dark")
    assert win._stack.count() == len(app_mod._STACK_KEYS)


def test_navigation_switches_stack_screens(app):
    win = app_mod.StudioWindow(theme_name="dark")
    win.navigate("dashboard")
    assert win._stack.currentWidget() is win._screens["dashboard"]
    win.navigate("workspace")
    assert win._stack.currentWidget() is win._screens["workspace"]


def test_assistant_and_logs_toggle_as_overlays(app):
    # isHidden() is the explicit flag; isVisible() needs the top-level shown.
    win = app_mod.StudioWindow(theme_name="dark")
    assert win._assistant.isHidden()
    win.navigate("assistant")
    assert not win._assistant.isHidden()
    win.navigate("assistant")
    assert win._assistant.isHidden()
    win.navigate("logs")
    assert not win._logs.isHidden()


def test_command_palette_opens_and_escape_closes(app):
    win = app_mod.StudioWindow(theme_name="dark")
    win._toggle_palette()
    assert not win._palette.isHidden()
    win._close_overlays()
    assert win._palette.isHidden()


def test_theme_toggle_rebuilds(app):
    from napari_app.studio import window_chrome
    win = app_mod.StudioWindow(theme_name="dark")
    win.toggle_theme()
    assert win._theme_name == "light"
    assert win._stack.count() == len(app_mod._STACK_KEYS)
    assert len(win.findChildren(window_chrome.TitleBar)) == 1


def test_load_fonts_returns_family(app):
    assert isinstance(app_mod.load_fonts(), str) and app_mod.load_fonts()
