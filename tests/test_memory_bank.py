"""Tests for velum_core/memory_bank.py — the training-free Prototype Memory
Bank + auto-prompt retrieval core. Pure NumPy (no torch/GPU/model), light CI
group. Exercises the vector math, masked pooling, similarity maps, prompt
derivation, the persistent bank, and save/load."""
import numpy as np
import pytest

from velum_core import memory_bank as mb
from velum_core.memory_bank import MemoryBank


# ── vector math ──────────────────────────────────────────────────────────────
def test_l2_normalize_unit_length_and_zero_safe():
    v = mb.l2_normalize(np.array([3.0, 4.0]))
    assert np.isclose(np.linalg.norm(v), 1.0)
    z = mb.l2_normalize(np.zeros(4))
    assert np.allclose(z, 0.0)  # no NaN/inf


def test_cosine_similarity_bounds():
    a = np.array([1.0, 0.0, 0.0])
    assert mb.cosine_similarity(a, a) == pytest.approx(1.0)
    assert mb.cosine_similarity(a, np.array([-1.0, 0.0, 0.0])) == pytest.approx(-1.0)
    assert mb.cosine_similarity(a, np.array([0.0, 1.0, 0.0])) == pytest.approx(0.0)
    assert mb.cosine_similarity(a, np.zeros(3)) == 0.0


# ── layout normalisation ─────────────────────────────────────────────────────
def test_to_hwc_accepts_all_layouts():
    hwc = np.zeros((4, 4, 16), np.float32)
    assert mb._to_hwc(hwc).shape == (4, 4, 16)
    chw = np.zeros((16, 4, 4), np.float32)          # SAM/torch layout
    assert mb._to_hwc(chw).shape == (4, 4, 16)
    batched = np.zeros((1, 16, 4, 4), np.float32)   # predictor.features
    assert mb._to_hwc(batched).shape == (4, 4, 16)


def test_to_hwc_rejects_bad_batch():
    with pytest.raises(ValueError):
        mb._to_hwc(np.zeros((2, 16, 4, 4)))


# ── masked pooling ───────────────────────────────────────────────────────────
def _feature_map_with_hot_region():
    """4×4×8 map: the top-left 2×2 block points one way, the rest another."""
    f = np.zeros((4, 4, 8), np.float32)
    hot = np.zeros(8); hot[0] = 1.0
    cold = np.zeros(8); cold[1] = 1.0
    f[:] = cold
    f[0:2, 0:2] = hot
    return f, hot


def test_masked_prototype_pools_region():
    f, hot = _feature_map_with_hot_region()
    mask = np.zeros((4, 4)); mask[0:2, 0:2] = 1
    proto = mb.masked_prototype(f, mask)
    assert mb.cosine_similarity(proto, hot) == pytest.approx(1.0)


def test_masked_prototype_resizes_full_res_mask():
    f, hot = _feature_map_with_hot_region()          # feature res 4×4
    mask = np.zeros((64, 64)); mask[0:32, 0:32] = 1  # full-res mask, 16× larger
    proto = mb.masked_prototype(f, mask)
    assert mb.cosine_similarity(proto, hot) == pytest.approx(1.0)


def test_masked_prototype_empty_mask_raises():
    f, _ = _feature_map_with_hot_region()
    with pytest.raises(ValueError):
        mb.masked_prototype(f, np.zeros((4, 4)))


# ── similarity map + prompt derivation ───────────────────────────────────────
def test_similarity_map_peaks_at_the_matching_region():
    f, hot = _feature_map_with_hot_region()
    sim = mb.similarity_map(f, hot)
    assert sim.shape == (4, 4)
    assert sim[0, 0] == pytest.approx(1.0)     # inside the hot block
    assert sim[3, 3] == pytest.approx(0.0)     # cold region, orthogonal


def test_points_from_similarity_positive_and_scaled():
    f, hot = _feature_map_with_hot_region()
    sim = mb.similarity_map(f, hot)            # 4×4 grid, peak in top-left
    pp = mb.points_from_similarity(sim, image_shape=(64, 64), n_positive=1)
    assert len(pp) == 1
    assert pp.labels[0] == 1
    x, y = pp.points[0]
    # top-left feature cell centre maps into the top-left quarter of a 64×64 img
    assert 0 <= x < 32 and 0 <= y < 32


