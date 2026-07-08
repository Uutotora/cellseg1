"""Headless tests for the New Project modal (studio/new_project_dialog.py).

Offscreen Qt, no napari/torch. Drag-and-drop itself needs a real pointer
device and isn't exercised here; ``_add_files``/``_remove_file`` are the
testable core both the drop handler and the file-picker funnel through.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
npd = pytest.importorskip("studio.new_project_dialog")

from PyQt6.QtWidgets import QApplication, QWidget

from studio import theme
from studio.project import ProjectStore


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def parent(app):
    w = QWidget()
    w.resize(1200, 800)
    w.show()  # isVisible() on descendants needs the ancestor chain actually shown
    return w


@pytest.fixture
def store(tmp_path):
    return ProjectStore(tmp_path)


@pytest.fixture
def dialog(app, parent, store):
    created = []
    d = npd.NewProjectDialog(parent, theme.DARK, store, on_created=created.append)
    d.created_ids = created  # stash for assertions
    return d


def test_constructs_hidden_on_step_zero(dialog):
    assert dialog.isHidden()
    assert dialog._step == 0


def test_open_resets_and_shows(dialog):
    dialog._step = 2
    dialog._name = "leftover"
    dialog.open()
    assert not dialog.isHidden()
    assert dialog._step == 0
    assert dialog._name == ""


def test_next_disabled_until_name_entered(dialog):
    dialog.open()
    assert not dialog._next_btn.isEnabled()
    dialog._set_name("Nuclei Screen")
    assert dialog._next_btn.isEnabled()
    dialog._set_name("   ")  # whitespace-only doesn't count
    assert not dialog._next_btn.isEnabled()


def test_go_next_blocked_on_empty_name(dialog):
    dialog.open()
    dialog._go_next()
    assert dialog._step == 0  # didn't advance


def test_step_navigation_forward_and_back(dialog):
    dialog.open()
    dialog._set_name("Nuclei Screen")
    dialog._go_next()
    assert dialog._step == 1
    assert dialog._title_lbl.text() == "Import images"
    dialog._go_next()
    assert dialog._step == 2
    assert dialog._title_lbl.text() == "Choose an engine"
    assert dialog._next_btn.text() == "Create Project"
    dialog._go_back()
    assert dialog._step == 1
    assert dialog._back_btn.isVisible()


def test_name_and_description_persist_across_steps(dialog):
    dialog.open()
    dialog._set_name("Nuclei Screen")
    dialog._set_description("A test cohort")
    dialog._go_next()
    dialog._go_back()
    assert dialog._name == "Nuclei Screen"
    assert dialog._description == "A test cohort"


def test_add_and_remove_files(dialog):
    dialog.open()
    dialog._add_files(["/a/img1.tif", "/a/img2.tif"])
    assert dialog._image_paths == ["/a/img1.tif", "/a/img2.tif"]
    dialog._add_files(["/a/img1.tif"])  # duplicate ignored
    assert dialog._image_paths == ["/a/img1.tif", "/a/img2.tif"]
    dialog._remove_file(0)
    assert dialog._image_paths == ["/a/img2.tif"]


def test_engine_selection_updates_index(dialog):
    dialog.open()
    dialog._set_engine(2)
    assert dialog._engine_idx == 2


def test_create_writes_through_store_and_calls_back(dialog, store):
    dialog.open()
    dialog._set_name("Nuclei Screen")
    dialog._set_description("A test cohort")
    dialog._go_next()
    dialog._add_files(["/a/img1.tif", "/a/img2.tif"])
    dialog._go_next()
    dialog._set_engine(1)  # cellpose
    dialog._go_next()  # creates

    assert dialog.isHidden()
    assert len(dialog.created_ids) == 1
    project = store.load(dialog.created_ids[0])
    assert project.name == "Nuclei Screen"
    assert project.description == "A test cohort"
    assert project.engine == "cellpose"
    assert project.image_paths == ["/a/img1.tif", "/a/img2.tif"]


def test_create_with_no_images_is_allowed(dialog, store):
    dialog.open()
    dialog._set_name("Empty Project")
    dialog._go_next()
    dialog._go_next()
    dialog._go_next()
    project = store.load(dialog.created_ids[0])
    assert project.image_paths == []


def test_close_button_hides_without_creating(dialog, store):
    dialog.open()
    dialog._set_name("Abandoned")
    dialog.hide()
    assert dialog.isHidden()
    assert store.list() == []


def test_click_outside_panel_closes(dialog):
    dialog.open()
    assert not dialog.isHidden()
    # childAt() on a point with no child (far corner, outside the centred
    # panel) returns None -- the same path a real click on the scrim takes.
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import Qt as QtNS
    pos = QPoint(2, 2)
    assert dialog.childAt(pos) is None
    event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, pos.toPointF(),
                        QtNS.MouseButton.LeftButton, QtNS.MouseButton.LeftButton,
                        QtNS.KeyboardModifier.NoModifier)
    dialog.mousePressEvent(event)
    assert dialog.isHidden()
