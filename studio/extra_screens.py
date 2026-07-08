"""CellSeg1 Studio — Models & Train and Dashboard screens (static skeleton)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor, QPen, QPolygonF, QPainterPath
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QHBoxLayout, QVBoxLayout, QGridLayout, QScrollArea,
)

from studio import icons
from studio import theme, demo
from studio.components import (
    Chip, Badge, PillButton, SelectBox, GroupLabel, hline, soft_shadow, label,
)
from studio.screens import page_header, scroll


# ── Models & Train ───────────────────────────────────────────────────────────
class ModelsScreen(QWidget):
    def __init__(self, t: dict):
        super().__init__()
        self._t = t
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(page_header("Models & Train", "4 trained adapters · one-shot LoRA fine-tuning",
                                    t, PillButton("Import model", t, "ghost", "download")))
        body = QWidget()
        row = QHBoxLayout(body)
        row.setContentsMargins(34, 4, 34, 40)
        row.setSpacing(24)
        row.addLayout(self._left(), 1)
        row.addLayout(self._aside(), 0)
        outer.addWidget(scroll(body))

    def _left(self) -> QVBoxLayout:
        t = self._t
        col = QVBoxLayout()
        col.setSpacing(24)

        card = QFrame()
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(f"background:{t['surface']}; border:1px solid {t['border']}; border-radius:14px;")
        soft_shadow(card, 14, 22, 3)
        cv = QVBoxLayout(card)
        cv.setContentsMargins(20, 20, 20, 20)
        cv.setSpacing(4)
        cv.addWidget(label("Train a new model", 16, t["text"], 600))
        cap = label("Fine-tune SAM with LoRA from a single annotated image — no ML setup, minutes on this device.",
                    13, t["text_muted"])
        cap.setWordWrap(True)
        cv.addWidget(cap)
        cv.addSpacing(14)
        form = QGridLayout()
        form.setSpacing(14)
        fields = [("Annotated image", "img_001.tif · 247 cells"), ("SAM backbone", "ViT-H"),
                  ("LoRA rank", "8"), ("Epochs", "100")]
        for i, (name, val) in enumerate(fields):
            fc = QVBoxLayout()
            fc.setSpacing(7)
            fc.addWidget(GroupLabel(name, t))
            fc.addWidget(SelectBox(val, t))
            form.addLayout(fc, i // 2, i % 2)
        cv.addLayout(form)
        cv.addSpacing(16)
        cv.addWidget(PillButton("Start training", t, "primary", "run"), alignment=Qt.AlignmentFlag.AlignLeft)
        col.addWidget(card)

        col.addWidget(label("Trained models", 15, t["text"], 600))
        for name, meta, f1 in demo.MODELS:
            col.addWidget(self._model_row(name, meta, f1))
        col.addStretch(1)
        return col

    def _model_row(self, name: str, meta: str, f1: str) -> QFrame:
        t = self._t
        row = QFrame()
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row.setStyleSheet(
            f"QFrame{{background:{t['surface']}; border:1px solid {t['border']}; border-radius:10px;}}"
            f"QFrame:hover{{border-color:{t['border_strong']};}}")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(13)
        badge = QLabel()
        badge.setFixedSize(38, 38)
        badge.setPixmap(icons.pixmap("models", t["primary"], 18))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"background:{t['primary_weak']}; border-radius:9px;")
        lay.addWidget(badge)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label(name, 13.5, t["text"], 600))
        col.addWidget(label(meta, 11.5, t["text_muted"]))
        lay.addLayout(col, 1)
        f1col = QVBoxLayout()
        f1col.setSpacing(1)
        v = QLabel(f1)
        v.setStyleSheet(f"color:{t['success']}; font-family:{theme.MONO}; font-size:14px; font-weight:600;")
        v.setAlignment(Qt.AlignmentFlag.AlignRight)
        f1col.addWidget(v)
        f1col.addWidget(label("F1", 10, t["text_muted"], 600, 0.5), alignment=Qt.AlignmentFlag.AlignRight)
        lay.addLayout(f1col)
        return row

    def _aside(self) -> QVBoxLayout:
        t = self._t
        col = QVBoxLayout()
        col.setSpacing(16)
        card = QFrame()
        card.setFixedWidth(320)
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(f"background:{t['surface']}; border:1px solid {t['border']}; border-radius:14px;")
        soft_shadow(card, 14, 20, 3)
        cv = QVBoxLayout(card)
        cv.setContentsMargins(16, 16, 16, 16)
        cv.setSpacing(10)
        cv.addWidget(label("Recent training runs", 13.5, t["text"], 600))
        for name, meta, state in demo.TRAIN_RUNS:
            r = QHBoxLayout()
            r.setSpacing(10)
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dcol = t["signal"] if state == "run" else t["success"]
            dot.setStyleSheet(f"background:{dcol}; border-radius:4px;")
            r.addWidget(dot)
            c = QVBoxLayout()
            c.setSpacing(1)
            c.addWidget(label(name, 12.5, t["text"], 600))
            c.addWidget(label(meta, 11, t["text_muted"]))
            r.addLayout(c, 1)
            cv.addLayout(r)
        col.addWidget(card)

        tip = QFrame()
        tip.setFixedWidth(320)
        tip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        tip.setStyleSheet(f"background:{t['primary_weak']}; border:1px solid {t['primary_line']}; border-radius:14px;")
        tv = QVBoxLayout(tip)
        tv.setContentsMargins(16, 16, 16, 16)
        tv.setSpacing(6)
        tv.addWidget(label("✦ One-shot fine-tuning", 13, t["primary"], 600))
        p = label("CellSeg1 specialises SAM to your assay from a single annotated field — the rest of the cohort inherits it.",
                  12.5, t["text_subtle"])
        p.setWordWrap(True)
        tv.addWidget(p)
        col.addWidget(tip)
        col.addStretch(1)
        return col


# ── Dashboard ────────────────────────────────────────────────────────────────
class _LineChart(QWidget):
    def __init__(self, data, color: str, t: dict):
        super().__init__()
        self._data = data
        self._color = color
        self._t = t
        self.setMinimumHeight(120)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h, pad = self.width(), self.height(), 8
        p.setPen(QPen(QColor(self._t["border"]), 1))
        for g in range(4):
            y = pad + (h - 2 * pad) * g / 3
            p.drawLine(0, int(y), w, int(y))
        data = self._data
        mn, mx = min(data), max(data)
        rng = (mx - mn) or 1

        def X(i):
            return pad + (w - 2 * pad) * i / (len(data) - 1)

        def Y(v):
            return pad + (h - 2 * pad) * (1 - (v - mn) / rng)
        path = QPainterPath()
        for i, v in enumerate(data):
            pt = QPointF(X(i), Y(v))
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        col = QColor(self._color)
        fill = QColor(self._color)
        fill.setAlpha(34)
        area = QPainterPath(path)
        area.lineTo(X(len(data) - 1), h - pad)
        area.lineTo(X(0), h - pad)
        area.closeSubpath()
        p.fillPath(area, fill)
        p.setPen(QPen(col, 2))
        p.drawPath(path)
        p.setBrush(col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(X(len(data) - 1), Y(data[-1])), 3, 3)
        p.end()


class _BarChart(QWidget):
    def __init__(self, data, color: str, t: dict):
        super().__init__()
        self._data = data
        self._color = color
        self._t = t
        self.setMinimumHeight(120)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        bw = w / len(self._data)
        base = QColor(self._color)
        faded = QColor(self._color)
        faded.setAlpha(102)
        for i, v in enumerate(self._data):
            bh = max(4, v * (h - 10))
            p.setBrush(base if i == len(self._data) - 1 else faded)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(i * bw + 4, h - bh, bw - 8, bh), 3, 3)
        p.end()


class DashboardScreen(QWidget):
    def __init__(self, t: dict):
        super().__init__()
        self._t = t
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(page_header("Dashboard", "Experiment tracking · embedded Aim",
                                    t, PillButton("Open in Aim", t, "ghost", "settings")))
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(34, 4, 34, 40)
        v.setSpacing(16)
        charts = QHBoxLayout()
        charts.setSpacing(16)
        charts.addWidget(self._chart_card("Training loss", "nuclei-dapi-r8 · 100 epochs",
                                          _LineChart(demo.LOSS_CURVE, t["primary"], t)))
        charts.addWidget(self._chart_card("F1 across runs", "held-out validation",
                                          _BarChart(demo.F1_BARS, t["signal"], t)))
        v.addLayout(charts)
        v.addWidget(self._runs_table())
        v.addStretch(1)
        outer.addWidget(scroll(body))

    def _chart_card(self, title: str, cap: str, chart: QWidget) -> QFrame:
        t = self._t
        card = QFrame()
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(f"background:{t['surface']}; border:1px solid {t['border']}; border-radius:14px;")
        soft_shadow(card, 14, 20, 3)
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(2)
        v.addWidget(label(title, 13.5, t["text"], 600))
        v.addWidget(label(cap, 11.5, t["text_muted"]))
        v.addSpacing(10)
        v.addWidget(chart)
        return card

    def _runs_table(self) -> QFrame:
        t = self._t
        card = QFrame()
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(f"background:{t['surface']}; border:1px solid {t['border']}; border-radius:14px;")
        soft_shadow(card, 14, 20, 3)
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 16, 18, 8)
        v.setSpacing(2)
        v.addWidget(label("Runs", 13.5, t["text"], 600))
        v.addWidget(label("6 tracked runs", 11.5, t["text_muted"]))
        v.addSpacing(8)
        header = ["Run", "Engine", "F1", "Cells", "Duration", "When"]
        hrow = QHBoxLayout()
        for i, hcol in enumerate(header):
            l = label(hcol.upper(), 10, t["text_muted"], 600, 0.5)
            hrow.addWidget(l, 2 if i == 0 else 1)
        v.addLayout(hrow)
        v.addWidget(hline(t))
        for name, eng, f1, cells, dur, when, ok in demo.DASH_RUNS:
            r = QHBoxLayout()
            cells_map = [(name, "mono"), (eng, ""), (f1, "ok" if ok else "mono"),
                         (cells, "mono"), (dur, "mono"), (when, "")]
            for i, (val, style) in enumerate(cells_map):
                if style == "mono":
                    col = t["text_subtle"]
                    fam = f"font-family:{theme.MONO};"
                elif style == "ok":
                    col = t["success"]
                    fam = f"font-family:{theme.MONO}; font-weight:600;"
                else:
                    col = t["text_subtle"]
                    fam = ""
                l = QLabel(val)
                l.setStyleSheet(f"color:{col}; font-size:12.5px; {fam}")
                r.addWidget(l, 2 if i == 0 else 1)
            rowwrap = QFrame()
            rowwrap.setLayout(r)
            r.setContentsMargins(0, 8, 0, 8)
            v.addWidget(rowwrap)
            v.addWidget(hline(t))
        return card
