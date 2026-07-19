"""CellSeg1 Studio — overlay surfaces: Logs console, command palette, toast.

Created as children of the main window; the window shows/hides and positions
them. ``LogsConsole`` is a real, live view onto ``studio.log_bus`` — every
tab's actual operational log lines (segmentation runs, training, the
Assistant's backend/connection events, app startup/crashes), not a static
``demo`` transcript — with a level filter, text search, autoscroll, clear,
and export to a file. The command palette still renders static ``demo``
content — buttons give visual feedback only. The Assistant drawer (real
chat, real diagnostics, real model management) has grown into its own
module, ``studio/assistant_panel.py`` — imported from there, not here; see
its docstring.
"""
from __future__ import annotations

import html
import time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QHBoxLayout, QVBoxLayout, QLineEdit,
    QTextEdit, QFileDialog,
)

from studio import icons
from studio import theme, demo
from studio.components import IconButton, Badge, SelectBox, Toggle, hline, label
from studio.log_bus import LogBus, LogRecord, get_log_bus, DEBUG, INFO, WARNING, ERROR, short_source


def _level_color(t: dict, rec: LogRecord) -> str:
    """The line's level colour -- status tokens for warn/error (an outcome),
    a plain/muted ink for debug/info (not "Primary hue = interactive only,"
    per DESIGN.md's rule 3), except a `on_log` success line (the existing
    `✓ ...` convention used throughout the reused ML core) reads as `success`
    even though it's technically INFO -- the console would otherwise render
    "247 cells found" in the same flat tone as routine progress chatter.
    """
    if rec.level >= ERROR:
        return t["danger"]
    if rec.level >= WARNING:
        return t["warning"]
    if rec.level >= INFO:
        return t["success"] if rec.message.startswith("✓") else t["text_subtle"]
    return t["text_muted"]


