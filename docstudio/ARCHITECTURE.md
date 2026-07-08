# Architecture — CellSeg1 Studio

## Module map (`studio/`)

```
app.py            StudioWindow(QMainWindow) + main(). Frameless rounded window,
                  title bar, sidebar, screen stack, overlays, ⌘K, theme toggle.
                  THE entry point. Pure design — imports no napari/torch.
window_chrome.py  TitleBar (own traffic lights, native move) + corner grips.
theme.py          Design tokens (light+dark) + QSS builders + viridis ramp. Pure.
components.py     The static UI kit (atoms) + the navigation Sidebar.
paint.py          QPainter "nuclei" stand-in art (canvas, card covers, thumbs).
demo.py           Static demo content for tabs not yet wired. No logic.
project.py        Project/ProjectSettings/ProjectStats/ProjectStore — the real,
                  persisted data model (pure stdlib). The Projects tab's data layer.
project_controller.py  ProjectController (Qt-free): search/filter, favourites,
                  the active project shared with the Workspace tab, sample
                  seeding. Home/Projects screens are bound to it.
screens.py        HomeScreen, ProjectsScreen — bound to project_controller
                  (+ shared page_header/scroll helpers). Live data, not demo.
                  Home's quick cards/resource links are all real actions now
                  (New Project dialog, navigate, external open, "Open Sample").
new_project_dialog.py  NewProjectDialog — the "+ New Project" modal (scrim +
                  centred panel, same construction as overlays.CommandPalette):
                  name+description → import (drag-drop or a file picker) →
                  engine, writing through ProjectStore.create() on finish.
workspace.py      WorkspaceScreen — the signature Segment screen
                  (Images|Layers panel · canvas · Segment|Results inspector).
                  Still static except the top-bar breadcrumb/engine chip,
                  which reflect the real active project (set_active_project).
extra_screens.py  ModelsScreen (train), DashboardScreen (charts + runs table).
overlays.py       AssistantDrawer, LogsConsole, CommandPalette, Toast (now has
                  a real announce() used by project creation, not just static).
icons.py          Studio's OWN icon set (from the mockup) — self-contained.
motion.py         Small motion helpers: fade_in (screen switches),
                  install_hover_lift (animated shadow "elevation" on hover —
                  QSS has no transform/transition, so this animates a
                  QGraphicsDropShadowEffect instead). Self-contained.
fonts/            Figtree (SIL OFL), registered at startup.
tests/            Studio's own test suite (run `pytest studio/tests`).
```

`studio/` is a **self-contained** top-level package — a sibling of the classic
`napari_app/` (old app) and the shared ML-core modules. It has its own icons and
motion and imports nothing from `napari_app` (the ML core is pulled in lazily,
only inside a tab being wired). Import direction is one-way, leaf → shell:
`theme`/`icons` ← `components`/`paint` ← `demo`/screens ← `app`.

## Entry points

- **New:** `run_studio.sh` / `cellseg1-studio` → `studio.app:main`.
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

1. **Re-introduce the data it needs.** If it was removed in the skeleton reset,
   it's in git history (`git log -- studio/<name>.py`) — reintroduce and adapt.
   Worked example: `studio/project.py` (the `Project`/`ProjectStore` model),
   restored for the Projects tab.
2. **Add a controller**, Qt-free where possible, that owns the logic and takes
   plain callbacks — mirror `napari_app/core/predict_controller.py`. Unit-test
   it without Qt. Worked example: `studio/project_controller.py`.
3. **Bind the screen to the controller.** Replace the screen's `demo.*` reads
   with live data; connect its buttons/toggles/sliders to controller calls;
   feed results back into the same widgets. **Do not restyle** — reuse the
   existing atoms.
4. **Lazily import heavy deps** (torch, engines, ML-core modules — **not**
   napari; we build our own canvas) inside the controller / handlers, never at
   a shared module's top level.
5. **Test:** pure controller logic in the light group; screen wiring
   headless (`pytest.importorskip("PyQt6")`, offscreen). Note GUI/GPU parts as
   not-verified-here.
6. **Ship** per the repo's branch → PR → green-CI workflow; log it in this
   folder's `CHANGELOG.md` and tick the tab in `BACKLOG.md`.

### The Segment tab specifically — our OWN canvas, not embedded napari

**We are not embedding napari.** Studio gets its **own** image canvas — like
Label Studio's and napari's viewers, but ours — so we own the look, the tool
strip, the layer model and every interaction (that's why the mockup's canvas
toolbar was redrawn from scratch). We reuse the *interaction patterns*
(pan/zoom, layers, brush/polygon/point editing, 2D↔3D, grid) and, above all,
the **segmentation logic** (engines, predict, morphometry) — we do not
reimplement the ML, and we do not reimplement the UI napari-style either.

Plan (see BACKLOG for the task list):

- Build a `Canvas` widget (start on `QGraphicsView`/`QGraphicsScene` or a
  custom `QWidget` + `QPainter`; a GPU `QOpenGLWidget` path later) that renders
  the image + label/shape/point layers with pan/zoom — replacing the
  `NucleiView` stand-in. Own the viewer bar (2D↔3D, grid, home) + tool strip.
- Give it our **own layer model** (an evented list of image/labels/shapes/points
  layers) that the existing custom Layers panel drives — visibility, opacity,
  new-layer, delete, colours. Interaction model *inspired by* napari; code ours.
- Wire Segment settings + Run to a predict controller that **reuses the ML
  core** — `napari_app/core/predict_controller.py`, `napari_app/engines*`,
  morphometry in `napari_app/analysis.py` — imported lazily. Results (stats,
  calibration, save/export, colour-by heatmap, GT & eval, batch, benchmark)
  and the toast render into the existing widgets.

The principle for every tab: **own the UI, the icons, the canvas, the settings;
reuse the logic.** We wrap the classic app's proven functionality under the new
design instead of rewriting it — and we build our own viewer instead of
embedding napari's.

## Testing conventions

Studio has its **own** suite in `studio/tests/`. When working on Studio, run
just those (not the classic app's `tests/`):

```
QT_QPA_PLATFORM=offscreen <python> -m pytest studio/tests -q
```

- Pure logic → no Qt import, runs in CI's light `test` group.
- Qt screens → offscreen construct/smoke with `pytest.importorskip("PyQt6")`.
- Before committing, run the throwaway-venv light-group check from the repo
  `AGENTS.md` so nothing heavy leaks into CI.
