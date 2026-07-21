"""Load user-provided segmentation engines ("bring your own engine").

A custom engine is nothing more than a Python file that calls
``velum_core.engine_registry.register(EngineSpec(...))`` at import time — the
exact one-call contract the built-in engines (:mod:`velum_core.engines`) use.
This module imports such a file as a throwaway module, notes which engine
keys it added to the registry, and (via :class:`CustomEngineStore`) remembers
the file path in a small JSON manifest so the engine re-registers on the next
launch.

Deliberately dependency-free beyond :mod:`velum_core.engine_registry` (stdlib
``importlib`` + ``json``) so it runs in the light CI ``test`` group. Loading a
Python file is inherently as powerful as the file's author makes it — this is
a local desktop app running the user's *own* plugin, the same trust model as
``pip install``-ing an engine package, just without the packaging ceremony.
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

from velum_core import engine_registry

MANIFEST_NAME = "custom_engines.json"


def _import_file_as_module(path: Path) -> None:
    """Import ``path`` as a uniquely-named, non-cached module.

    A fresh module name per load (uuid-suffixed) means re-loading the same
    file — e.g. after the user edits their plugin — actually re-executes it
    and re-registers, rather than being short-circuited by ``sys.modules``.
    """
    mod_name = f"velum_custom_engine_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Not an importable Python file: {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


def load_engine_file(path: str | Path) -> list[str]:
    """Import a plugin file and return the engine keys it registered.

    Keys are captured by watching ``engine_registry.register`` calls made
    while the file imports — so a plugin that *updates* an already-registered
    key (e.g. a re-load after an edit) is still reported, which a plain
    before/after diff of the registry would miss.

    Raises ``ValueError`` if the file is missing, isn't a ``.py`` file, fails
    to import, or imports cleanly but registers no engine (the most common
    mistake — a specific message beats a silent no-op).
    """
    path = Path(path)
    if not path.exists():
        raise ValueError(f"File not found: {path}")
    if path.suffix.lower() != ".py":
        raise ValueError("An engine plugin must be a Python (.py) file.")

    seen: list[str] = []
    real_register = engine_registry.register

    def _tracking_register(spec):
        seen.append(spec.key)
        real_register(spec)

    engine_registry.register = _tracking_register
    try:
        _import_file_as_module(path)
    except ValueError:
        raise
    except Exception as e:  # any error the plugin itself raised while importing
        raise ValueError(f"Plugin failed to load: {e}") from e
    finally:
        engine_registry.register = real_register

    keys = sorted(dict.fromkeys(seen))  # de-dup, stable
    if not keys:
        raise ValueError(
            "This file did not register an engine. It must call "
            "velum_core.engine_registry.register(EngineSpec(...)) at import time."
        )
    return keys


class CustomEngineStore:
    """The on-disk manifest of loaded custom-engine plugins.

    One JSON file (``<storage>/custom_engines.json``) holding a list of
    ``{"path": <plugin file>, "keys": [<engine keys>]}`` entries — enough to
    re-register every plugin on the next launch and to know which registry
    keys came from a user plugin (so the UI can badge and remove them).
    """

    def __init__(self, storage_dir: str | Path):
        self.path = Path(storage_dir) / MANIFEST_NAME

    def _read(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    def _write(self, entries: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def entries(self) -> list[dict]:
        return self._read()

    def custom_keys(self) -> set[str]:
        """Every engine key that came from a loaded plugin."""
        keys: set[str] = set()
        for e in self._read():
            keys.update(e.get("keys", []))
        return keys

    def add(self, path: str | Path, keys: list[str]) -> None:
        """Record a plugin (replacing any prior entry for the same file)."""
        path = str(Path(path).resolve())
        entries = [e for e in self._read() if e.get("path") != path]
        entries.append({"path": path, "keys": list(keys)})
        self._write(entries)

    def remove_key(self, key: str) -> None:
        """Drop whichever plugin entry registered ``key`` from the manifest."""
        entries = [e for e in self._read() if key not in e.get("keys", [])]
        self._write(entries)


def register_persisted(store: CustomEngineStore) -> list[str]:
    """Re-register every plugin recorded in ``store`` (best-effort).

    Returns the keys that loaded successfully. A plugin whose file has since
    moved or errors is skipped silently — a broken plugin must never stop the
    app from starting — and its recorded keys simply won't appear.
    """
    loaded: list[str] = []
    for entry in store.entries():
        path = entry.get("path", "")
        try:
            loaded.extend(load_engine_file(path))
        except ValueError:
            continue
    return loaded
