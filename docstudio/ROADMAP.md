# Roadmap — CellSeg1 Studio

Phases from design skeleton to shippable product. Each phase closes when its
`BACKLOG.md` items are done and logged in `CHANGELOG.md`.

### Phase 0 — Design skeleton ✅ (current)
Native, static, logic-free reproduction of the mockup. Frameless rounded
window, all screens + overlays, design tokens + UI kit. Launches on PyQt6
alone. **This is where we are.**

### Phase 1 — A usable shell
Projects become real (data model + store), the new-project flow works, and the
**Segment** workspace is wired: embedded napari canvas, the custom Layers panel
driving `viewer.layers`, real predict + Results. After Phase 1 you can create a
project, load images, segment, and read results — end to end, in the new UI.

### Phase 2 — Differentiation
Models & Train, Assistant (diagnostics), Dashboard (Aim), Logs, and the ⌘K
command palette all wired. The features that make Studio more than a viewer.

### Phase 3 — Polish & platform
Live theme repaint + persistence, Guide/onboarding, Settings, native rounded
corners, and a packaged `.app`. The 1.0 finish.

### North star
Tens of thousands of microscopists using Studio daily; the reference
open-source tool for cell segmentation. Every decision is made for that.
