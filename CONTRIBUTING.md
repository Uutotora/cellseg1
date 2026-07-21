# Contributing

This repo is built primarily by AI coding agents working with a human. The
full, authoritative guide — what the project is, how to build/run/test it, the
task queue, and the git workflow — lives in **[`AGENTS.md`](AGENTS.md)** (the
cross-tool convention, auto-loaded by Claude Code via `CLAUDE.md`).

Quick pointers:

- **What to work on:** [`docs/BACKLOG.md`](docs/BACKLOG.md) (project-wide) and
  [`docs/velum/BACKLOG.md`](docs/velum/BACKLOG.md) (the app). See
  [`docs/README.md`](docs/README.md) for the documentation map.
- **Set up:** `bash scripts/setup.sh` (conda env + SAM weights), then
  `bash run_studio.sh`.
- **Test:** `pytest` — the pure-logic suite runs without torch/PyQt6
  (`pip install --group test`). Keep it green; add a test for new logic.
- **Commits & PRs:** one meaningful change per commit; log every meaningful
  change in the relevant `CHANGELOG.md`. PRs follow the template — summary,
  test plan, and what is explicitly *not* verified.

Please read `AGENTS.md` before your first change.
