"""A modern chat surface for the Assistant — message bubbles, an assistant
avatar, a streaming typing indicator and an empty state.

Presentation only: the agent (advisor / Ollama / threads / signals) is unchanged.
The widget exposes a small API the AssistantWidget drives:

    add_user(text)              user bubble (right)
    add_assistant_start()       open a streaming assistant bubble (left)
    append_token(text)          stream text into the open assistant bubble
    assistant_done()            finalise the streaming bubble
    add_assistant_full(text)    a complete assistant bubble (offline answer)
    system_note(text)           a centred, dim status line
    add_widget(w)               drop an arbitrary widget into the flow
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
)

from napari_app import icons
from napari_app.theme import (
    ACCENT, CARD_HEADER, INPUT, TEXT, LABEL, DIM, TEAL, TEAL_SOFT, BORDER, R_LG,
)

BUBBLE_MAXW = 300


class _TypingDots(QLabel):
    """A tiny animated 'assistant is typing' indicator."""

    def __init__(self):
        super().__init__("●   ·   ·")
        self.setStyleSheet(f"color:{TEAL}; font-size:11px; background:transparent;")
        self._i = 0
        self._t = QTimer(self)
        self._t.setInterval(340)
        self._t.timeout.connect(self._tick)
        self._t.start()

    def _tick(self):
        seq = ("●   ·   ·", "·   ●   ·", "·   ·   ●")
        self.setText(seq[self._i % 3])
        self._i += 1

    def stop(self):
        self._t.stop()
        self.hide()
        self.deleteLater()


class ChatView(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setObjectName("ChatView")
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setStyleSheet(
            f"#ChatView {{ background:{INPUT}; border:1px solid {BORDER};"
            f" border-radius:{R_LG}px; }}")

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{INPUT};")
        self._v = QVBoxLayout(self._body)
        self._v.setContentsMargins(12, 14, 12, 14)
        self._v.setSpacing(12)
        self._v.addStretch()
        self.setWidget(self._body)

        self._cur: QLabel | None = None
        self._cur_text = ""
        self._typing: _TypingDots | None = None
        self._empty: QWidget | None = None
        self._build_empty()

    # ── empty state ──────────────────────────────────────────────────────────
    def _build_empty(self):
        self._empty = QWidget()
        el = QVBoxLayout(self._empty)
        el.setContentsMargins(0, 40, 0, 0)
        el.setSpacing(9)
        el.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("spark", TEAL, 30))
        ic.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        t = QLabel("Ask the assistant")
        t.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        t.setStyleSheet(f"color:{TEXT}; font-size:13px; font-weight:600; background:transparent;")
        s = QLabel("It sees your image and mask, and can tune the pipeline.\n"
                   "e.g. “why are my cells over-merged?”")
        s.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        s.setWordWrap(True)
        s.setStyleSheet(f"color:{DIM}; font-size:11px; background:transparent;")
        el.addWidget(ic)
        el.addWidget(t)
        el.addWidget(s)
        self._insert(self._empty)

    def _hide_empty(self):
        if self._empty is not None:
            self._empty.hide()

    # ── flow helpers ─────────────────────────────────────────────────────────
    def _insert(self, w):
        self._v.insertWidget(self._v.count() - 1, w)  # before the trailing stretch

    def _scroll(self):
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(
            self.verticalScrollBar().maximum()))

    def _bubble(self, text: str, bg: str, fg: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setMaximumWidth(BUBBLE_MAXW)
        lbl.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:12px;"
            f" padding:9px 12px; font-size:12.5px;")
        return lbl

    def _row(self, inner, align: str):
        w = QWidget()
        r = QHBoxLayout(w)
        r.setContentsMargins(0, 0, 0, 0)
        r.setSpacing(8)
        if align == "right":
            r.addStretch()
            r.addWidget(inner)
        else:
            r.addWidget(inner)
            r.addStretch()
        self._insert(w)
        self._scroll()
        return w

    def _assistant_container(self):
        w = QWidget()
        r = QHBoxLayout(w)
        r.setContentsMargins(0, 0, 0, 0)
        r.setSpacing(9)
        av = QLabel()
        av.setFixedSize(26, 26)
        av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av.setPixmap(icons.pixmap("spark", TEAL, 15))
        av.setStyleSheet(f"background:{TEAL_SOFT}; border-radius:13px;")
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(5)
        r.addWidget(av, alignment=Qt.AlignmentFlag.AlignTop)
        r.addLayout(col)
        r.addStretch()
        self._insert(w)
        self._scroll()
        return col

    # ── public API ───────────────────────────────────────────────────────────
    def add_user(self, text: str):
        self._hide_empty()
        self._row(self._bubble(text, ACCENT, "#ffffff"), "right")

    def add_assistant_start(self):
        self._hide_empty()
        col = self._assistant_container()
        self._cur = self._bubble("", CARD_HEADER, TEXT)
        self._cur.hide()  # hidden until the first token arrives
        self._cur_text = ""
        col.addWidget(self._cur)
        self._typing = _TypingDots()
        col.addWidget(self._typing, alignment=Qt.AlignmentFlag.AlignLeft)
        self._scroll()

    def append_token(self, t: str):
        if self._cur is None:
            return
        self._cur_text += t
        self._cur.setText(self._cur_text)
        if self._cur_text.strip():
            self._cur.show()
        self._scroll()

    def assistant_done(self):
        if self._typing is not None:
            self._typing.stop()
            self._typing = None
        if self._cur is not None and not self._cur_text.strip():
            self._cur.setText("(no response)")
            self._cur.show()
        self._cur = None
        self._scroll()

    def add_assistant_full(self, text: str):
        self._hide_empty()
        col = self._assistant_container()
        col.addWidget(self._bubble(text, CARD_HEADER, TEXT))
        self._scroll()

    def system_note(self, text: str):
        self._hide_empty()
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{DIM}; font-size:10.5px; background:transparent;")
        self._insert(lbl)
        self._scroll()

    def add_widget(self, w):
        self._hide_empty()
        self._insert(w)
        self._scroll()
