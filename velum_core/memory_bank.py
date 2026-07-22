"""Velum — Prototype Memory Bank (training-free few-shot retrieval core).

The buildable, GPU-free core of the "CellSeg1 v2" Memory-Bank + auto-prompt
idea: instead of dissolving a support image into LoRA weights, store the
*feature prototype* of an annotated cell and, at inference, retrieve the most
similar prototype and turn its similarity map into SAM prompts. This is the
PerSAM / Matcher family of **training-free** SAM personalisation — no network
is trained here; it is cosine-similarity retrieval over the ViT embeddings the
app *already* computes and caches (``velum_core.inference_cache`` intercepts
``SamPredictor.set_image`` and keeps ``predictor.features``, a ``(1, C, H, W)``
dense image embedding — exactly the "64×64×256 feature tensor" a prototype is
pooled from).

**What is real and unit-tested here** (pure NumPy, no torch/GPU/model):
  - masked prototype pooling: a feature map + an instance/class mask → one
    L2-normalised prototype vector (``masked_prototype``),
  - cosine-similarity retrieval over a persistent bank (``MemoryBank``),
  - per-location similarity maps (``similarity_map``) and deriving positive /
    negative SAM point prompts from them (``points_from_similarity``) — the
    training-free "dynamic prompt generator",
  - a local, inspectable, JSON+``.npz`` store (fits the product's local-first
    stance — prototypes are your data, on your machine).

**What is NOT done/validated here** (needs the real model + a GPU + a
benchmark, none available in this sandbox): calling the live SAM encoder to
produce a query feature map, wiring the derived prompts back into a real
predict run, and measuring an actual segmentation-quality uplift. The
integration seam is ``prototype_from_predictor_features`` +
``points_from_similarity`` (both pure); the caller supplies the real
``predictor.features`` array. The *learned* prompt generator and the CNN×ViT
multi-scale fusion from the same v2 sketch are deliberately out of scope — they
require training and cannot be shipped as verified code from here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

_EPS = 1e-8


# ── vector math (pure) ───────────────────────────────────────────────────────
def l2_normalize(vec: np.ndarray, axis: int = -1) -> np.ndarray:
    """Unit-normalise along ``axis``; a zero vector stays zero (no div-by-0)."""
    vec = np.asarray(vec, dtype=np.float32)
    norm = np.linalg.norm(vec, axis=axis, keepdims=True)
    return vec / np.maximum(norm, _EPS)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two 1-D vectors, in [-1, 1]."""
    a = np.asarray(a, dtype=np.float32).ravel()
    b = np.asarray(b, dtype=np.float32).ravel()
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom < _EPS:
        return 0.0
    return float(np.dot(a, b) / denom)


def _to_hwc(feature_map: np.ndarray) -> np.ndarray:
    """Normalise a feature map to ``(H, W, C)``.

    Accepts ``(H, W, C)`` as-is, ``(C, H, W)`` (torch/SAM layout), or a
    ``(1, C, H, W)`` batch of one (``SamPredictor.features``). Heuristic for the
    3-D ambiguous case: SAM embeddings are far deeper (C≈256) than they are
    wide, so the axis that is largest is taken to be C when it is axis 0.
    """
    f = np.asarray(feature_map, dtype=np.float32)
    if f.ndim == 4:
        if f.shape[0] != 1:
            raise ValueError(f"Expected a batch of 1, got shape {f.shape}")
        f = f[0]
    if f.ndim != 3:
        raise ValueError(f"Feature map must be 3-D (or 1×3-D), got {f.shape}")
    # (C, H, W) → (H, W, C) when the first axis looks like the channel axis
    # (deeper than the spatial dims, the SAM/torch convention).
    if f.shape[0] >= f.shape[1] and f.shape[0] >= f.shape[2]:
        f = np.transpose(f, (1, 2, 0))
    return f


