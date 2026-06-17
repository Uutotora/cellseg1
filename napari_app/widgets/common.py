from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QSizePolicy,
)
from napari_app.theme import BORDER, DIM, TEXT, ACCENT


def section_header(text: str) -> QWidget:
    """Static section label with blue left-accent bar."""
    container = QWidget()
    container.setContentsMargins(0, 0, 0, 0)
    row = QHBoxLayout()
    row.setContentsMargins(0, 14, 0, 5)
    row.setSpacing(8)

    bar = QFrame()
    bar.setFixedWidth(2)
    bar.setFixedHeight(11)
    bar.setStyleSheet(f"background: {ACCENT}; border-radius: 1px;")

    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"color: {DIM};"
        f"font-size: 11px;"
        f"font-weight: 700;"
        f"letter-spacing: 1.5px;"
    )

    row.addWidget(bar)
    row.addWidget(lbl)
    row.addStretch()
    container.setLayout(row)
    return container


def divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {BORDER}; border: none; margin: 4px 0;")
    return f


def param_row(label_text: str, widget, tip: str = "", label_width: int = 120) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(10)
    lbl = QLabel(label_text)
    lbl.setStyleSheet(f"color: {DIM}; font-size: 12px;")
    lbl.setFixedWidth(label_width)
    if tip:
        lbl.setToolTip(tip)
        widget.setToolTip(tip)
    row.addWidget(lbl)
    row.addWidget(widget)
    return row


# kept for compatibility — code that still imports CollapsibleSection
# renders as a plain always-open container now
class CollapsibleSection(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        vbox = QVBoxLayout()
        vbox.setSpacing(6)
        vbox.setContentsMargins(0, 0, 0, 0)

        # static header — matches section_header() style
        vbox.addWidget(section_header(title))

        self._content = QWidget()
        self._cl = QVBoxLayout()
        self._cl.setSpacing(6)
        self._cl.setContentsMargins(0, 0, 0, 0)
        self._content.setLayout(self._cl)
        vbox.addWidget(self._content)

        self.setLayout(vbox)

    def addWidget(self, w):
        self._cl.addWidget(w)

    def addLayout(self, lay):
        self._cl.addLayout(lay)

    # no-op: kept so existing callers don't crash
    def _on_toggle(self, checked: bool):
        pass
