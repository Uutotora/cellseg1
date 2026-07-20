"""Headless tests for studio/project_dialogs.py -- ConfirmDialog (+ the
confirm_delete_project builder) and ProjectSettingsDialog.

Offscreen Qt, no napari/torch.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
pd = pytest.importorskip("studio.project_dialogs")

from PyQt6 import sip
from PyQt6.QtCore import QPoint
from PyQt6.QtCore import Qt as QtNS
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget

from studio import theme
from studio.project import ProjectStore
from studio.project_controller import ProjectController


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def parent(app):
    w = QWidget()
    w.resize(1200, 800)
    w.show()
    return w


@pytest.fixture
def controller(tmp_path):
    return ProjectController(ProjectStore(tmp_path))


def _click_outside(dialog) -> None:
    # childAt() on a point with no child (far corner, outside the centred
    # panel) returns None -- the same path a real click on the scrim takes.
    # Mirrors test_new_project_dialog.py's test_click_outside_panel_closes.
    pos = QPoint(2, 2)
    assert dialog.childAt(pos) is None
    event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, pos.toPointF(),
                        QtNS.MouseButton.LeftButton, QtNS.MouseButton.LeftButton,
                        QtNS.KeyboardModifier.NoModifier)
    dialog.mousePressEvent(event)


# ── ConfirmDialog ────────────────────────────────────────────────────────────
def test_confirm_dialog_hidden_until_open(parent):
    dlg = pd.ConfirmDialog(parent, theme.DARK, "Delete Project?", "body",
                           on_confirm=lambda: None)
    assert dlg.isHidden()
    dlg.open()
    assert not dlg.isHidden()


def test_confirm_dialog_click_outside_closes_without_confirming(parent):
    seen = []
    dlg = pd.ConfirmDialog(parent, theme.DARK, "Title", "body",
                           on_confirm=lambda: seen.append(1))
    dlg.open()
    _click_outside(dlg)
    assert dlg.isHidden()
    assert seen == []


def test_confirm_dialog_confirm_button_calls_on_confirm_and_hides(parent):
    seen = []
    dlg = pd.ConfirmDialog(parent, theme.DARK, "Title", "body", confirm_label="Do it",
                           on_confirm=lambda: seen.append(1))
    dlg.open()
    dlg._confirm()
    assert seen == [1]
    assert dlg.isHidden()


def test_confirm_dialog_constructor_time_hide_does_not_self_delete(app, parent):
    """__init__ ends with self.hide() (same construction as NewProjectDialog)
    to start hidden -- must be a no-op (never-shown -> hidden is not a real
    transition) and NOT trigger hideEvent's deleteLater(), or the dialog
    would be destroyed before ever being usable."""
    dlg = pd.ConfirmDialog(parent, theme.DARK, "Title", "body", on_confirm=lambda: None)
    app.processEvents()
    assert not sip.isdeleted(dlg)
    dlg.open()
    assert not dlg.isHidden()


def test_confirm_dialog_self_disposes_after_a_real_hide(app, parent):
    dlg = pd.ConfirmDialog(parent, theme.DARK, "Title", "body", on_confirm=lambda: None)
    dlg.open()
    dlg.hide()
    app.processEvents()  # let the deferred deleteLater() run
    assert sip.isdeleted(dlg)


def test_confirm_delete_project_names_the_project_and_wires_confirm(parent):
    seen = []
    dlg = pd.confirm_delete_project(parent, theme.DARK, "My Project", on_confirm=lambda: seen.append(1))
    assert not dlg.isHidden()
    dlg._confirm()
    assert seen == [1]


def test_confirm_delete_project_escapes_html_in_the_project_name(parent):
    # A project named with HTML-special characters must not break the rich
    # text body or inject markup -- html.escape() before embedding.
    dlg = pd.confirm_delete_project(parent, theme.DARK, "<script>alert(1)</script>", on_confirm=lambda: None)
    from PyQt6.QtWidgets import QLabel
    labels = dlg.findChildren(QLabel)
    assert any("&lt;script&gt;" in lbl.text() for lbl in labels)
    assert not any("<script>" in lbl.text() for lbl in labels)


# ── ProjectSettingsDialog ────────────────────────────────────────────────────
def test_settings_dialog_hidden_until_open(parent, controller):
    p = controller.list_projects()[0]
    dlg = pd.ProjectSettingsDialog(parent, theme.DARK, p)
    assert dlg.isHidden()
    dlg.open()
    assert not dlg.isHidden()


def test_settings_dialog_prefills_name_and_description(parent, controller):
    p = controller.list_projects()[0]
    dlg = pd.ProjectSettingsDialog(parent, theme.DARK, p)
    assert dlg._name_input.text() == p.name
    assert dlg._desc_input.text() == p.description


def test_settings_dialog_click_outside_does_not_save(parent, controller):
    p = controller.list_projects()[0]
    seen = []
    dlg = pd.ProjectSettingsDialog(parent, theme.DARK, p, on_saved=lambda n, d: seen.append((n, d)))
    dlg.open()
    _click_outside(dlg)
    assert dlg.isHidden()
    assert seen == []


def test_settings_dialog_save_calls_on_saved_with_trimmed_name_and_description(parent, controller):
    p = controller.list_projects()[0]
    seen = []
    dlg = pd.ProjectSettingsDialog(parent, theme.DARK, p, on_saved=lambda n, d: seen.append((n, d)))
    dlg.open()
    dlg._name_input.setText("  Renamed  ")
    dlg._desc_input.setText("  New description  ")
    dlg._save_general()
    assert seen == [("Renamed", "New description")]
    assert dlg.isHidden()


def test_settings_dialog_save_with_blank_name_does_not_save(parent, controller):
    p = controller.list_projects()[0]
    seen = []
    dlg = pd.ProjectSettingsDialog(parent, theme.DARK, p, on_saved=lambda n, d: seen.append((n, d)))
    dlg.open()
    dlg._name_input.setText("   ")
    dlg._save_general()
    assert seen == []


def test_settings_dialog_delete_requires_its_own_nested_confirm(parent, controller):
    """Delete Project must not act immediately -- it opens its own nested
    ConfirmDialog first (the one truly irreversible action in this flow),
    same pattern as NewProjectDialog's "keep a ref alive" convention."""
    p = controller.list_projects()[0]
    deleted = []
    dlg = pd.ProjectSettingsDialog(parent, theme.DARK, p, on_delete=lambda: deleted.append(1))
    dlg.open()

    dlg._confirm_delete()

    assert deleted == []  # not yet -- only the nested confirm opened
    nested = next(w for w in dlg.findChildren(pd.ConfirmDialog) if not w.isHidden())
    nested._confirm()
    assert deleted == [1]