def masked_prototype(feature_map: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Mean-pool the feature vectors under ``mask`` into one L2-normalised
    prototype vector.

    ``feature_map`` is any layout accepted by :func:`_to_hwc`; ``mask`` is a
    2-D array (any nonzero = foreground) that is nearest-neighbour resized to
    the feature-map resolution if it doesn't already match (feature maps are
    ~16× smaller than the image, so a full-res mask is the normal input).
    Raises ``ValueError`` if the mask selects nothing.
    """
    f = _to_hwc(feature_map)
    h, w, _ = f.shape
    m = np.asarray(mask)
    if m.shape != (h, w):
        m = _resize_nearest(m, (h, w))
    sel = m.astype(bool)
    if not sel.any():
        raise ValueError("mask is empty at feature resolution — nothing to pool")
    vecs = f[sel]                      # (N, C)
    proto = vecs.mean(axis=0)          # (C,)
    return l2_normalize(proto)


def similarity_map(feature_map: np.ndarray, prototype: np.ndarray) -> np.ndarray:
    """Cosine similarity of every spatial location to ``prototype`` → an
    ``(H, W)`` heatmap in [-1, 1]. This is the location prior a prompt is read
    from."""
    f = _to_hwc(feature_map)
    h, w, c = f.shape
    flat = f.reshape(-1, c)
    flat = l2_normalize(flat, axis=1)
    proto = l2_normalize(np.asarray(prototype, dtype=np.float32).ravel())
    sims = flat @ proto                # (H*W,)
    return sims.reshape(h, w)


@dataclass
class PromptPoints:
    """SAM-ready point prompts derived from a similarity map. ``points`` is
    ``(N, 2)`` in ``(x, y)`` pixel coordinates of the *original image* (scaled
    up from feature resolution); ``labels`` is ``(N,)`` with 1=foreground,
    0=background — exactly SAM's ``point_coords`` / ``point_labels`` contract."""

    points: np.ndarray
    labels: np.ndarray

    def __len__(self) -> int:
        return int(self.points.shape[0])


def points_from_similarity(sim_map: np.ndarray, *, image_shape: tuple[int, int],
                           n_positive: int = 1, n_negative: int = 0,
                           pos_thresh: float = 0.0) -> PromptPoints:
    """Turn a similarity map into positive/negative SAM point prompts.

    The ``n_positive`` highest-similarity locations become foreground points,
    the ``n_negative`` lowest become background points (PerSAM's positive-
    negative location prior). Coordinates are scaled from the feature-map grid
    to ``image_shape`` (H, W) so they line up with the full-resolution image
    SAM is prompted on. Positive points below ``pos_thresh`` are dropped (a
    query with no matching prototype yields no positive prompt rather than a
    spurious one).
    """
    sim = np.asarray(sim_map, dtype=np.float32)
    fh, fw = sim.shape
    ih, iw = image_shape
    sy, sx = ih / fh, iw / fw

    def _coords(indices):
        pts = []
        for idx in indices:
            r, c = divmod(int(idx), fw)
            # centre of the feature cell, mapped to image pixels
            pts.append(((c + 0.5) * sx, (r + 0.5) * sy))
        return pts

    flat = sim.ravel()
    order = np.argsort(flat)           # ascending
    pos_idx = [i for i in order[::-1][:n_positive] if flat[i] >= pos_thresh]
    neg_idx = list(order[:n_negative]) if n_negative > 0 else []

    coords = _coords(pos_idx) + _coords(neg_idx)
    labels = [1] * len(pos_idx) + [0] * len(neg_idx)
    if not coords:
        return PromptPoints(np.empty((0, 2), np.float32), np.empty((0,), np.int32))
    return PromptPoints(np.asarray(coords, np.float32), np.asarray(labels, np.int32))


def prototype_from_predictor_features(features, mask: np.ndarray) -> np.ndarray:
    """Integration seam: pool a prototype from a live ``SamPredictor.features``
    tensor (``inference_cache`` keeps one per encoded image). Accepts a torch
    tensor or ndarray; converts to CPU float32 NumPy without importing torch
    (uses the tensor's own ``.detach().cpu().numpy()`` if present)."""
    arr = _as_numpy(features)
    return masked_prototype(arr, mask)


# ── the bank ─────────────────────────────────────────────────────────────────
@dataclass
class Prototype:
    """One stored feature prototype — the "experience" of one annotated cell
    type. The vector is what's matched; everything else is provenance/curation
    (which lab, microscope, magnification, etc., per the v2 sketch)."""

    id: str
    label: str
    vector: np.ndarray
    n_samples: int = 1
    tags: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    created_at: str = ""

    def to_meta(self) -> dict:
        return {"id": self.id, "label": self.label, "n_samples": self.n_samples,
                "tags": list(self.tags), "meta": dict(self.meta),
                "created_at": self.created_at, "dim": int(self.vector.shape[0])}


@dataclass
class Retrieval:
    prototype: Prototype
    score: float


