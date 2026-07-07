# Changelog — CellSeg1 Studio

What actually shipped in Studio, dated, newest first. (The repo-wide log is
`docs/CHANGELOG.md`; this one is Studio-specific.)

---

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