class LogsConsole(QFrame):
    """Bottom console: a real, live stream from the shared :class:`LogBus`.

    Backfills whatever the bus already holds at construction (so opening
    Logs after a background run finished still shows it), then stays live
    for as long as the widget exists. A ``QTextEdit`` rather than one
    ``QLabel`` per line (the original static version's approach) — the
    professional choice once the stream is unbounded instead of 7 fixed
    demo lines, and matches the classic app's own ``widgets/log_window.py``.
    """

    HEIGHT = 210
    _record_sig = pyqtSignal(object)

    _LEVEL_OPTIONS = ("All", "Debug", "Info", "Warn", "Error")
    _LEVEL_THRESHOLD = {"All": 0, "Debug": DEBUG, "Info": INFO, "Warn": WARNING, "Error": ERROR}

    def __init__(self, parent: QWidget, t: dict, bus: Optional[LogBus] = None):
        super().__init__(parent)
        self._t = t
        # Deliberately `is None`, not `bus or get_log_bus()` -- see
        # log_bus.install_handler's own comment: LogBus defines __len__, so
        # a freshly-constructed empty bus is falsy and a plain `or` would
        # silently discard an intentionally-injected (e.g. test) bus.
        self._bus = bus if bus is not None else get_log_bus()
        self._threshold = INFO
        self._records: list[LogRecord] = []
        self.setFixedHeight(self.HEIGHT)
        # Qualified selector: an unqualified background+border rule here
        # would cascade to every descendant that doesn't more specifically
        # override `border` (bare QWidget/QLabel have no such override) --
        # the exact rendering-bug family already found/fixed repeatedly
        # elsewhere in Studio (see AssistantDrawer's own comment).
        self.setObjectName("LogsConsole")
        self.setStyleSheet(
            f"QFrame#LogsConsole{{background:{t['surface']}; border-top:1px solid {t['border']};}}")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        head = QWidget()
        head.setStyleSheet(f"background:{t['inset']};")
        hr = QHBoxLayout(head)
        hr.setContentsMargins(14, 8, 12, 8)
        hr.setSpacing(8)
        hr.addWidget(label("LOGS", 11.5, t["text_subtle"], 600, 0.6))
        self._badge = Badge("0", t)
        hr.addWidget(self._badge)
        hr.addStretch(1)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter…")
        self._search.setFixedWidth(140)
        self._search.setStyleSheet(
            f"QLineEdit{{background:{t['surface']}; border:1px solid {t['border']};"
            f"border-radius:6px; padding:4px 8px; font-size:11.5px; min-height:0;}}")
        self._search.textChanged.connect(lambda _text: self._rerender())
        hr.addWidget(self._search)

        self._level = SelectBox("Info", t, options=list(self._LEVEL_OPTIONS),
                                 on_select=self._on_level_selected)
        # SelectBox has no stretch factor of its own -- everywhere else it's
        # used, its container either gives it a stretch factor or is the
        # sole child of a vertical layout (which stretches it to the full
        # container width regardless of sizeHint). Packed into a QHBoxLayout
        # next to other siblings with real stretch (the search box, the
        # earlier addStretch), Qt instead honours SelectBox's own sizeHint
        # literally -- and that sizeHint under-reports the width its value
        # label + chevron actually need, so "Debug"/"Error" collapsed to a
        # sliver (confirmed by inspecting _val's allocated geometry: width 0)
        # with only the chevron visibly left. A floor wide enough for the
        # longest option (measured: "Debug"/"Error" at 42px) plus its icon
        # and margins fixes this locally without touching the shared atom.
        self._level.setMinimumWidth(96)
        hr.addWidget(self._level)

        self._autoscroll = Toggle(t, on=True)
        self._autoscroll.toggled.connect(self._on_autoscroll_toggled)
        hr.addWidget(self._autoscroll)
        hr.addWidget(label("Auto", 10.5, t["text_muted"]))

        hr.addWidget(IconButton("trash", t, 27, "Clear", self._on_clear))
        hr.addWidget(IconButton("download", t, 27, "Save to file…", self._export))
        hr.addWidget(IconButton("close", t, 27, "Close", self.hide))
        v.addWidget(head)
        v.addWidget(hline(t))

        # Always a dark "scope" ground regardless of the app's light/dark
        # theme (same token the image viewport uses) -- a log console reads
        # as an instrument, not a page, in both themes; deliberate, not an
        # oversight (see theme.py's "the bench & the scope" concept).
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFrameShape(QFrame.Shape.NoFrame)
        self._text.setStyleSheet(
            f"QTextEdit{{background:{t['scope']}; border:none; padding:8px 14px;"
            f"color:#aeb9c7; font-family:{theme.MONO}; font-size:11.5px;}}")
        v.addWidget(self._text, 1)

        self._record_sig.connect(self._on_record)
        backlog, unsubscribe = self._bus.subscribe(self._safe_emit_record)
        self._unsubscribe = unsubscribe
        # Fires on real C++ destruction regardless of how it happens
        # (deleteLater during a theme toggle's overlay teardown, or a
        # test's sip.delete()) -- more robust than trying to catch every
        # teardown path by hand, and avoids leaking a subscriber closure
        # onto the bus for the rest of the process's life.
        self.destroyed.connect(unsubscribe)
        self._records = list(backlog)
        self._rerender()
        self._badge.setText(self._badge_text())
        self.hide()

    # ── filtering / rendering ────────────────────────────────────────────────
    def _matches(self, rec: LogRecord) -> bool:
        if rec.level < self._threshold:
            return False
        q = self._search.text().strip().lower()
        if not q:
            return True
        return q in rec.message.lower() or q in short_source(rec.source).lower()

    def _format_parts(self, rec: LogRecord) -> tuple[str, str, str]:
        ts = time.strftime("%H:%M:%S", time.localtime(rec.ts))
        return ts, rec.level_name, short_source(rec.source)

    def _line_html(self, rec: LogRecord) -> str:
        ts, lvl, src = self._format_parts(rec)
        color = _level_color(self._t, rec)
        msg = html.escape(rec.message).replace("\n", "<br>&nbsp;&nbsp;&nbsp;&nbsp;")
        lvl_pad = html.escape(lvl.ljust(8)).replace(" ", "&nbsp;")
        src_pad = html.escape(src.ljust(10)).replace(" ", "&nbsp;")
        return (
            f"<div><span style='color:#5b6472'>{ts}</span>&nbsp;&nbsp;"
            f"<span style='color:{color};font-weight:700'>{lvl_pad}</span>"
            f"<span style='color:#6c7480'>{src_pad}</span>"
            f"<span>{msg}</span></div>"
        )

    def _plain_line(self, rec: LogRecord) -> str:
        ts, lvl, src = self._format_parts(rec)
        return f"{ts}  {lvl:<8}{src:<10}{rec.message}"

    def _rerender(self) -> None:
        matching = [r for r in self._records if self._matches(r)]
        self._text.setHtml("".join(self._line_html(r) for r in matching))
        sb = self._text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _badge_text(self) -> str:
        total = len(self._records)
        errors = sum(1 for r in self._records if r.level >= ERROR)
        warns = sum(1 for r in self._records if r.level == WARNING)
        parts = [str(total)]
        if errors:
            parts.append(f"{errors} err")
        if warns:
            parts.append(f"{warns} warn")
        return " · ".join(parts)

    # ── live updates (bus -> Qt main thread) ────────────────────────────────
    # A record can arrive from any thread (a predict/training worker, the
    # Assistant's urllib SSE thread) -- guarded the same way every other
    # cross-thread emit in Studio is (ModelsScreen._safe_emit_log, etc.): a
    # background callback can outlive this widget (torn down by a theme
    # toggle mid-run), and emitting a signal on a since-deleted QObject
    # raises RuntimeError.
    def _safe_emit_record(self, rec: LogRecord) -> None:
        try:
            self._record_sig.emit(rec)
        except RuntimeError:
            pass

    def _on_record(self, rec: LogRecord) -> None:
        self._records.append(rec)
        self._badge.setText(self._badge_text())
        if self._matches(rec):
            self._text.append(self._line_html(rec))
            if self._autoscroll.is_on():
                sb = self._text.verticalScrollBar()
                sb.setValue(sb.maximum())

    # ── toolbar actions ──────────────────────────────────────────────────────
    def _on_level_selected(self, choice: str) -> None:
        self._threshold = self._LEVEL_THRESHOLD[choice]
        self._rerender()

    def _on_autoscroll_toggled(self, on: bool) -> None:
        if on:
            sb = self._text.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _on_clear(self) -> None:
        self._bus.clear()
        self._records = []
        self._text.clear()
        self._badge.setText(self._badge_text())

    def _export(self) -> None:
        default_name = f"cellseg1-studio-logs-{time.strftime('%Y%m%d-%H%M%S')}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save logs", default_name, "Text files (*.txt);;All files (*)")
        if not path:
            return
        lines = [self._plain_line(r) for r in self._records if self._matches(r)]
        Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def place(self):
        p = self.parentWidget()
        if p:
            from studio.components import Sidebar
            x = Sidebar.WIDTH
            self.setGeometry(x, p.height() - self.HEIGHT, p.width() - x, self.HEIGHT)


