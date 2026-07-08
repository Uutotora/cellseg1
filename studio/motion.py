"""CellSeg1 Studio — small, safe motion helpers (self-contained).

Micro-interactions for the shell (currently a soft fade on screen switches).
Defensive: if animations can't run (e.g. offscreen), degrade to the final
state instead of raising.
"""
from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation
from PyQt6.QtWidgets import QGraphicsOpacityEffect

EASE = QEasingCurve.Type.OutCubic


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