class MemoryBank:
    """A persistent, inspectable set of feature prototypes with cosine-
    similarity retrieval. Nothing is trained; adding a prototype is O(1) and
    forgets nothing (unlike LoRA weight updates)."""

    def __init__(self) -> None:
        self._protos: list[Prototype] = []
        self._counter = 0

    # -- add / remove / query --
    def add(self, vector: np.ndarray, label: str, *, tags: Optional[list[str]] = None,
            meta: Optional[dict] = None, n_samples: int = 1) -> Prototype:
        self._counter += 1
        proto = Prototype(
            id=f"proto-{self._counter:04d}", label=label,
            vector=l2_normalize(np.asarray(vector, dtype=np.float32).ravel()),
            n_samples=n_samples, tags=list(tags or []), meta=dict(meta or {}),
            created_at=datetime.now().isoformat(timespec="seconds"))
        self._protos.append(proto)
        return proto

    def add_from_features(self, feature_map: np.ndarray, mask: np.ndarray,
                          label: str, **kw) -> Prototype:
        """Convenience: pool a prototype from a feature map + mask and store it."""
        return self.add(masked_prototype(feature_map, mask), label, **kw)

    def remove(self, proto_id: str) -> bool:
        n = len(self._protos)
        self._protos = [p for p in self._protos if p.id != proto_id]
        return len(self._protos) != n

    def __len__(self) -> int:
        return len(self._protos)

    def prototypes(self) -> list[Prototype]:
        return list(self._protos)

    def labels(self) -> list[str]:
        seen: list[str] = []
        for p in self._protos:
            if p.label not in seen:
                seen.append(p.label)
        return seen

    def retrieve(self, query_vector: np.ndarray, *, k: int = 1,
                 label: Optional[str] = None) -> list[Retrieval]:
        """Top-``k`` prototypes most similar to ``query_vector`` (optionally
        restricted to one ``label``), highest score first."""
        q = l2_normalize(np.asarray(query_vector, dtype=np.float32).ravel())
        pool = [p for p in self._protos if label is None or p.label == label]
        scored = [Retrieval(p, cosine_similarity(q, p.vector)) for p in pool]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:max(0, k)]

    def aggregate(self, label: str) -> Optional[Prototype]:
        """Mean-pool every prototype of ``label`` into a single class
        prototype (weighted by ``n_samples``) — the "one representative
        embedding per cell type" view. Returns a fresh, unstored Prototype."""
        group = [p for p in self._protos if p.label == label]
        if not group:
            return None
        weights = np.array([p.n_samples for p in group], dtype=np.float32)
        stack = np.stack([p.vector for p in group])          # (G, C)
        mean = (stack * weights[:, None]).sum(0) / weights.sum()
        return Prototype(id=f"agg-{label}", label=label, vector=l2_normalize(mean),
                         n_samples=int(weights.sum()), tags=["aggregate"],
                         created_at=datetime.now().isoformat(timespec="seconds"))

    # -- persistence (local, inspectable) --
    def save(self, directory: str | Path) -> Path:
        """Write vectors (``vectors.npz``) + provenance (``meta.json``) under
        ``directory``. Local and human-inspectable, matching the app's
        nothing-leaves-your-machine stance."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        if self._protos:
            np.savez(directory / "vectors.npz",
                     **{p.id: p.vector for p in self._protos})
        else:
            np.savez(directory / "vectors.npz")
        (directory / "meta.json").write_text(json.dumps({
            "counter": self._counter,
            "prototypes": [p.to_meta() for p in self._protos],
        }, indent=2), encoding="utf-8")
        return directory

    @classmethod
    def load(cls, directory: str | Path) -> "MemoryBank":
        directory = Path(directory)
        bank = cls()
        meta_path = directory / "meta.json"
        if not meta_path.exists():
            return bank
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        vectors = {}
        vpath = directory / "vectors.npz"
        if vpath.exists():
            with np.load(vpath) as data:
                vectors = {k: data[k] for k in data.files}
        for pm in meta.get("prototypes", []):
            vec = vectors.get(pm["id"])
            if vec is None:
                continue
            bank._protos.append(Prototype(
                id=pm["id"], label=pm["label"],
                vector=l2_normalize(np.asarray(vec, dtype=np.float32).ravel()),
                n_samples=pm.get("n_samples", 1), tags=pm.get("tags", []),
                meta=pm.get("meta", {}), created_at=pm.get("created_at", "")))
        bank._counter = meta.get("counter", len(bank._protos))
        return bank


# ── small helpers ────────────────────────────────────────────────────────────
def _as_numpy(x) -> np.ndarray:
    """torch tensor or array-like → CPU float32 ndarray, without importing torch."""
    if hasattr(x, "detach"):
        x = x.detach()
    if hasattr(x, "cpu"):
        x = x.cpu()
    if hasattr(x, "numpy"):
        x = x.numpy()
    return np.asarray(x, dtype=np.float32)


def _resize_nearest(arr: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Nearest-neighbour resize of a 2-D array to ``shape`` (H, W) with plain
    index math — no cv2/scipy dependency, so this module stays import-light."""
    arr = np.asarray(arr)
    h0, w0 = arr.shape[:2]
    h1, w1 = shape
    rows = (np.arange(h1) * h0 / h1).astype(int).clip(0, h0 - 1)
    cols = (np.arange(w1) * w0 / w1).astype(int).clip(0, w0 - 1)
    return arr[rows][:, cols]
