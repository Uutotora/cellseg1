<!--
Keep PRs focused: one meaningful change each (see AGENTS.md → Working agreement).
Delete any section that genuinely doesn't apply.
-->

## Summary

<!-- What changed and, briefly, *why*. -->

## Test plan

<!-- How you verified it. For pure logic, name the tests. -->

- [ ] `pytest` green (full suite, offscreen Qt if GUI code is touched)
- [ ] New/changed logic has a test

## Not verified

<!-- Be explicit about what this PR does NOT prove — real GUI behaviour, real
model inference, packaging, anything that can't run headless here. -->

## Docs

- [ ] `docs/CHANGELOG.md` (or `docs/velum/CHANGELOG.md`) has a dated line
- [ ] `AGENTS.md` updated if build/run/test/layout changed
