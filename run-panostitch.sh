#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
LOCAL_ROOT=${PANOSTITCH_LOCAL_ROOT:-/run/media/stolpee/localprog/panostitch}
VENV_ROOT="$LOCAL_ROOT/venvs/default"
VENV_PYTHON="$VENV_ROOT/bin/python"

if [ ! -x "$VENV_PYTHON" ]; then
  echo "PanoStitch virtualenv is missing. Bootstrapping into $LOCAL_ROOT ..." >&2
  PANOSTITCH_LOCAL_ROOT="$LOCAL_ROOT" python3 "$PROJECT_ROOT/scripts/bootstrap_local_env.py"
fi

unset PYTHONHOME
unset PYTHONSAFEPATH

if [ -n "${PYTHONPATH:-}" ]; then
  export PYTHONPATH="$PROJECT_ROOT/src:$PYTHONPATH"
else
  export PYTHONPATH="$PROJECT_ROOT/src"
fi

export PANOSTITCH_LOCAL_ROOT="$LOCAL_ROOT"
export TMPDIR="$LOCAL_ROOT/tmp"
export PIP_CACHE_DIR="$LOCAL_ROOT/pip-cache"

if ! "$VENV_PYTHON" -c "import PySide6, panostitch" >/dev/null 2>&1; then
  echo "PanoStitch runtime is incomplete or stale. Rebuilding local environment in $LOCAL_ROOT ..." >&2
  PANOSTITCH_LOCAL_ROOT="$LOCAL_ROOT" python3 "$PROJECT_ROOT/scripts/bootstrap_local_env.py"
fi

exec "$VENV_PYTHON" -m panostitch "$@"