class CommandPalette(QWidget):
    """Centered ⌘K command palette over a scrim."""

    def __init__(self, parent: QWidget, t: dict):
        super().__init__(parent)
        self._t = t
        self.setStyleSheet("background:rgba(8,10,20,0.34);")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 96, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        outer.addWidget(self._panel())
        self.hide()

    def _panel(self) -> QFrame:
        t = self._t
        panel = QFrame()
        panel.setFixedWidth(560)
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        panel.setObjectName("PalettePanel")   # qualified -- see AssistantDrawer's comment
        panel.setStyleSheet(
            f"QFrame#PalettePanel{{background:{t['surface']}; border:1px solid {t['border_strong']};"
            f" border-radius:14px;}}")
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        inp_wrap = QWidget()
        ir = QHBoxLayout(inp_wrap)
        ir.setContentsMargins(17, 15, 17, 15)
        ir.setSpacing(11)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("diagnose", t["text_muted"], 17))
        ir.addWidget(ic)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Search actions, projects, engines…")
        self.input.setStyleSheet("QLineEdit{border:none; background:transparent; font-size:15px;}")
        ir.addWidget(self.input, 1)
        esc = QLabel("ESC")
        esc.setStyleSheet(
            f"color:{t['text_muted']}; font-family:{theme.MONO}; font-size:10.5px;"
            f"border:1px solid {t['border']}; border-radius:5px; padding:2px 6px;")
        ir.addWidget(esc)
        v.addWidget(inp_wrap)
        v.addWidget(hline(t))

        section = None
        for i, (sec, icon_name, text, hint) in enumerate(demo.PALETTE):
            if sec != section:
                section = sec
                sl = label(sec.upper(), 10.5, t["text_muted"], 600, 0.6)
                sl.setContentsMargins(17, 12, 17, 5)
                v.addWidget(sl)
            v.addWidget(self._item(icon_name, text, hint, highlighted=(i == 0)))

        foot = QWidget()
        fr = QHBoxLayout(foot)
        fr.setContentsMargins(17, 10, 17, 10)
        fr.setSpacing(16)
        for k, act in [("↑↓", "navigate"), ("⏎", "run"), ("esc", "close")]:
            fr.addWidget(label(f"<span style='font-family:{theme.MONO}'>{k}</span> {act}", 11, t["text_muted"]))
        fr.addStretch(1)
        v.addWidget(hline(t))
        v.addWidget(foot)
        return panel

    def _item(self, icon_name: str, text: str, hint: str, highlighted: bool) -> QFrame:
        t = self._t
        row = QFrame()
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setStyleSheet(
            (f"QFrame{{background:{t['primary_weak']};}}" if highlighted else "QFrame{background:transparent;}") +
            f"QFrame:hover{{background:{t['primary_weak']};}}")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(17, 10, 17, 10)
        lay.setSpacing(12)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, t["primary"] if highlighted else t["text_muted"], 16))
        lay.addWidget(ic)
        lay.addWidget(label(text, 13.5, t["text"] if highlighted else t["text_subtle"]))
        lay.addStretch(1)
        if hint:
            lay.addWidget(label(hint, 10.5, t["text_muted"]))
        return row

    def place(self):
        p = self.parentWidget()
        if p:
            self.setGeometry(0, 0, p.width(), p.height())

    def open(self):
        self.place()
        self.show()
        self.raise_()
        self.input.setFocus()

    def mousePressEvent(self, e):
        # click on the scrim (outside the panel) closes
        child = self.childAt(e.position().toPoint())
        if child is None:
            self.hide()
        super().mousePressEvent(e)


