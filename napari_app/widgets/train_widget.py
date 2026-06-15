import os
import threading
from pathlib import Path

import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QProgressBar, QFileDialog, QScrollArea, QFrame,
    QGroupBox, QSizePolicy, QTextEdit,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

from gui.pages.utils.train_state_manager import TrainingStateManager
from project_root import STORAGE_DIR

TRAIN_IMAGE_DIR  = STORAGE_DIR / "train_images"
TRAIN_MASK_DIR   = STORAGE_DIR / "train_masks"
LORA_OUT_DIR     = STORAGE_DIR / "loras"
SAM_BACKBONE_DIR = STORAGE_DIR / "sam_backbone"

STATE_MANAGER = TrainingStateManager(str(STORAGE_DIR))
_DLG = QFileDialog.Option.DontUseNativeDialog

PRESETS = {
    "Fast · MPS": {
        "epochs": 150, "batch_size": 1, "grad_accum": 32,
        "lr": 3e-3, "lora_rank": 4, "resize_size": "512",
    },
    "Balanced": {
        "epochs": 300, "batch_size": 1, "grad_accum": 32,
        "lr": 3e-3, "lora_rank": 4, "resize_size": "512",
    },
    "Best quality": {
        "epochs": 500, "batch_size": 1, "grad_accum": 32,
        "lr": 1e-3, "lora_rank": 8, "resize_size": "1024",
    },
}


def _pick_dir(parent, line_edit, start=None):
    start = start or (line_edit.text() if line_edit.text() else str(Path.home()))
    path = QFileDialog.getExistingDirectory(parent, "Select folder", start, _DLG)
    if path:
        line_edit.setText(path)


def _pick_file(parent, line_edit, caption="Select file", ext="All (*)", start=None):
    start = start or (str(Path(line_edit.text()).parent) if line_edit.text() else str(Path.home()))
    path, _ = QFileDialog.getOpenFileName(parent, caption, start, ext, options=_DLG)
    if path:
        line_edit.setText(path)


def _pick_save(parent, line_edit, start=None):
    start = start or str(LORA_OUT_DIR)
    path, _ = QFileDialog.getSaveFileName(
        parent, "Save checkpoint as", start, "PyTorch (*.pth)", options=_DLG)
    if path:
        if not path.endswith(".pth"):
            path += ".pth"
        line_edit.setText(path)


def _divider():
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("color: #3a3a3a; margin: 2px 0;")
    return f


def _section(text, color="#90CAF9"):
    lbl = QLabel(text)
    font = QFont()
    font.setBold(True)
    font.setPointSize(11)
    lbl.setFont(font)
    lbl.setStyleSheet(f"color: {color}; margin-top: 8px; margin-bottom: 2px;")
    return lbl


