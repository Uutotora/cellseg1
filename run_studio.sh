#!/bin/bash
# Launch Velum — the standalone desktop app (PyQt6, own Qt canvas — not napari).
#
# Equivalent to the installed `velum` / `cellseg1` console command; use this to
# run straight from a source checkout without `pip install -e .`. First run
# needs SAM weights + deps — see scripts/setup.sh.
#
# Resolution order for the Python interpreter:
#   1. $CELLSEG1_PYTHON if set explicitly
#   2. a conda/mamba env named "cellseg1" if one exists
#   3. whatever "python" is on PATH (e.g. an activated venv)
DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$DIR"

# Run the entry FILE directly (not `python -m`): app.py bootstraps sys.path to
# the repo root itself, so this works from any cwd. `-m` would prepend the
# caller's cwd to sys.path ahead of PYTHONPATH and import the wrong package
# when launched from another checkout.
APP="$DIR/studio/app.py"
if [ -n "$CELLSEG1_PYTHON" ]; then
    exec "$CELLSEG1_PYTHON" "$APP"
elif command -v conda >/dev/null 2>&1 && conda env list | grep -qE '[/ ]cellseg1$'; then
    exec conda run --no-capture-output -n cellseg1 python "$APP"
else
    exec python "$APP"
fi