class Toast(QFrame):
    """Bottom-right success toast. Static by default; ``announce()`` for real use."""

    def __init__(self, parent: QWidget, t: dict):
        super().__init__(parent)
        self._t = t
        self.setObjectName("Toast")   # qualified -- see AssistantDrawer's comment
        self.setStyleSheet(
            f"QFrame#Toast{{background:{t['surface']}; border:1px solid {t['border']};"
            f"border-left:3px solid {t['success']}; border-radius:11px;}}")
        row = QHBoxLayout(self)
        row.setContentsMargins(15, 12, 15, 12)
        row.setSpacing(12)
        ic = QLabel()
        ic.setFixedSize(30, 30)
        ic.setPixmap(icons.pixmap("check", t["success"], 16))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setStyleSheet(f"background:{t['success_weak']}; border-radius:8px;")
        row.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(1)
        self._title = label("Segmentation complete", 13, t["text"], 600)
        col.addWidget(self._title)
        self._subtitle = label("247 cells · F1 0.94 vs ground truth · 3.2 s", 11.5, t["text_muted"])
        self._subtitle.setWordWrap(True)
        self._subtitle.setMaximumWidth(280)  # wrap long messages instead of clipping/overflowing
        col.addWidget(self._subtitle)
        row.addLayout(col)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self.hide()

    def place(self):
        p = self.parentWidget()
        if p:
            self.adjustSize()
            self.move(p.width() - self.width() - 22, p.height() - self.height() - 22)

    def announce(self, title: str, subtitle: str, duration_ms: int = 3200) -> None:
        """Show a real, timed confirmation with the given text."""
        self._title.setText(title)
        self._subtitle.setText(subtitle)
        self.place()
        self.show()
        self.raise_()
        self._hide_timer.start(duration_ms)
