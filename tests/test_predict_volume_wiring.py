"""Wiring test: the z-stack/time-lapse toggle and SAM2 settings card in
PredictWidget.

Exercises real Qt widget construction, visibility, and state — using a
MagicMock in place of a real napari.Viewer. Constructing an actual
napari.Viewer segfaults under this sandbox's offscreen Qt platform (confirmed
separately: the crash happens inside napari.Viewer() itself, before
PredictWidget is ever touched), but PredictWidget's constructor only calls a
handful of Viewer methods (layers, add_image, add_labels, bind_key,
reset_view), all of which a MagicMock satisfies as harmless no-ops — so this
still exercises the real widget, real signals, and real Qt visibility
plumbing, just without a real napari canvas.

Skipped in the lightweight CI image (no PyQt6/napari).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import MagicMock

import numpy as np
import pytest

pytest.importorskip("PyQt6")
pw = pytest.importorskip("napari_app.widgets.predict_widget")

from PyQt6.QtWidgets import QApplication


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def widget(app):
    viewer = MagicMock()
    viewer.layers = []
    w = pw.PredictWidget(viewer)
    # Qt's isVisible() is composite (considers ancestors), so an unshown
    # top-level widget reports every child as invisible regardless of its own
    # setVisible() state — show() + processEvents() makes isVisible() checks
    # below meaningful instead of trivially False.
    w.show()
    app.processEvents()
    yield w
    w.close()


def _write_zstack_tiff(tmp_path):
    import tifffile
    path = tmp_path / "zstack.tif"
    tifffile.imwrite(path, np.zeros((4, 16, 16), dtype=np.uint16), metadata={"axes": "ZYX"})
    return path


def _write_plain_png(tmp_path):
    import cv2
    path = tmp_path / "flat.png"
    cv2.imwrite(str(path), np.zeros((16, 16, 3), dtype=np.uint8))
    return path


# ── z-stack checkbox visibility ──────────────────────────────────────────────

def test_zstack_checkbox_hidden_for_plain_image(widget, app, tmp_path):
    widget.image_path.setText(str(_write_plain_png(tmp_path)))
    app.processEvents()
    assert widget.zstack_cb.isVisible() is False


def test_zstack_checkbox_shown_for_multiplane_tiff(widget, app, tmp_path):
    widget.image_path.setText(str(_write_zstack_tiff(tmp_path)))
    app.processEvents()
    assert widget.zstack_cb.isVisible() is True


def test_zstack_checkbox_force_unchecked_when_switching_back_to_plain_image(widget, app, tmp_path):
    widget.image_path.setText(str(_write_zstack_tiff(tmp_path)))
    app.processEvents()
    widget.zstack_cb.setChecked(True)

    widget.image_path.setText(str(_write_plain_png(tmp_path)))
    app.processEvents()
    assert widget.zstack_cb.isChecked() is False
    assert widget.zstack_cb.isVisible() is False


def test_gather_params_zstack_true_only_when_checked_and_visible(widget, app, tmp_path):
    widget.image_path.setText(str(_write_zstack_tiff(tmp_path)))
    app.processEvents()
    widget.zstack_cb.setChecked(True)
    assert widget._gather_params()["zstack"] is True


def test_gather_params_zstack_false_when_hidden_even_if_checked(widget):
    # Defence in depth: _gather_params must not trust isChecked() alone once
    # the toggle is hidden, independent of _refresh_zstack_toggle's own
    # force-uncheck behaviour.
    widget.zstack_cb.setVisible(False)
    widget.zstack_cb.setChecked(True)
    assert widget._gather_params()["zstack"] is False


# ── engine switching: SAM2 settings card + hint text ─────────────────────────

def test_sam2_card_hidden_for_default_engine(widget):
    assert widget._current_engine() == "cellseg1"
    assert widget._sam2_card.isVisible() is False


def test_sam2_card_shown_when_engine_switched_to_sam2(widget, app):
    widget.engine.setCurrentIndex(widget.engine.findData("sam2"))
    app.processEvents()
    assert widget._sam2_card.isVisible() is True
    assert widget._cp_card.isVisible() is False
    assert widget._ckpt_card.isVisible() is False


def test_cp_card_shown_when_engine_switched_to_cellpose(widget, app):
    widget.engine.setCurrentIndex(widget.engine.findData("cellpose"))
    app.processEvents()
    assert widget._cp_card.isVisible() is True
    assert widget._sam2_card.isVisible() is False


def test_sam2_engine_hint_reflects_availability(widget, monkeypatch):
    import napari_app.engines_sam2 as es2

    monkeypatch.setattr(es2, "sam2_available", lambda: False)
    widget.engine.setCurrentIndex(widget.engine.findData("sam2"))
    assert "not installed" in widget._engine_hint.text()

    monkeypatch.setattr(es2, "sam2_available", lambda: True)
    widget._on_engine_changed()
    assert "z-stack" in widget._engine_hint.text()


def test_gather_params_includes_sam2_fields(widget):
    widget.sam2_model_type.setCurrentText("small")
    widget.sam2_checkpoint.setText("/x/y.pt")
    widget.sam2_config_text.setText("configs/custom.yaml")
    params = widget._gather_params()
    assert params["sam2_model_type"] == "small"
    assert params["sam2_checkpoint_text"] == "/x/y.pt"
    assert params["sam2_config_text"] == "configs/custom.yaml"


def test_run_prediction_dispatches_to_volume_path_when_zstack_checked(widget, app, tmp_path, monkeypatch):
    """_run_prediction must call run_volume_prediction_async (not
    run_prediction_async) when the z-stack toggle is on, and never reach the
    2-D on_result path."""
    path = _write_zstack_tiff(tmp_path)
    widget.image_path.setText(str(path))
    app.processEvents()
    widget.zstack_cb.setChecked(True)
    widget.engine.setCurrentIndex(widget.engine.findData("cellpose"))
    app.processEvents()

    calls = []
    monkeypatch.setattr(
        widget._controller, "run_volume_prediction_async",
        lambda config, **kw: calls.append(("volume", config.get("zstack"))))
    monkeypatch.setattr(
        widget._controller, "run_prediction_async",
        lambda config, **kw: calls.append(("2d", config.get("zstack"))))

    widget._run_prediction()
    assert calls == [("volume", True)]


# ── _show_volume_results: real 3-D measurements, not a stub ─────────────────
#
# get_log_window() is a module-level singleton shared across every
# PredictWidget instance in this process; repeatedly constructing and
# closing PredictWidget (one per test, per the `widget` fixture) is a test-
# only pattern the real app never does — one PredictWidget lives for the
# whole napari session — and it leaves the shared LogWindow's underlying Qt
# object in a torn-down state for a later test to inherit ("wrapped C/C++
# object ... has been deleted"). None of these tests assert on log text, so
# _append_log is stubbed out to sidestep that shared, test-only fragility
# rather than working around it in production code.

def test_show_volume_results_populates_last_measure(widget, monkeypatch):
    monkeypatch.setattr(widget, "_append_log", lambda *a, **k: None)
    img_vol = np.zeros((4, 30, 30, 3), dtype=np.uint8)
    mask_vol = np.zeros((4, 30, 30), dtype=np.int32)
    mask_vol[:, 5:15, 5:15] = 1

    widget._show_volume_results(img_vol, mask_vol)

    assert widget._last_measure is not None
    assert widget._last_measure["n_cells"] == 1
    assert any(k == "volume" for k, _l, _u in widget._last_measure["columns"])
    assert widget._results_card.isVisible() is False   # hero chips stay hidden (2-D wording)


def test_show_volume_results_no_cells_leaves_measure_none(widget, monkeypatch):
    monkeypatch.setattr(widget, "_append_log", lambda *a, **k: None)
    img_vol = np.zeros((3, 20, 20, 3), dtype=np.uint8)
    mask_vol = np.zeros((3, 20, 20), dtype=np.int32)   # no instances

    widget._show_volume_results(img_vol, mask_vol)

    assert widget._last_measure is None


def test_show_volume_results_enables_open_measurements(widget, monkeypatch):
    """_open_measurements' only guard is `_last_measure is None` — confirm a
    volume result clears that guard the same way a 2-D one does."""
    monkeypatch.setattr(widget, "_append_log", lambda *a, **k: None)
    img_vol = np.zeros((4, 30, 30, 3), dtype=np.uint8)
    mask_vol = np.zeros((4, 30, 30), dtype=np.int32)
    mask_vol[:, 5:15, 5:15] = 1

    widget._show_volume_results(img_vol, mask_vol)
    widget._open_measurements()   # must not raise / log a "run a prediction first" warning


# ── SAM2 tracking-mode combo ─────────────────────────────────────────────────

def test_tracking_mode_defaults_to_automatic(widget):
    assert widget.sam2_tracking_mode.currentData() == "automatic"
    assert widget._gather_params()["sam2_tracking_mode"] == "automatic"


def test_tracking_mode_propagate_threads_through_gather_params(widget):
    idx = widget.sam2_tracking_mode.findData("propagate")
    widget.sam2_tracking_mode.setCurrentIndex(idx)
    assert widget._gather_params()["sam2_tracking_mode"] == "propagate"
