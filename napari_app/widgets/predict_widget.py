import threading
from pathlib import Path

import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QDoubleSpinBox, QSpinBox,
    QFileDialog, QScrollArea, QProgressBar, QTextEdit,
    QFrame, QGroupBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from gui.pages.utils.predict_state_manager import PredictionStateManager
from project_root import STORAGE_DIR

LORA_DIR = STORAGE_DIR / "loras"
BUILTIN_LORA_DIR = Path(__file__).parents[2] / "checkpoints"
TEST_IMAGE_DIR = STORAGE_DIR / "test_images"

LORA_META = {
    "cellpose_specialized_12.pth":      ("General cells",         0.917),
    "cellseg_blood_117.pth":            ("Blood cells",           0.941),
    "deepbacs_rod_brightfield_9.pth":   ("E. coli brightfield",  0.860),
    "deepbacs_rod_fluorescence_75.pth": ("B. subtilis fluor.",    0.821),
    "dsb2018_stardist_435.pth":         ("Cell nuclei",           0.872),
}

STATE_MANAGER = PredictionStateManager(str(STORAGE_DIR))
_DLG = QFileDialog.Option.DontUseNativeDialog


def _pick_file(parent, line_edit, caption, ext="All (*)"):
    start = str(Path(line_edit.text()).parent) if line_edit.text() else str(Path.home())
    path, _ = QFileDialog.getOpenFileName(parent, caption, start, ext, options=_DLG)
    if path:
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


