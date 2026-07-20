"""Tests for the newly-interactive atoms in studio/components.py (Slider,
Stepper) — the rest of the UI kit stays presentational or was already
covered indirectly by screen-wiring tests. Offscreen Qt, no napari/torch.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
components = pytest.importorskip("studio.components")

from PyQt6.QtCore import QPoint, QPointF, QPropertyAnimation, Qt
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from studio import theme


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def _press(widget, x, y=7):
    ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(x, y), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    widget.mousePressEvent(ev)


def _drag(widget, x, y=7):
    ev = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(x, y), Qt.MouseButton.NoButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    widget.mouseMoveEvent(ev)


# ── Slider ───────────────────────────────────────────────────────────────────
def test_slider_default_value_and_clamping(app):
    s = components.Slider(theme.DARK, 0.5)
    assert s.value() == 0.5
    s.set_value(1.5)
    assert s.value() == 1.0
    s.set_value(-1.0)
    assert s.value() == 0.0


def test_slider_click_sets_value_and_emits(app):
    s = components.Slider(theme.DARK, 0.0)
    s.resize(100, 14)
    seen = []
    s.changed.connect(seen.append)
    _press(s, 25)  # 25/100 -> 0.25
    assert s.value() == pytest.approx(0.25, abs=0.02)
    assert seen and seen[-1] == pytest.approx(0.25, abs=0.02)


def test_slider_drag_updates_value(app):
    s = components.Slider(theme.DARK, 0.0)
    s.resize(100, 14)
    _press(s, 10)
    _drag(s, 90)
    assert s.value() == pytest.approx(0.9, abs=0.02)


def test_slider_set_value_without_emit_stays_silent(app):
    s = components.Slider(theme.DARK, 0.2)
    seen = []
    s.changed.connect(seen.append)
    s.set_value(0.8)
    assert s.value() == 0.8
    assert seen == []


# ── Stepper ──────────────────────────────────────────────────────────────────
def test_stepper_default_value_and_display(app):
    st = components.Stepper(32, theme.DARK)
    assert st.value() == 32
    assert st._val_label.text() == "32"


def test_stepper_plus_minus_buttons_change_value_and_emit(app):
    st = components.Stepper(10, theme.DARK, step=2, minimum=0, maximum=100)
    seen = []
    st.changed.connect(seen.append)
    st._plus.click()
    assert st.value() == 12
    st._minus.click()
    st._minus.click()
    assert st.value() == 8
    assert seen == [12, 10, 8]


def test_stepper_clamps_to_bounds(app):
    st = components.Stepper(1, theme.DARK, step=1, minimum=0, maximum=2)
    st._plus.click()
    st._plus.click()
    st._plus.click()
    assert st.value() == 2  # clamped at maximum
    st._minus.click()
    st._minus.click()
    st._minus.click()
    assert st.value() == 0  # clamped at minimum


def test_stepper_decimals_and_suffix_format_display(app):
    st = components.Stepper(0.8, theme.DARK, step=0.05, minimum=0, maximum=1,
                            decimals=2, suffix=" iou")
    assert st._val_label.text() == "0.80 iou"
    st._plus.click()
    assert st._val_label.text() == "0.85 iou"


def test_stepper_set_value_without_emit_stays_silent(app):
    st = components.Stepper(5, theme.DARK)
    seen = []
    st.changed.connect(seen.append)
    st.set_value(9)
    assert st.value() == 9
    assert seen == []


# ── SmoothScrollArea ─────────────────────────────────────────────────────────
def _wheel(widget, angle_y: int, pixel_y: int = 0) -> None:
    ev = QWheelEvent(
        QPointF(10, 10), QPointF(10, 10), QPoint(0, pixel_y), QPoint(0, angle_y),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False)
    widget.wheelEvent(ev)


def _tall_scroll_area():
    inner = QWidget()
    lay = QVBoxLayout(inner)
    for i in range(200):
        lay.addWidget(QLabel(f"row {i}"))
    sa = components.SmoothScrollArea()
    sa.setWidgetResizable(True)
    sa.setWidget(inner)
    sa.resize(300, 200)
    sa.show()
    return sa


def test_smooth_scroll_area_animates_a_discrete_wheel_notch(app):
    """A traditional notched mouse wheel (angleDelta only, no pixelDelta)
    must not jump the scrollbar instantly -- docstudio/BACKLOG.md's
    "Projects tab v2" entry. Right after the event the bar must still be at
    its starting value (an instant jump would already be at the target the
    moment wheelEvent() returns), and the animation actually queued for it
    must be configured to land on the right target.

    Deliberately does not wait for the animation to actually finish and
    assert on the bar's *settled* value: Qt's shared animation-driver timer
    is process-wide, and another test module (test_motion.py) starts several
    short-lived QPropertyAnimations of its own without ever pumping the
    event loop afterwards to let them complete -- confirmed by bisection
    (`pytest test_motion.py test_components.py` reproduces a stuck-at-0
    failure that neither file alone does) to leave the shared timer unable
    to advance *new* animations for the rest of the process, no matter how
    long a test then waits. Asserting on the configured animation object
    itself (mirroring test_motion.py's own test_slide_in_returns_an_
    animation_with_the_right_start_and_end) verifies the same thing --the
    right eased step was set up, not an instant jump-- without depending on
    that shared, apparently-stateful timer ever actually firing again.
    """
    sa = _tall_scroll_area()
    app.processEvents()
    bar = sa.verticalScrollBar()
    assert bar.maximum() > 0
    start = bar.value()

    _wheel(sa, angle_y=-120)

    assert bar.value() == start, "must not jump instantly -- it should still be animating"
    anim = bar._smooth_scroll_anim
    assert isinstance(anim, QPropertyAnimation)
    assert anim.propertyName() == b"value"
    assert anim.startValue() == start
    assert anim.endValue() == start + components.SmoothScrollArea._STEP_PX
    assert anim.state() == QPropertyAnimation.State.Running


def test_smooth_scroll_area_leaves_trackpad_pixel_delta_untouched(app):
    """A trackpad's pixelDelta is already smooth -- Qt's own default handling
    must run unmodified (synchronously, no animation), not the eased step for
    a discrete wheel -- double-applying both would make trackpad scrolling
    feel wrong, not right."""
    sa = _tall_scroll_area()
    app.processEvents()
    bar = sa.verticalScrollBar()
    start = bar.value()

    _wheel(sa, angle_y=-120, pixel_y=-40)
    assert bar.value() != start  # Qt's own default pixelDelta handling took it, synchronously
    assert not hasattr(bar, "_smooth_scroll_anim")


def test_smooth_scroll_area_noop_when_nothing_to_scroll(app):
    """No scrollable range (content shorter than the viewport) must fall
    through to Qt's default (a no-op / propagate-to-parent), not spin up an
    animation to nowhere."""
    sa = components.SmoothScrollArea()
    inner = QWidget()
    QVBoxLayout(inner).addWidget(QLabel("one short row"))
    sa.setWidgetResizable(True)
    sa.setWidget(inner)
    sa.resize(400, 400)
    sa.show()
    app.processEvents()
    bar = sa.verticalScrollBar()
    assert bar.maximum() <= bar.minimum()

    _wheel(sa, angle_y=-120)
    assert not hasattr(bar, "_smooth_scroll_anim")
