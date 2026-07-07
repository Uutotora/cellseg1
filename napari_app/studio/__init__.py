"""CellSeg1 Studio — the standalone desktop application layer.

**Design-skeleton phase.** This branch is a faithful, *static* reproduction of
the north-star mockup with **no business logic** — no napari, no torch, no
model or project IO. It launches on PyQt6 alone. Real functionality is wired
back tab by tab; the plan, the fresh-agent prompt, the changelog and the
backlog all live in the repo's ``docstudio/`` folder.

Modules (import direction is one-way, leaf → shell):

- :mod:`~napari_app.studio.theme` — design tokens (light + dark) + QSS.
- :mod:`~napari_app.studio.components` — the static UI kit + sidebar.
- :mod:`~napari_app.studio.paint` — the nuclei canvas stand-in art.
- :mod:`~napari_app.studio.demo` — static demo content.
- :mod:`~napari_app.studio.screens` / :mod:`~.workspace` / :mod:`~.extra_screens`
  — the screens.
- :mod:`~napari_app.studio.overlays` — assistant drawer, logs, ⌘K palette, toast.
- :mod:`~napari_app.studio.window_chrome` — the frameless title bar.
- :mod:`~napari_app.studio.app` — ``StudioWindow`` + ``main`` (the entry point).

The data model that briefly lived here (``project.py``, carrying every
predict/train setting) was removed with the rest of the logic for this phase;
it's preserved in git history and returns when the Projects tab is wired
(see ``docstudio/BACKLOG.md``).
"""