class PredictWidget(QWidget):
    _log_signal    = pyqtSignal(str)
    _done_signal   = pyqtSignal(object, object)   # image_arr, label_mask
    _finish_signal = pyqtSignal()

    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self._pred_thread = None
        self._last_label_mask = None
        self._last_image_path = None

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

        # ── LoRA checkpoint ──────────────────────────────────────────────────
        L.addWidget(_section("LoRA checkpoint", "#A5D6A7"))
        self.lora_combo = QComboBox()
        self._lora_paths = {}
        self._populate_lora_combo()
        L.addWidget(self.lora_combo)

        row_custom = QHBoxLayout()
        self.lora_custom = QLineEdit()
        self.lora_custom.setPlaceholderText("Custom .pth — leave blank to use above")
        row_custom.addWidget(self.lora_custom)
        b = QPushButton("…"); b.setFixedWidth(30)
        b.clicked.connect(lambda: _pick_file(self, self.lora_custom, "Select LoRA checkpoint", "PyTorch (*.pth)"))
        row_custom.addWidget(b)
        L.addLayout(row_custom)

        L.addWidget(_divider())

        # ── Input image ──────────────────────────────────────────────────────
        L.addWidget(_section("Input image", "#A5D6A7"))
        row_img = QHBoxLayout()
        self.image_path = QLineEdit()
        default_img = _find_test_image()
        if default_img:
            self.image_path.setText(str(default_img))
        row_img.addWidget(self.image_path)
        b2 = QPushButton("…"); b2.setFixedWidth(30)
        b2.clicked.connect(lambda: _pick_file(self, self.image_path, "Select image",
            "Images (*.png *.tif *.tiff *.jpg *.bmp *.npy)"))
        row_img.addWidget(b2)
        L.addLayout(row_img)

        # Ground truth overlay
        row_gt = QHBoxLayout()
        self.gt_path = QLineEdit()
        self.gt_path.setPlaceholderText("Ground truth mask (optional)")
        row_gt.addWidget(self.gt_path)
        b_gt = QPushButton("…"); b_gt.setFixedWidth(30)
        b_gt.clicked.connect(lambda: _pick_file(self, self.gt_path, "Select ground truth mask",
            "Images (*.png *.tif *.tiff *.npy)"))
        row_gt.addWidget(b_gt)
        L.addLayout(row_gt)

        btn_gt = QPushButton("Show ground truth layer")
        btn_gt.setStyleSheet("background:#2a3a4a; color:#90CAF9; border-radius:3px;")
        btn_gt.clicked.connect(self._show_ground_truth)
        L.addWidget(btn_gt)

        L.addWidget(_divider())

        # ── Model ────────────────────────────────────────────────────────────
        L.addWidget(_section("Model", "#A5D6A7"))

        row_vit = QHBoxLayout()
        row_vit.addWidget(QLabel("SAM type"))
        self.vit_name = QComboBox()
        self.vit_name.addItems(["vit_h", "vit_l", "vit_b"])
        self.vit_name.currentTextChanged.connect(self._on_vit_changed)
        row_vit.addWidget(self.vit_name)
        L.addLayout(row_vit)

        row_sam = QHBoxLayout()
        row_sam.addWidget(QLabel("SAM backbone"))
        self.sam_path = QLineEdit()
        self.sam_path.setPlaceholderText("auto")
        row_sam.addWidget(self.sam_path)
        b3 = QPushButton("…"); b3.setFixedWidth(30)
        b3.clicked.connect(lambda: _pick_file(self, self.sam_path, "Select SAM backbone", "PyTorch (*.pth)"))
        row_sam.addWidget(b3)
        L.addLayout(row_sam)
        self._on_vit_changed("vit_h")

        row_rank = QHBoxLayout()
        row_rank.addWidget(QLabel("LoRA rank"))
        self.lora_rank = QSpinBox()
        self.lora_rank.setRange(1, 64)
        self.lora_rank.setValue(4)
        row_rank.addWidget(self.lora_rank)
        L.addLayout(row_rank)

        row_dev = QHBoxLayout()
        row_dev.addWidget(QLabel("Device"))
        self.device = QComboBox()
        self._populate_devices()
        row_dev.addWidget(self.device)
        L.addLayout(row_dev)

        L.addWidget(_divider())

        # ── Inference parameters ─────────────────────────────────────────────
        L.addWidget(_section("Inference parameters", "#A5D6A7"))

        row_rs = QHBoxLayout()
        row_rs.addWidget(QLabel("Resize size"))
        self.resize_size = QComboBox()
        for v in ["256", "512", "768", "1024"]:
            self.resize_size.addItem(v)
        self.resize_size.setCurrentText("512")
        self.resize_size.setToolTip(
            "Resolution for SAM inference. Higher = better accuracy but slower and more memory.")
        row_rs.addWidget(self.resize_size)
        L.addLayout(row_rs)

        params = [
            ("Points/side",    "points_per_side",         4,   128,  32,  0, 4),
            ("IoU threshold",  "pred_iou_thresh",          0.0, 1.0, 0.8,  2, 0.05),
            ("Stability score","stability_score_thresh",   0.0, 1.0, 0.6,  2, 0.05),
            ("Box NMS thresh", "box_nms_thresh",           0.0, 1.0, 0.05, 3, 0.01),
            ("Min mask area",  "min_mask_area",            0,   10000, 20, 0, 10),
        ]
        for label, attr, lo, hi, val, dec, step in params:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            if dec == 0:
                w = QSpinBox()
                w.setRange(int(lo), int(hi))
                w.setValue(int(val))
                w.setSingleStep(int(step))
            else:
                w = QDoubleSpinBox()
                w.setDecimals(dec)
                w.setRange(lo, hi)
                w.setValue(val)
                w.setSingleStep(step)
            setattr(self, attr, w)
            row.addWidget(w)
            L.addLayout(row)

        L.addWidget(_divider())

        # ── Run ──────────────────────────────────────────────────────────────
        self.run_btn = QPushButton("▶  Run Prediction")
        self.run_btn.setFixedHeight(38)
        self.run_btn.setStyleSheet(
            "background:#1B5E20; color:white; font-weight:bold; border-radius:5px; font-size:13px;")
        self.run_btn.clicked.connect(self._run_prediction)
        L.addWidget(self.run_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        L.addWidget(self.progress_bar)

        # ── Stats ────────────────────────────────────────────────────────────
        self.stats_box = QGroupBox("Result")
        self.stats_box.setVisible(False)
        stats_layout = QVBoxLayout()
        self.cell_count_lbl  = QLabel("Cells found: —")
        self.avg_area_lbl    = QLabel("Avg area: —")
        self.coverage_lbl    = QLabel("Coverage: —")
        for lbl in (self.cell_count_lbl, self.avg_area_lbl, self.coverage_lbl):
            lbl.setStyleSheet("color: #E0E0E0; font-size: 12px;")
            stats_layout.addWidget(lbl)

        self.save_mask_btn = QPushButton("💾  Save masks as PNG")
        self.save_mask_btn.setStyleSheet("background:#1a3a5a; color:white; border-radius:3px;")
        self.save_mask_btn.clicked.connect(self._save_masks)
        stats_layout.addWidget(self.save_mask_btn)

        self.stats_box.setLayout(stats_layout)
        L.addWidget(self.stats_box)

        # ── Log ──────────────────────────────────────────────────────────────
        L.addWidget(_section("Log", "#A5D6A7"))
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(110)
        self.log_box.setStyleSheet(
            "background:#1A2E1A; color:#A0C0A0; font-family:Menlo,Monaco,Courier; font-size:11px;")
        L.addWidget(self.log_box)

        L.addStretch()
        inner.setLayout(L)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self.setLayout(outer)
        self.setMinimumWidth(320)

        self._log_signal.connect(self._append_log)
        self._done_signal.connect(self._show_results)
        self._finish_signal.connect(self._on_done)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _populate_lora_combo(self):
        self.lora_combo.clear()
        self._lora_paths = {}
        for f in sorted(BUILTIN_LORA_DIR.glob("*.pth")):
            desc, mAP = LORA_META.get(f.name, ("Custom", 0.0))
            label = f"{desc}  ·  mAP {mAP:.3f}  [{f.name}]" if mAP else f.name
            self.lora_combo.addItem(label)
            self._lora_paths[label] = str(f)
        for f in sorted(LORA_DIR.glob("*.pth")):
            if f.name not in LORA_META:
                label = f"[trained] {f.name}"
                self.lora_combo.addItem(label)
                self._lora_paths[label] = str(f)

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
        cand = STORAGE_DIR / "sam_backbone" / names.get(vit, "")
        if cand.exists():
            self.sam_path.setText(str(cand))
        else:
            self.sam_path.clear()
            self.sam_path.setPlaceholderText(f"Not found: {cand.name}")

    def _resolve_lora_path(self):
        custom = self.lora_custom.text().strip()
        if custom:
            return custom
        return self._lora_paths.get(self.lora_combo.currentText(), "")

    def _resolve_sam_path(self):
        p = self.sam_path.text().strip()
        if p and Path(p).exists():
            return p
        vit = self.vit_name.currentText()
        names = {"vit_h": "sam_vit_h_4b8939.pth",
                 "vit_l": "sam_vit_l_0b3195.pth",
                 "vit_b": "sam_vit_b_01ec64.pth"}
        cand = STORAGE_DIR / "sam_backbone" / names[vit]
        if cand.exists():
            return str(cand)
        raise ValueError(f"SAM backbone not found. Place {names[vit]} in {STORAGE_DIR/'sam_backbone'}/")

    def _build_config(self):
        lora_path  = self._resolve_lora_path()
        image_path = self.image_path.text().strip()
        sam_path   = self._resolve_sam_path()

        if not lora_path or not Path(lora_path).exists():
            raise ValueError(f"LoRA checkpoint not found: {lora_path}")
        if not image_path or not Path(image_path).exists():
            raise ValueError(f"Image not found: {image_path}")

        rs = int(self.resize_size.currentText())
        return {
            "vit_name": self.vit_name.currentText(),
            "model_path": sam_path,
            "result_pth_path": lora_path,
            "image_path": image_path,
            "image_encoder_lora_rank": self.lora_rank.value(),
            "mask_decoder_lora_rank":  self.lora_rank.value(),
            "freeze_image_encoder":             True,
            "freeze_prompt_encoder":            True,
            "freeze_mask_decoder_transformer":  True,
            "freeze_upscaling_cnn":             True,
            "freeze_output_hypernetworks_mlps": True,
            "freeze_mask_decoder_mask_tokens":  True,
            "freeze_mask_decoder_iou":          True,
            "lora_dropout": 0.1,
            "sam_image_size": rs,
            "resize_size": [rs, rs],
            "points_per_side":  self.points_per_side.value(),
            "points_per_batch": 64,
            "pred_iou_thresh":         self.pred_iou_thresh.value(),
            "stability_score_thresh":  self.stability_score_thresh.value(),
            "stability_score_offset":  0.8,
            "box_nms_thresh":          self.box_nms_thresh.value(),
            "crop_nms_thresh":         0.05,
            "crop_n_layers":           1,
            "crop_n_points_downscale_factor": 1,
            "min_mask_region_area":    self.min_mask_area.value(),
            "max_mask_region_area_ratio": 0.1,
            "selected_device": self.device.currentText(),
            "deterministic": True,
            "seed": 0,
            "allow_tf32_on_cudnn":  True,
            "allow_tf32_on_matmul": True,
        }

    # ── Actions ──────────────────────────────────────────────────────────────

    def _run_prediction(self):
        try:
            config = self._build_config()
        except ValueError as e:
            self._append_log(f"[ERROR] {e}")
            return

        self.run_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.stats_box.setVisible(False)
        self._append_log(f"Running on {Path(config['image_path']).name} …")

        def run():
            try:
                image_arr, label_mask = _predict(config)
                self._done_signal.emit(image_arr, label_mask)
                n = int(label_mask.max()) if label_mask is not None else 0
                self._log_signal.emit(f"Done — {n} cells found.")
            except Exception as e:
                import traceback
                self._log_signal.emit(f"[ERROR] {e}")
                self._log_signal.emit(traceback.format_exc())
            finally:
                self._finish_signal.emit()

        self._pred_thread = threading.Thread(target=run, daemon=True)
        self._pred_thread.start()

    def _on_done(self):
        self.run_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._populate_lora_combo()

    def _show_results(self, image_arr, label_mask):
        name = Path(self.image_path.text()).stem
        self._last_label_mask  = label_mask
        self._last_image_path  = self.image_path.text()

        for layer in list(self.viewer.layers):
            if layer.name.startswith(name) and "_gt" not in layer.name:
                self.viewer.layers.remove(layer)

        self.viewer.add_image(image_arr, name=f"{name}_image")

        if label_mask is not None and label_mask.max() > 0:
            lyr = self.viewer.add_labels(
                label_mask.astype(np.int32), name=f"{name}_masks", opacity=0.7)
            lyr.contour = 2
            self._update_stats(label_mask, image_arr.shape[:2])
        self.viewer.reset_view()

    def _update_stats(self, label_mask, shape):
        n_cells = int(label_mask.max())
        total_px = shape[0] * shape[1]
        cell_px  = int((label_mask > 0).sum())
        areas    = [int((label_mask == i).sum()) for i in range(1, n_cells + 1)]
        avg_area = int(np.mean(areas)) if areas else 0
        coverage = cell_px / total_px * 100

        self.cell_count_lbl.setText(f"Cells found:  {n_cells}")
        self.avg_area_lbl.setText(f"Avg area:      {avg_area} px²")
        self.coverage_lbl.setText(f"Coverage:     {coverage:.1f}%")
        self.stats_box.setVisible(True)

    def _show_ground_truth(self):
        gt_path = self.gt_path.text().strip()
        if not gt_path or not Path(gt_path).exists():
            self._append_log("[ERROR] Ground truth path not set or not found.")
            return
        try:
            import cv2
            gt = cv2.imread(gt_path, cv2.IMREAD_UNCHANGED)
            if gt is None:
                import numpy as _np
                gt = _np.load(gt_path)
            name = Path(self.image_path.text()).stem
            layer_name = f"{name}_gt"
            for lyr in list(self.viewer.layers):
                if lyr.name == layer_name:
                    self.viewer.layers.remove(lyr)
            gt_lyr = self.viewer.add_labels(
                gt.astype(np.int32), name=layer_name, opacity=0.5)
            gt_lyr.contour = 2
            n_gt = int(gt.max())
            self._append_log(f"Ground truth loaded — {n_gt} cells.")
        except Exception as e:
            self._append_log(f"[ERROR] loading GT: {e}")

    def _save_masks(self):
        if self._last_label_mask is None:
            return
        stem = Path(self._last_image_path).stem if self._last_image_path else "mask"
        default = str(STORAGE_DIR / "predict_masks" / f"{stem}_mask.png")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save mask", default, "PNG (*.png);;TIFF (*.tif)", options=_DLG)
        if not path:
            return
        try:
            import cv2
            mask = self._last_label_mask
            if mask.max() <= 65535:
                cv2.imwrite(path, mask.astype(np.uint16))
            else:
                cv2.imwrite(path, mask.astype(np.int32))
            self._append_log(f"Saved: {Path(path).name}")
        except Exception as e:
            self._append_log(f"[ERROR] saving: {e}")

    def _append_log(self, text):
        self.log_box.append(text)
        self.log_box.verticalScrollBar().setValue(
            self.log_box.verticalScrollBar().maximum())


# ── Prediction logic (background thread) ─────────────────────────────────────

def _predict(config):
    import os
    dev = config.get("selected_device", "cpu")
    if dev in ("cpu", "mps"):
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    if dev == "mps":
        os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
    elif "PYTORCH_ENABLE_MPS_FALLBACK" in os.environ:
        del os.environ["PYTORCH_ENABLE_MPS_FALLBACK"]
    if dev not in ("cpu", "mps"):
        os.environ["CUDA_VISIBLE_DEVICES"] = dev

    import cv2
    from data.utils import resize_image
    from predict import predict_images

    image_path = config["image_path"]
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")

    if img.ndim == 2:
        img_rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    elif img.shape[2] == 4:
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
    else:
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    orig_h, orig_w = img_rgb.shape[:2]
    img_resized = resize_image(img_rgb, config["resize_size"])
    label_small = predict_images(config, [img_resized])[0]

    # Scale mask back to original image size
    if label_small.shape != (orig_h, orig_w):
        label_mask = cv2.resize(
            label_small.astype(np.float32),
            (orig_w, orig_h),
            interpolation=cv2.INTER_NEAREST,
        ).astype(label_small.dtype)
    else:
        label_mask = label_small

    return img_rgb, label_mask


def _find_test_image():
    for ext in ("*.png", "*.tif", "*.tiff", "*.jpg"):
        hits = list(TEST_IMAGE_DIR.glob(ext))
        if hits:
            return hits[0]
    return None
