#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "Ambiente virtual nao encontrado. Execute ./setup.sh primeiro."
    exit 1
fi

cd "$ROOT_DIR"

# Native acceleration is mandatory for runtime performance.
if ! "$VENV_PYTHON" - <<'PY'
import voxel_accel
PY
then
    echo "Modulo nativo obrigatorio nao encontrado. Execute ./setup.sh novamente."
    exit 1
fi

exec "$VENV_PYTHON" main.py