def test_points_from_similarity_adds_negatives():
    f, hot = _feature_map_with_hot_region()
    sim = mb.similarity_map(f, hot)
    pp = mb.points_from_similarity(sim, image_shape=(4, 4), n_positive=1, n_negative=2)
    assert len(pp) == 3
    assert list(pp.labels) == [1, 0, 0]


def test_points_from_similarity_threshold_drops_weak_positive():
    sim = np.full((4, 4), 0.1, np.float32)     # nothing matches well
    pp = mb.points_from_similarity(sim, image_shape=(8, 8), n_positive=1, pos_thresh=0.5)
    assert len(pp) == 0


def test_prototype_from_predictor_features_via_fake_tensor():
    f, hot = _feature_map_with_hot_region()
    chw = np.transpose(f, (2, 0, 1))[None]     # (1, C, H, W), like predictor.features

    class _FakeTensor:  # mimics a torch tensor's .detach().cpu().numpy()
        def __init__(self, a): self._a = a
        def detach(self): return self
        def cpu(self): return self
        def numpy(self): return self._a

    mask = np.zeros((4, 4)); mask[0:2, 0:2] = 1
    proto = mb.prototype_from_predictor_features(_FakeTensor(chw), mask)
    assert mb.cosine_similarity(proto, hot) == pytest.approx(1.0)


# ── the bank ─────────────────────────────────────────────────────────────────
def _v(*idx_dim, dim=8):
    """A one-hot-ish vector of length dim with 1.0 at idx_dim[0]."""
    v = np.zeros(dim); v[idx_dim[0]] = 1.0
    return v


def test_bank_add_and_retrieve_by_similarity():
    bank = MemoryBank()
    bank.add(_v(0), "round", tags=["labA"])
    bank.add(_v(1), "elongated")
    bank.add(_v(2), "mitosis")
    hits = bank.retrieve(_v(1), k=1)
    assert len(hits) == 1
    assert hits[0].prototype.label == "elongated"
    assert hits[0].score == pytest.approx(1.0)


def test_bank_retrieve_respects_label_filter():
    bank = MemoryBank()
    bank.add(_v(0), "round")
    bank.add(_v(1), "round")
    bank.add(_v(0), "elongated")
    hits = bank.retrieve(_v(0), k=5, label="round")
    assert all(h.prototype.label == "round" for h in hits)
    assert len(hits) == 2


def test_bank_aggregate_mean_pools_a_label():
    bank = MemoryBank()
    a = np.array([1.0, 0, 0, 0]); b = np.array([0, 1.0, 0, 0])
    bank.add(a, "cell")
    bank.add(b, "cell")
    agg = bank.aggregate("cell")
    assert agg is not None and agg.tags == ["aggregate"]
    # mean of two orthogonal unit vectors, renormalised → equal components
    assert agg.vector[0] == pytest.approx(agg.vector[1])
    assert bank.aggregate("nonexistent") is None


def test_bank_remove_and_labels():
    bank = MemoryBank()
    p = bank.add(_v(0), "round")
    bank.add(_v(1), "elongated")
    assert set(bank.labels()) == {"round", "elongated"}
    assert bank.remove(p.id) is True
    assert bank.labels() == ["elongated"]
    assert bank.remove("nope") is False


def test_bank_save_load_round_trip(tmp_path):
    bank = MemoryBank()
    bank.add(_v(2), "mitosis", tags=["lab1"], meta={"microscope": "confocal"})
    bank.add(_v(3), "debris")
    out = bank.save(tmp_path / "bank")
    assert (out / "vectors.npz").exists() and (out / "meta.json").exists()

    loaded = MemoryBank.load(out)
    assert len(loaded) == 2
    assert set(loaded.labels()) == {"mitosis", "debris"}
    hit = loaded.retrieve(_v(2), k=1)[0]
    assert hit.prototype.label == "mitosis"
    assert hit.prototype.meta["microscope"] == "confocal"
    assert hit.score == pytest.approx(1.0)


def test_bank_load_missing_dir_is_empty(tmp_path):
    assert len(MemoryBank.load(tmp_path / "nope")) == 0
