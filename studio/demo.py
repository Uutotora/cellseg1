"""CellSeg1 Studio — static demo content for the design skeleton.

Hard-coded stand-in data mirroring the north-star mockup, so every screen
renders a believable, consistent picture with **no logic** behind it. When a
tab is wired for real (see ``docstudio/BACKLOG.md``), its screen swaps this
module for live data from the (re-introduced) data layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DemoProject:
    name: str
    description: str
    engine_key: str        # cellseg1 | cellpose | sam2
    engine_label: str
    n_images: int
    n_cells: str           # pre-formatted (e.g. "31.4k")
    progress: int          # 0..100
    f1: Optional[str]      # None → "—"
    tags: list[str]
    seed: int
    favorite: bool = False


PROJECTS: list[DemoProject] = [
    DemoProject("Fluorescence Nuclei — DAPI",
                "384-well DAPI screen, one-shot LoRA fine-tuned on a single field.",
                "cellseg1", "CellSeg1 · LoRA", 128, "31.4k", 96, "0.94",
                ["fluorescence", "nuclei"], 7, favorite=True),
    DemoProject("H&E Tissue Cohort",
                "Whole-slide H&E biopsies, tiled at native resolution across 12 patients.",
                "cellpose", "Cellpose-SAM", 342, "188k", 41, None,
                ["histology", "H&E"], 22),
    DemoProject("Live-cell Mitosis",
                "Confocal z-stacks tracked across time with SAM 2 propagation.",
                "sam2", "SAM 2", 24, "9.7k", 70, "0.90",
                ["time-lapse", "3D"], 41, favorite=True),
    DemoProject("BBBC039 Nuclei Benchmark",
                "Public benchmark for regression-testing engine accuracy.",
                "cellseg1", "CellSeg1 · LoRA", 200, "52k", 100, "0.91",
                ["benchmark"], 63),
    DemoProject("Organoid Membranes",
                "Brightfield organoid sections, membrane-channel segmentation.",
                "cellpose", "Cellpose-SAM", 88, "14.2k", 33, None,
                ["membrane", "brightfield"], 88),
    DemoProject("Phantom QC",
                "Synthetic phantoms for daily pipeline quality control.",
                "cellseg1", "CellSeg1 · LoRA", 12, "1.1k", 100, "0.98",
                ["QC", "synthetic"], 101),
]

RECENT_WHEN = ["2 hours ago", "yesterday", "3 days ago", "last week"]

# Workspace image list (filename, status): ok=annotated, pred=predicted, none=new
TASKS = [
    ("img_001.tif", "ok"), ("img_002.tif", "pred"), ("img_003.tif", "pred"),
    ("img_004.tif", "none"), ("img_005.tif", "ok"), ("img_006.tif", "pred"),
    ("img_007.tif", "none"), ("img_008.tif", "pred"), ("img_009.tif", "ok"),
    ("img_010.tif", "none"), ("img_011.tif", "pred"), ("img_012.tif", "pred"),
]
STATUS_LABEL = {"ok": "annotated", "pred": "predicted", "none": "new"}

# Layers panel (name, type, count, visible)
LAYERS = [
    ("Segmentation", "labels", "247", True),
    ("Ground truth", "labels", "240", False),
    ("Corrections", "shapes", "3", True),
    ("Prompts", "points", "5", True),
    ("DAPI", "image", "ch1", True),
    ("Membrane", "image", "ch2", False),
]
LAYER_TYPE_KIND = {"labels": "signal", "shapes": "primary", "points": "warning", "image": "muted"}

# Label palette (bigger set) — the "more colours" the user asked for
LABEL_COLORS = [
    "#b23b1e", "#4d8fff", "#2bd4c0", "#6fae53", "#e0982f", "#ee6a52", "#a878cf",
    "#e37bd3", "#539eee", "#78b757", "#faba4c", "#ff7557", "#9f5694", "#22625d",
    "#57b7ab", "#ffa663", "#c98500", "#e66767",
]

# Results
RESULTS = {
    "cells": 247, "median_d": "25.5", "mean_area": "508", "coverage": "9.3",
    "f1": "0.94", "precision": "0.95", "recall": "0.93", "ap50": "0.88",
}
COLOR_BY = ["Instance ID (default)", "Area (heatmap)", "Diameter (heatmap)",
            "Solidity (heatmap)", "Mean intensity (heatmap)"]

# Models & Train
MODELS = [
    ("nuclei-dapi-r8", "ViT-H · rank 8 · 128 images · fluorescence", "0.94"),
    ("tissue-he-r16", "ViT-H · rank 16 · 342 images · H&E", "0.89"),
    ("phantom-qc-r8", "ViT-L · rank 8 · 12 images · synthetic", "0.98"),
]
TRAIN_RUNS = [
    ("nuclei-dapi-r8", "epoch 74/100 · loss 0.19", "run"),
    ("tissue-he-r16", "done · 8m 12s", "done"),
    ("phantom-qc-r8", "done · 3m 41s", "done"),
]

# Dashboard
LOSS_CURVE = [0.92, 0.71, 0.55, 0.44, 0.37, 0.31, 0.27, 0.24, 0.22, 0.205, 0.195, 0.188]
F1_BARS = [0.71, 0.80, 0.86, 0.90, 0.91, 0.94]
DASH_RUNS = [
    ("nuclei-dapi-r8", "CellSeg1 · LoRA", "0.94", "31.4k", "6m 02s", "2h ago", True),
    ("tissue-he-r16", "CellSeg1 · LoRA", "0.89", "188k", "8m 12s", "yesterday", True),
    ("bbbc039-bench", "CellSeg1 · LoRA", "0.91", "52k", "5m 44s", "3d ago", True),
    ("organoid-cp", "Cellpose-SAM", "0.83", "14.2k", "2m 08s", "last week", False),
    ("mitosis-sam2", "SAM 2", "0.90", "9.7k", "11m 30s", "last week", True),
]

# Assistant chat (role, text, [apply chips])
CHAT = [
    ("user", "Some nuclei in the centre are merged into one mask — how do I split them?", []),
    ("bot", "Three touching nuclei were merged into one instance. For dense DAPI "
            "fields I'd tighten the split: raise IoU 0.80 → 0.86, raise Stability "
            "0.60 → 0.66, keep Min area low so small splits survive.",
     ["Apply IoU 0.86", "Apply Stability 0.66", "Re-run"]),
    ("bot", "Alternatively switch the engine to SAM 2 and drop two point prompts — "
            "it separates touching instances cleanly here.", []),
]

# Logs console (time, level, message)
LOGS = [
    ("10:42:01", "info", "Loading SAM backbone ViT-H (sam_vit_h_4b8939.pth)…"),
    ("10:42:03", "ok", "LoRA adapter nuclei-dapi-r8 attached · rank 8 · device mps"),
    ("10:42:03", "info", "Encoding image embedding 512×512 (cache hit)"),
    ("10:42:05", "info", "AMG · 32 points/side · pred_iou 0.80 · stability 0.60"),
    ("10:42:06", "ok", "261 raw masks → box-NMS 0.05 → 247 instances"),
    ("10:42:06", "warn", "3 masks below min_area 20px discarded"),
    ("10:42:06", "ok", "Morphometry done · F1 0.94 vs GT · 3.2s"),
]

# Command palette entries (section, icon, text, hint)
PALETTE = [
    ("Actions", "run", "Run segmentation", "⏎"),
    ("Actions", "models", "Switch engine → SAM 2", "z-stack"),
    ("Actions", "chart", "Apply preset → Accurate", ""),
    ("Actions", "models", "Train LoRA from this annotation", ""),
    ("Export", "csv", "Export masks → COCO / PNG / label TIFF", ""),
    ("Export", "csv", "Export measurements → CSV", ""),
]