def test_settings_dialog_self_disposes_after_a_real_hide(app, parent, controller):
    p = controller.list_projects()[0]
    dlg = pd.ProjectSettingsDialog(parent, theme.DARK, p)
    dlg.open()
    dlg.hide()
    app.processEvents()
    assert sip.isdeleted(dlg)


def test_settings_dialog_labels_sit_on_the_panel_surface_not_a_scrim_blended_patch(app, controller):
    """The same rendering-bug family test_new_project_dialog.py's own
    analogous test pins (a bare QWidget() container leaking the app-wide
    background rule, glaring under this dialog's translucent scrim) --
    ProjectSettingsDialog applies the learned fix (explicit `background:
    transparent` on its header/body containers) from the start; this test
    confirms that actually holds, not just that it looks right by eye.
    """
    import time as _time

    t = theme.LIGHT  # see the NewProjectDialog test's comment for why light, not dark
    app.setStyleSheet(theme.build_qss(t))
    try:
        store = ProjectStore("/tmp/_unused_settings_scrim_test_store")
        controller = ProjectController(store)
        p = controller.list_projects()[0]

        win = QWidget()
        win.resize(1400, 900)
        win.setStyleSheet(f"background:{t['bg']};")
        win.show()
        dlg = pd.ProjectSettingsDialog(win, t, p)
        dlg.open()
        for _ in range(30):
            app.processEvents()
            _time.sleep(0.01)

        img = win.grab().toImage()
        from PyQt6.QtWidgets import QLabel
        # Exclude labels genuinely meant to sit on the Danger Zone's own
        # intentionally red-tinted card (an explicit, qualified #DangerZone
        # fill, not a rendering bug) -- everything else in the dialog should
        # sit directly on the panel's own plain surface.
        danger_zone = dlg.findChild(QWidget, "DangerZone")
        labels = [w for w in dlg.findChildren(QLabel) if w.text().strip() and w.isVisible()
                 and not (danger_zone and danger_zone.isAncestorOf(w))]
        assert len(labels) >= 3  # "Project Settings", "PROJECT NAME", "DESCRIPTION", ...
        offenders = []
        for lbl in labels:
            pt = lbl.mapTo(win, lbl.rect().topLeft())
            sample = img.pixelColor(pt.x(), pt.y())
            if sample.name() != t["surface"]:
                offenders.append((lbl.text(), sample.name()))
        assert not offenders, f"labels not sitting on the panel's own surface fill: {offenders}"

        # The Danger Zone's own labels, meanwhile, must sit on ITS tinted
        # fill, not the plain panel surface -- confirms the red tint is
        # actually applied, not silently absent (a real, if different,
        # instance of the same "is this container really styled" question).
        assert danger_zone is not None
        danger_labels = [w for w in dlg.findChildren(QLabel) if w.text().strip() and w.isVisible()
                         and danger_zone.isAncestorOf(w)]
        assert len(danger_labels) >= 2  # "Danger zone" + the explanatory body text
        for lbl in danger_labels:
            pt = lbl.mapTo(win, lbl.rect().topLeft())
            sample = img.pixelColor(pt.x(), pt.y())
            assert sample.name() != t["surface"], (
                f"{lbl.text()!r} sampled the plain panel surface -- the danger-zone tint isn't showing")
    finally:
        app.setStyleSheet("")  # process-wide QApplication singleton -- don't leak
