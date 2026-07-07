"""CellSeg1 Studio — the microscopy 'nuclei' painter (design skeleton).

A QPainter port of the mockup's ``<canvas>``: a dark field of fluorescent
nuclei (DAPI-like glow) with teal segmentation outlines and, on the big
viewport, iris 'selected' cells. Purely decorative stand-in art so the design
reads correctly before any real image/mask is wired in.

``NucleiView`` fills its widget; ``nuclei_pixmap`` renders a fixed-size pixmap
for card covers and thumbnails. Deterministic per ``seed`` so a given card
always looks the same.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPixmap, QColor, QRadialGradient, QPolygonF, QPen
from PyQt6.QtWidgets import QWidget


def _rng(seed: int):
    state = seed & 0xFFFFFFFF

    def rnd():
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = state
        t = (t ^ (t >> 15)) * (1 | t) & 0xFFFFFFFF
        t = (t + ((t ^ (t >> 7)) * (61 | t) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0
    return rnd


def _blob(cx, cy, r, seed, steps, wobble=0.09) -> QPolygonF:
    poly = QPolygonF()
    a = 0.0
    while a <= math.pi * 2 + 0.01:
        rr = r * (0.9 + math.sin(a * 3 + seed * 6) * wobble + math.cos(a * 2) * 0.04)
        poly.append(QPointF(cx + math.cos(a) * rr, cy + math.sin(a) * rr))
        a += math.pi / steps
    return poly


def paint_nuclei(p: QPainter, w: int, h: int, seed: int,
                 density: float = 1.0, outline: bool = True,
                 big: bool = False) -> None:
    """Render the nuclei field into ``p`` over a ``w``×``h`` area."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.fillRect(0, 0, w, h, QColor("#080a0e"))
    # vignette
    vg = QRadialGradient(w / 2, h / 2, max(w, h) * 0.7)
    vg.setColorAt(0.0, QColor(30, 40, 60, 26))
    vg.setColorAt(1.0, QColor(0, 0, 0, 128))
    p.fillRect(0, 0, w, h, vg)

    r = _rng(seed)
    cols = max(4, round(w / 48 * density))
    rows = max(3, round(h / 48 * density))
    cw, ch = w / cols, h / rows
    cells = []
    for yy in range(rows):
        for xx in range(cols):
            if r() < 0.12:
                continue
            cx = (xx + 0.5 + (r() - 0.5) * 0.7) * cw
            cy = (yy + 0.5 + (r() - 0.5) * 0.7) * ch
            rad = min(cw, ch) * (0.30 + r() * 0.20)
            cells.append((cx, cy, rad, r()))

    # DAPI-like glow
    for cx, cy, rad, s in cells:
        g = QRadialGradient(cx, cy, rad * 1.5)
        g.setColorAt(0.0, QColor(205, 222, 255, 242))
        g.setColorAt(0.45, QColor(150, 180, 240, 140))
        g.setColorAt(1.0, QColor(90, 120, 200, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawPolygon(_blob(cx, cy, rad, s, 9))

    if not outline:
        return

    # segmentation overlays
    for i, (cx, cy, rad, s) in enumerate(cells):
        poly = _blob(cx, cy, rad, s, 18, wobble=0.08)
        selected = big and (i % 17 == 3)
        if selected:
            p.setPen(QPen(QColor(139, 155, 244, 242), 2))
            p.setBrush(QColor(109, 135, 241, 41))
        else:
            if big and i % 5 == 0:
                p.setBrush(QColor(43, 212, 192, 26))
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(43, 212, 192, 230 if big else 191), 1.4 if big else 1.0))
        p.drawPolygon(poly)


def nuclei_pixmap(w: int, h: int, seed: int, density: float = 1.15,
                  outline: bool = True, big: bool = False, dpr: float = 2.0) -> QPixmap:
    px = QPixmap(int(w * dpr), int(h * dpr))
    px.setDevicePixelRatio(dpr)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    paint_nuclei(p, w, h, seed, density, outline, big)
    p.end()
    return px


class NucleiView(QWidget):
    """A widget that fills itself with the nuclei field (the viewport canvas)."""

    def __init__(self, seed: int = 7, density: float = 0.85, big: bool = True):
        super().__init__()
        self._seed = seed
        self._density = density
        self._big = big
        self.setMinimumSize(200, 160)
        self.setStyleSheet("background:#07090c;")

    def paintEvent(self, e):
        p = QPainter(self)
        paint_nuclei(p, self.width(), self.height(), self._seed,
                     self._density, True, self._big)
        p.end()
