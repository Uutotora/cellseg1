"""CellSeg1 Studio — small, safe motion helpers (self-contained).

Micro-interactions for the shell: a soft fade on screen switches, and a hover
"lift" for cards/rows. Defensive: if animations can't run (e.g. offscreen),
degrade to the final state instead of raising.
"""
from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPointF, QPropertyAnimation
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsOpacityEffect

EASE = QEasingCurve.Type.OutCubic
HOVER_MS = 160  # matches the mockup's --rail-tap timing


def fade_in(widget, duration: int = 240):
    """Fade a widget from transparent to opaque (used on screen switch)."""
    try:
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(EASE)
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        anim.start()
        widget._fade_anim = anim  # keep a ref alive
        return anim
    except Exception:
        return None


def install_hover_lift(widget, base=(0, 0, 0), hover=(14, 26, 3), duration: int = HOVER_MS):
    """Deepen a widget's drop shadow on hover — an "elevation" cue.

    QSS has no ``transform``/``transition``, so a literal CSS
    ``translateY()`` lift isn't available; animating a
    ``QGraphicsDropShadowEffect``'s blur/offset instead reads the same way
    (shadow deepens toward the pointer) without fighting the layout engine.
    ``base``/``hover`` are ``(blur, alpha, y-offset)`` triples — default
    ``base`` is an invisible shadow (alpha 0), so a row with no shadow at
    rest gains one only on hover; pass a visible ``base`` for a card that
    already has a resting shadow and should merely deepen it.
    """
    try:
        b_blur, b_alpha, b_dy = base
        h_blur, h_alpha, h_dy = hover
        effect = QGraphicsDropShadowEffect(widget)
        effect.setColor(QColor(28, 42, 120, b_alpha))
        effect.setBlurRadius(b_blur)
        effect.setOffset(0, b_dy)
        widget.setGraphicsEffect(effect)

        blur_anim = QPropertyAnimation(effect, b"blurRadius", widget)
        blur_anim.setDuration(duration)
        blur_anim.setEasingCurve(EASE)
        offset_anim = QPropertyAnimation(effect, b"offset", widget)
        offset_anim.setDuration(duration)
        offset_anim.setEasingCurve(EASE)

        def animate_to(blur_to, alpha_to, dy_to):
            effect.setColor(QColor(28, 42, 120, alpha_to))
            blur_anim.stop()
            blur_anim.setStartValue(effect.blurRadius())
            blur_anim.setEndValue(blur_to)
            blur_anim.start()
            offset_anim.stop()
            offset_anim.setStartValue(effect.offset())
            offset_anim.setEndValue(QPointF(0, dy_to))
            offset_anim.start()

        orig_enter, orig_leave = widget.enterEvent, widget.leaveEvent

        def enter(event):
            animate_to(h_blur, h_alpha, h_dy)
            orig_enter(event)

        def leave(event):
            animate_to(b_blur, b_alpha, b_dy)
            orig_leave(event)

        widget.enterEvent = enter
        widget.leaveEvent = leave
        widget._hover_lift = (effect, blur_anim, offset_anim)  # keep refs alive
        return effect
    except Exception:
        return None