class LossChart(QWidget):
    """Embedded matplotlib loss chart."""

    def __init__(self):
        super().__init__()
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure

        self.fig = Figure(figsize=(3, 1.6), dpi=90)
        self.fig.patch.set_facecolor("#1a1a2e")
        self.ax = self.fig.add_subplot(111)
        self._style_ax()

        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.canvas.setFixedHeight(150)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        self.setLayout(layout)
        self.setVisible(False)

    def _style_ax(self):
        ax = self.ax
        ax.set_facecolor("#0d0d1a")
        ax.tick_params(colors="#888", labelsize=8)
        ax.set_xlabel("Epoch", color="#888", fontsize=8)
        ax.set_ylabel("Loss",  color="#888", fontsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor("#333")
        self.fig.tight_layout(pad=0.5)

    def update(self, loss_history: list, epoch_max: int):
        if not loss_history:
            return
        epochs = [d["epoch"] for d in loss_history]
        losses = [d["loss"]  for d in loss_history]

        self.ax.cla()
        self._style_ax()
        self.ax.plot(epochs, losses, color="#ef4444", linewidth=1.5)
        self.ax.fill_between(epochs, losses, alpha=0.15, color="#ef4444")
        if epoch_max:
            self.ax.set_xlim(1, epoch_max)
        self.ax.set_title(
            f"Loss: {losses[-1]:.5f}  (best {min(losses):.5f})",
            color="#ccc", fontsize=8, pad=2)
        self.fig.tight_layout(pad=0.5)
        self.canvas.draw_idle()
        self.setVisible(True)


class TrainWidget(QWidget):
    _log_signal    = pyqtSignal(str)
    _finish_signal = pyqtSignal()

    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self._train_thread = None

        outer = QVBoxLayout()
        outer.setSpacing(4)
        outer.setContentsMargins(8, 8, 8, 8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        L = QVBoxLayout()
        L.setSpacing(4)
        L.setContentsMargins(0, 0, 0, 0)

        # ── Presets ──────────────────────────────────────────────────────────
        L.addWidget(_section("Presets", "#90CAF9"))
        preset_row = QHBoxLayout()
        for name, vals in PRESETS.items():
            btn = QPushButton(name)
            btn.setFixedHeight(28)
            btn.setStyleSheet(
                "background:#1a2a3a; color:#90CAF9; border:1px solid #2a4a6a;"
                "border-radius:3px; font-size:11px;")
            btn.clicked.connect(lambda checked, v=vals: self._apply_preset(v))
            preset_row.addWidget(btn)
        L.addLayout(preset_row)

        L.addWidget(_divider())

        # ── Data folders ─────────────────────────────────────────────────────
        L.addWidget(_section("Training data", "#90CAF9"))
        TRAIN_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        TRAIN_MASK_DIR.mkdir(parents=True, exist_ok=True)

        L.addWidget(QLabel("Image folder"))
        self.image_dir = QLineEdit(str(TRAIN_IMAGE_DIR))
        r1 = QHBoxLayout()
        r1.addWidget(self.image_dir)
        b1 = QPushButton("…"); b1.setFixedWidth(30)
        b1.clicked.connect(lambda: _pick_dir(self, self.image_dir, str(TRAIN_IMAGE_DIR)))
        r1.addWidget(b1)
        L.addLayout(r1)

        L.addWidget(QLabel("Mask folder"))
        self.mask_dir = QLineEdit(str(TRAIN_MASK_DIR))
        r2 = QHBoxLayout()
        r2.addWidget(self.mask_dir)
        b2 = QPushButton("…"); b2.setFixedWidth(30)
        b2.clicked.connect(lambda: _pick_dir(self, self.mask_dir, str(TRAIN_MASK_DIR)))
        r2.addWidget(b2)
        L.addLayout(r2)

        L.addWidget(QLabel("Output checkpoint"))
        LORA_OUT_DIR.mkdir(parents=True, exist_ok=True)
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("auto-named in streamlit_storage/loras/")
        r3 = QHBoxLayout()
        r3.addWidget(self.output_path)
        b3 = QPushButton("…"); b3.setFixedWidth(30)
        b3.clicked.connect(lambda: _pick_save(self, self.output_path))
        r3.addWidget(b3)
        L.addLayout(r3)

        L.addWidget(_divider())

        # ── Model ────────────────────────────────────────────────────────────
        L.addWidget(_section("Model", "#90CAF9"))

        row_vit = QHBoxLayout()
        row_vit.addWidget(QLabel("SAM type"))
        self.vit_name = QComboBox()
        self.vit_name.addItems(["vit_h", "vit_l", "vit_b"])
        self.vit_name.currentTextChanged.connect(self._on_vit_changed)
        row_vit.addWidget(self.vit_name)
        L.addLayout(row_vit)

        L.addWidget(QLabel("SAM backbone"))
        self.sam_path = QLineEdit()
        self.sam_path.setPlaceholderText("auto")
        r_sam = QHBoxLayout()
        r_sam.addWidget(self.sam_path)
        b_sam = QPushButton("…"); b_sam.setFixedWidth(30)
        b_sam.clicked.connect(lambda: _pick_file(
            self, self.sam_path, "Select SAM backbone", "PyTorch (*.pth)", str(SAM_BACKBONE_DIR)))
        r_sam.addWidget(b_sam)
        L.addLayout(r_sam)
        self._on_vit_changed("vit_h")

        row_rank = QHBoxLayout()
        row_rank.addWidget(QLabel("LoRA rank"))
        self.lora_rank = QSpinBox()
        self.lora_rank.setRange(1, 64)
        self.lora_rank.setValue(4)
        row_rank.addWidget(self.lora_rank)
        L.addLayout(row_rank)

        L.addWidget(_divider())

        # ── Training ─────────────────────────────────────────────────────────
        L.addWidget(_section("Training", "#90CAF9"))

        row_rs = QHBoxLayout()
        row_rs.addWidget(QLabel("Resize size"))
        self.resize_size = QComboBox()
        for v in ["256", "512", "768", "1024"]:
            self.resize_size.addItem(v)
        self.resize_size.setCurrentText("512")
        row_rs.addWidget(self.resize_size)
        L.addLayout(row_rs)

        for label, attr, lo, hi, val in [
            ("Epochs",           "epochs",     1,   2000, 300),
            ("Batch size",       "batch_size", 1,   16,   1),
            ("Grad accumulation","grad_accum", 1,   128,  32),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            w = QSpinBox(); w.setRange(lo, hi); w.setValue(val)
            setattr(self, attr, w)
            row.addWidget(w)
            L.addLayout(row)

        row_lr = QHBoxLayout()
        row_lr.addWidget(QLabel("Learning rate"))
        self.lr = QDoubleSpinBox()
        self.lr.setDecimals(5)
        self.lr.setRange(1e-6, 1.0)
        self.lr.setSingleStep(1e-4)
        self.lr.setValue(3e-3)
        row_lr.addWidget(self.lr)
        L.addLayout(row_lr)

        row_dev = QHBoxLayout()
        row_dev.addWidget(QLabel("Device"))
        self.device = QComboBox()
        self._populate_devices()
        row_dev.addWidget(self.device)
        L.addLayout(row_dev)

        L.addWidget(_divider())

        # ── Buttons ──────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("▶  Start Training")
        self.start_btn.setFixedHeight(38)
        self.start_btn.setStyleSheet(
            "background:#1565C0; color:white; font-weight:bold; border-radius:5px; font-size:13px;")
        self.start_btn.clicked.connect(self._start_training)
        btn_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("■  Stop")
        self.stop_btn.setFixedHeight(38)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setFixedWidth(80)
        self.stop_btn.setStyleSheet(
            "background:#B71C1C; color:white; font-weight:bold; border-radius:5px;")
        self.stop_btn.clicked.connect(self._stop_training)
        btn_row.addWidget(self.stop_btn)
        L.addLayout(btn_row)

        # ── Progress ─────────────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        L.addWidget(self.progress_bar)

        status_row = QHBoxLayout()
        self.epoch_lbl = QLabel("Epoch: —")
        self.loss_lbl  = QLabel("Loss: —")
        self.epoch_lbl.setStyleSheet("color:#ccc; font-size:12px;")
        self.loss_lbl.setStyleSheet("color:#ef9999; font-size:12px;")
        status_row.addWidget(self.epoch_lbl)
        status_row.addStretch()
        status_row.addWidget(self.loss_lbl)
        L.addLayout(status_row)

        # ── Loss chart ───────────────────────────────────────────────────────
        self.loss_chart = LossChart()
        L.addWidget(self.loss_chart)

        # ── Training history ─────────────────────────────────────────────────
        L.addWidget(_section("History", "#90CAF9"))
        self.history_box = QTextEdit()
        self.history_box.setReadOnly(True)
        self.history_box.setMaximumHeight(100)
        self.history_box.setStyleSheet(
            "background:#0d1117; color:#888; font-family:Menlo,Monaco,Courier; font-size:10px;")
        L.addWidget(self.history_box)
        self._refresh_history()

        # ── Log ──────────────────────────────────────────────────────────────
        L.addWidget(_section("Log", "#90CAF9"))
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(110)
        self.log_box.setStyleSheet(
            "background:#1A1A2E; color:#A0A0C0; font-family:Menlo,Monaco,Courier; font-size:11px;")
        L.addWidget(self.log_box)

        L.addStretch()
        inner.setLayout(L)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self.setLayout(outer)
        self.setMinimumWidth(320)

        self._log_signal.connect(self._append_log)
        self._finish_signal.connect(self._on_finish)

        self._timer = QTimer()
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll_progress)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _populate_devices(self):
        import torch
        self.device.addItem("cpu")
        if torch.backends.mps.is_available():
            self.device.addItem("mps")
            self.device.setCurrentText("mps")
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                self.device.addItem(str(i))

    def _on_vit_changed(self, vit):
        names = {"vit_h": "sam_vit_h_4b8939.pth",
                 "vit_l": "sam_vit_l_0b3195.pth",
                 "vit_b": "sam_vit_b_01ec64.pth"}
        cand = SAM_BACKBONE_DIR / names.get(vit, "")
        if cand.exists():
            self.sam_path.setText(str(cand))
        else:
            self.sam_path.clear()
            self.sam_path.setPlaceholderText(f"Not found: {cand.name}")

    def _apply_preset(self, vals):
        self.epochs.setValue(vals["epochs"])
        self.batch_size.setValue(vals["batch_size"])
        self.grad_accum.setValue(vals["grad_accum"])
        self.lr.setValue(vals["lr"])
        self.lora_rank.setValue(vals["lora_rank"])
        self.resize_size.setCurrentText(vals["resize_size"])
        self._append_log(f"Preset applied: {vals['epochs']} epochs, rank {vals['lora_rank']}, resize {vals['resize_size']}")

    def _resolve_sam_path(self):
        p = self.sam_path.text().strip()
        if p and Path(p).exists():
            return p
        vit = self.vit_name.currentText()
        names = {"vit_h": "sam_vit_h_4b8939.pth",
                 "vit_l": "sam_vit_l_0b3195.pth",
                 "vit_b": "sam_vit_b_01ec64.pth"}
        cand = SAM_BACKBONE_DIR / names[vit]
        if cand.exists():
            return str(cand)
        raise ValueError(f"SAM backbone not found. Place {names[vit]} in {SAM_BACKBONE_DIR}/")

    def _resolve_output_path(self):
        p = self.output_path.text().strip()
        if p:
            return p if p.endswith(".pth") else p + ".pth"
        from datetime import datetime
        ts   = datetime.now().strftime("%Y%m%d-%H%M%S")
        vit  = self.vit_name.currentText()
        rank = self.lora_rank.value()
        rs   = self.resize_size.currentText()
        return str(LORA_OUT_DIR / f"lora_{vit}_r{rank}_s{rs}_{ts}.pth")

    def _build_config(self):
        sam_path   = self._resolve_sam_path()
        image_dir  = self.image_dir.text().strip()
        mask_dir   = self.mask_dir.text().strip()
        output     = self._resolve_output_path()

        if not image_dir or not Path(image_dir).exists():
            raise ValueError(f"Image folder not found: {image_dir}")
        if not mask_dir or not Path(mask_dir).exists():
            raise ValueError(f"Mask folder not found: {mask_dir}")

        img_files = sorted([
            f for f in Path(image_dir).iterdir()
            if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".npy")
        ])
        if not img_files:
            raise ValueError(f"No images found in {image_dir}")

        Path(output).parent.mkdir(parents=True, exist_ok=True)
        rs = int(self.resize_size.currentText())

        return {
            "deterministic": True,
            "seed": 0,
            "allow_tf32_on_cudnn":  True,
            "allow_tf32_on_matmul": True,
            "vit_name":    self.vit_name.currentText(),
            "model_path":  sam_path,
            "train_image_dir": image_dir,
            "train_mask_dir":  mask_dir,
            "result_pth_path": output,
            "resize_size": [rs, rs],
            "patch_size":  rs // 2,
            "sam_image_size": rs,
            "train_id":    list(range(len(img_files))),
            "duplicate_data": 32,
            "epoch_max":   self.epochs.value(),
            "batch_size":  self.batch_size.value(),
            "gradient_accumulation_step": self.grad_accum.value(),
            "base_lr":     self.lr.value(),
            "onecycle_lr_pct_start": 0.3,
            "num_workers": 0,
            "image_encoder_lora_rank":          self.lora_rank.value(),
            "mask_decoder_lora_rank":           self.lora_rank.value(),
            "freeze_image_encoder":             True,
            "freeze_prompt_encoder":            True,
            "freeze_mask_decoder_transformer":  True,
            "freeze_upscaling_cnn":             True,
            "freeze_output_hypernetworks_mlps": True,
            "freeze_mask_decoder_mask_tokens":  True,
            "freeze_mask_decoder_iou":          True,
            "lora_dropout": 0.1,
            "pos_rate": 1.0, "neg_rate": 0.5, "max_point_num": 30,
            "edge_distance": 20, "neg_area_ratio_threshold": 5,
            "neg_area_threshold": 1000, "min_cell_area": 100,
            "foreground_sample_area_ratio": 0.2,
            "background_sample_area_ratio": 0.2,
            "foreground_equal_prob": True,
            "background_equal_prob": True,
            "data_augmentation": True,
            "bright_limit": 0.1, "contrast_limit": 0.1,
            "bright_prob": 0.5, "flip_prob": 0.75, "rotate_prob": 0.8,
            "scale_limit": [-0.5, 0.5], "crop_prob": 0.5,
            "crop_scale": [0.3, 1.0], "crop_ratio": [0.75, 1.3333],
            "ce_loss_weight": 1.0, "punish_background_point": False,
            "track_gpu_memory": False,
            "selected_device": self.device.currentText(),
        }

    def _refresh_history(self):
        history = STATE_MANAGER.load_history()
        if not history:
            self.history_box.setPlainText("No training runs yet.")
            return
        lines = []
        for h in history[:5]:  # show last 5
            ts    = h.get("started_at", "")[:16].replace("T", " ")
            fl    = h.get("final_loss")
            ep    = h.get("epochs_run", 0)
            ep_mx = h.get("epoch_max", "")
            ckpt  = Path(h.get("checkpoint", "")).name
            status = "✓" if h.get("status") == "completed" else "✗"
            loss_str = f"{fl:.5f}" if fl is not None else "—"
            lines.append(f"{status} {ts}  ep {ep}/{ep_mx}  loss {loss_str}  {ckpt}")
        self.history_box.setPlainText("\n".join(lines))

    # ── Training actions ─────────────────────────────────────────────────────

    def _start_training(self):
        try:
            config = self._build_config()
        except ValueError as e:
            self._append_log(f"[ERROR] {e}")
            return

        STATE_MANAGER.clear_training_state()
        STATE_MANAGER.clear_stop_flag()
        STATE_MANAGER.clear_loss_history()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.epoch_lbl.setText("Epoch: 0")
        self.loss_lbl.setText("Loss: —")
        self.loss_chart.setVisible(False)
        self._append_log(f"Starting — {self.epochs.value()} epochs, rank {self.lora_rank.value()}, device {self.device.currentText()}")

        def run():
            from gui.pages.utils.train_model import train_model
            try:
                train_model(config, STATE_MANAGER)
                self._log_signal.emit("Training complete.")
            except Exception as e:
                import traceback
                self._log_signal.emit(f"[ERROR] {e}")
                self._log_signal.emit(traceback.format_exc())
            finally:
                self._finish_signal.emit()

        self._train_thread = threading.Thread(target=run, daemon=True)
        self._train_thread.start()
        self._timer.start()

    def _stop_training(self):
        STATE_MANAGER.set_stop_flag()
        self._append_log("Stop requested — will halt after current epoch.")
        self.stop_btn.setEnabled(False)

    def _poll_progress(self):
        progress = STATE_MANAGER.load_progress()
        pct   = progress.get("progress", 0)
        epoch = progress.get("current_epoch", 0)
        total = self.epochs.value()

        self.progress_bar.setValue(pct)
        self.epoch_lbl.setText(f"Epoch: {epoch} / {total}")

        history = STATE_MANAGER.load_loss_history()
        if history:
            last = history[-1]["loss"]
            self.loss_lbl.setText(f"Loss: {last:.6f}")
            self.loss_chart.update(history, total)

        if self._train_thread and not self._train_thread.is_alive():
            self._timer.stop()

    def _on_finish(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._timer.stop()
        self._refresh_history()

    def _append_log(self, text):
        self.log_box.append(text)
        self.log_box.verticalScrollBar().setValue(
            self.log_box.verticalScrollBar().maximum())
