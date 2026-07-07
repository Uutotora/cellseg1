# Architecture — CellSeg1 Studio

## Module map (`napari_app/studio/`)

```
app.py            StudioWindow(QMainWindow) + main(). Frameless rounded window,
                  title bar, sidebar, screen stack, overlays, ⌘K, theme toggle.
                  THE entry point. Pure design — imports no napari/torch.
window_chrome.py  TitleBar (own traffic lights, native move) + corner grips.
theme.py          Design tokens (light+dark) + QSS builders + viridis ramp. Pure.
components.py     The static UI kit (atoms) + the navigation Sidebar.
paint.py          QPainter "nuclei" stand-in art (canvas, card covers, thumbs).
demo.py           Static demo content mirroring the mockup. No logic.
screens.py        HomeScreen, ProjectsScreen (+ shared page_header/scroll helpers).
workspace.py      WorkspaceScreen — the signature Segment screen
                  (Images|Layers panel · canvas · Segment|Results inspector).
extra_screens.py  ModelsScreen (train), DashboardScreen (charts + runs table).
overlays.py       AssistantDrawer, LogsConsole, CommandPalette, Toast.
fonts/            Figtree (SIL OFL), registered at startup.
```

Import direction is one-way, leaf → shell: `theme` ← `components`/`paint` ←
`demo`/screens ← `app`. Nothing imports `app`.

## Entry points

- **New:** `run_studio.sh` / `cellseg1-studio` → `napari_app.studio.app:main`.
  Runs the file directly and self-bootstraps `sys.path` (works from any cwd —
  `python -m` would prepend the caller's cwd and import the wrong `napari_app`).
- **Classic (untouched):** `run_napari.sh` / `cellseg1` →
  `napari_app.main:main`. The proven, fully-functional app.

## Why the skeleton is logic-free

`app.py` and every shared module import only PyQt6 + our own leaves. That keeps
the app light (launches with no torch/napari/GPU), keeps the pure-logic tests
runnable in CI's light `test` group, and keeps the design a stable target.
Real dependencies get imported **lazily, inside the tab being wired** — never
at a shared module's top level.

## How to wire a tab (the core workflow)

Each tab goes from *static* to *functional* without changing how it looks.
General recipe:

1. **Re-introduce the data it needs.** For Projects, that's the `Project` /
   `ProjectStore` data model (removed in the skeleton; it's in git history —
   `git log -- napari_app/studio/project.py` — reintroduce and adapt).
2. **Add a controller**, Qt-free where possible, that owns the logic and takes
   plain callbacks — mirror `napari_app/core/predict_controller.py`. Unit-test
   it without Qt.
3. **Bind the screen to the controller.** Replace the screen's `demo.*` reads
   with live data; connect its buttons/toggles/sliders to controller calls;
   feed results back into the same widgets. **Do not restyle** — reuse the
   existing atoms.
4. **Lazily import heavy deps** (napari, torch, engines) inside the controller
   / handlers, never at module top.
5. **Test:** pure controller logic in the light group; screen wiring
   headless (`pytest.importorskip("PyQt6")`, offscreen). Note GUI/GPU parts as
   not-verified-here.
6. **Ship** per the repo's branch → PR → green-CI workflow; log it in this
   folder's `CHANGELOG.md` and tick the tab in `BACKLOG.md`.

### The Segment tab specifically

This is where napari returns. Plan (see BACKLOG for the task list):

- Embed napari's canvas (`napari.Viewer(show=False)`, reparent
  `viewer.window._qt_viewer`) into `WorkspaceScreen`'s centre, replacing the
  `NucleiView` stand-in.
- Drive the **custom** Layers panel from `viewer.layers` events (it already
  looks right — give the eye/opacity/visibility/new-layer/grid/2D-3D controls
  real effects on the viewer). Do **not** show napari's own dock widgets.
- Wire the Segment settings + Run to a predict controller (reuse
  `napari_app/core/predict_controller.py`); feed the Results panel + toast.

## Testing conventions

- Pure logic → `tests/test_studio_*.py`, no Qt import, runs in the light group.
- Qt screens → offscreen construct/smoke with `pytest.importorskip("PyQt6")`.
- Before committing, run the throwaway-venv light-group check from the repo
  `AGENTS.md` so nothing heavy leaks into CI.
