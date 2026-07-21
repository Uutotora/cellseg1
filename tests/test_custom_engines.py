"""Unit tests for velum_core.custom_engines ("bring your own engine").

Pure stdlib + importlib + the engine registry — no Qt/torch — so it runs in
the light CI ``test`` group. Each test uses an isolated, empty registry so a
loaded plugin can't leak into (or be masked by) the real built-in engines.
"""
import pytest

from velum_core import custom_engines, engine_registry


@pytest.fixture
def isolated_registry(monkeypatch):
    monkeypatch.setattr(engine_registry, "_registry", {})
    return engine_registry


def _write_plugin(path, key="myeng", label="My Engine"):
    path.write_text(
        "from velum_core.engine_registry import EngineSpec, register\n"
        f"register(EngineSpec(key={key!r}, label={label!r}, "
        "predict=lambda img, cfg: img, available=lambda: True))\n",
        encoding="utf-8",
    )
    return path


# ── load_engine_file ──────────────────────────────────────────────────────────

def test_load_engine_file_registers_and_returns_keys(isolated_registry, tmp_path):
    plugin = _write_plugin(tmp_path / "eng.py")
    keys = custom_engines.load_engine_file(plugin)
    assert keys == ["myeng"]
    assert isolated_registry.is_registered("myeng")


def test_load_engine_file_missing_file_raises(isolated_registry, tmp_path):
    with pytest.raises(ValueError, match="File not found"):
        custom_engines.load_engine_file(tmp_path / "nope.py")


def test_load_engine_file_non_python_raises(isolated_registry, tmp_path):
    bad = tmp_path / "eng.txt"
    bad.write_text("whatever")
    with pytest.raises(ValueError, match="Python"):
        custom_engines.load_engine_file(bad)


def test_load_engine_file_that_registers_nothing_raises(isolated_registry, tmp_path):
    empty = tmp_path / "empty.py"
    empty.write_text("x = 1\n")
    with pytest.raises(ValueError, match="did not register an engine"):
        custom_engines.load_engine_file(empty)


def test_load_engine_file_import_error_is_wrapped(isolated_registry, tmp_path):
    broken = tmp_path / "broken.py"
    broken.write_text("raise RuntimeError('boom')\n")
    with pytest.raises(ValueError, match="Plugin failed to load"):
        custom_engines.load_engine_file(broken)


def test_load_engine_file_reload_reregisters(isolated_registry, tmp_path):
    """A fresh module name per load means re-loading the same (edited) file
    re-executes it instead of being short-circuited by sys.modules."""
    plugin = _write_plugin(tmp_path / "eng.py", label="First")
    custom_engines.load_engine_file(plugin)
    assert isolated_registry.get("myeng").label == "First"
    _write_plugin(plugin, label="Second")
    custom_engines.load_engine_file(plugin)
    assert isolated_registry.get("myeng").label == "Second"


# ── CustomEngineStore ─────────────────────────────────────────────────────────

def test_store_roundtrips_entries_and_keys(tmp_path):
    store = custom_engines.CustomEngineStore(tmp_path)
    store.add(tmp_path / "a.py", ["a1", "a2"])
    store.add(tmp_path / "b.py", ["b1"])
    assert store.custom_keys() == {"a1", "a2", "b1"}
    assert {e["path"] for e in store.entries()} == {
        str((tmp_path / "a.py").resolve()), str((tmp_path / "b.py").resolve())}


def test_store_add_replaces_same_path(tmp_path):
    store = custom_engines.CustomEngineStore(tmp_path)
    store.add(tmp_path / "a.py", ["old"])
    store.add(tmp_path / "a.py", ["new"])
    assert store.custom_keys() == {"new"}
    assert len(store.entries()) == 1


def test_store_remove_key_drops_its_entry(tmp_path):
    store = custom_engines.CustomEngineStore(tmp_path)
    store.add(tmp_path / "a.py", ["a1"])
    store.remove_key("a1")
    assert store.custom_keys() == set()
    assert store.entries() == []


def test_store_tolerates_missing_or_corrupt_manifest(tmp_path):
    store = custom_engines.CustomEngineStore(tmp_path)
    assert store.entries() == []          # never written yet
    store.path.write_text("not json{", encoding="utf-8")
    assert store.entries() == []          # corrupt → empty, not a crash


# ── register_persisted ────────────────────────────────────────────────────────

def test_register_persisted_reloads_all(isolated_registry, tmp_path):
    plugin = _write_plugin(tmp_path / "eng.py")
    store = custom_engines.CustomEngineStore(tmp_path)
    store.add(plugin, ["myeng"])
    isolated_registry._registry.clear()   # simulate a fresh launch
    loaded = custom_engines.register_persisted(store)
    assert loaded == ["myeng"]
    assert isolated_registry.is_registered("myeng")


def test_register_persisted_skips_broken_plugin(isolated_registry, tmp_path):
    """A plugin whose file has since moved must never stop startup."""
    store = custom_engines.CustomEngineStore(tmp_path)
    store.add(tmp_path / "gone.py", ["gone"])
    assert custom_engines.register_persisted(store) == []
