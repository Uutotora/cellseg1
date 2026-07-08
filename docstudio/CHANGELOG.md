# Changelog — CellSeg1 Studio

What actually shipped in Studio, dated, newest first. (The repo-wide log is
`docs/CHANGELOG.md`; this one is Studio-specific.)

---

## 2026-07-08 — Studio is now its own top-level project + docs pivot to "own canvas"

Structural + directional clarity, no behaviour change:

- **Studio promoted to a top-level `studio/` package** (`git mv` from
  `napari_app/studio/`, history preserved), a **sibling** of the classic
  `napari_app/` (old app) and the shared ML core — the standard monorepo
  "old app + new app + shared core" shape, so the branch reads as its own
  project. Studio is now **self-contained**: its own `icons.py` (the mockup's
  icons, not the classic app's) and `motion.py`; it imports nothing from
  `napari_app`. The classic `napari_app/icons.py` was reverted to pristine.
- **Studio has its own test suite** in `studio/tests/` (run `pytest
  studio/tests`); `pytest.ini` includes it; packaging/entry point updated
  (`cellseg1-studio = studio.app:main`, `studio/` packaged, tests excluded).
- **Docs pivot — we are NOT embedding napari.** The Segment tab will get our
  **own** canvas (like Label Studio's / napari's viewers, but ours: own tool
  strip, own layer model, own interactions), reusing only the **ML logic**
  (engines/predict/morphometry). New guiding principle across the docs: *own
  the UI, the icons, the canvas, the settings; reuse the logic.* Label Studio
  reaffirmed as the primary **structure** reference (not look). AGENT_PROMPT
  gained explicit git-sync (keep local↔remote in sync) and "run only
  `studio/tests`" guidance.

Verified: full suite 473 passed; Studio's suite green from its new location;
the app imports and boots from the top-level `studio` package offscreen,
importing neither napari nor torch.

## 2026-07-07 — Design skeleton: the mockup, reproduced natively (no logic)

Reset Studio to a pure **design skeleton** — a faithful, static, native-Qt
reproduction of the north-star mockup with **all business logic removed** — so
there's a clean, consistent target to wire functionality against, tab by tab.

- **Stripped all logic** from the running app: no napari, no torch, no model,
  no project/file IO. `import napari` / `import torch` never runs; the app
  launches on PyQt6 alone. Removed the wired-in `PredictWidget`/`TrainWidget`
  hosting and the `project.py` data model (preserved in git history; returns
  when the Projects tab is wired).
- **Native reproduction of every mockup screen** with static demo content
  (`demo.py`): Home, Projects, the Segment workspace (adapted-napari
  **Images|Layers** panel with full layer controls · nuclei canvas · **Segment|
  Results** inspector), Models & Train, Dashboard — plus overlays: Assistant
  drawer, Logs console, ⌘K command palette, toast.
- **Design system** as reusable modules: `theme.py` (tokens), `components.py`
  (the UI-kit atoms + sidebar), `paint.py` (a QPainter nuclei stand-in for the
  canvas / card covers / thumbnails).
- **Rounded window corners** (12px rounded mask) on the frameless window.
- **`docstudio/`** — this doc set (OVERVIEW, DESIGN, ARCHITECTURE, BACKLOG,
  ROADMAP, CHANGELOG, AGENT_PROMPT) driving the tab-by-tab plan.

Verified: full pure-logic suite green; the app boots offscreen and navigates
every screen, opens all overlays, toggles theme and resizes cleanly, importing
**neither napari nor torch**. Not verified here (no display): the live look,
the rounded corners (offscreen can't set window masks — real macOS can), fades.

### Earlier (foundation, superseded by the reset above)
- Frameless window + own dark title bar (own traffic lights, native
  move/resize via `startSystemMove` + grips) replacing the grey OS title bar.
- First shell: sidebar + Home/Projects backed by a `ProjectStore`, embedding
  the classic `PredictWidget`. Reset to a logic-free skeleton on the same day.
