#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$ROOT_DIR"

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Native acceleration is mandatory.
cd "$ROOT_DIR/native"
python setup.py build_ext --inplace
cd "$ROOT_DIR"

echo "Ambiente pronto. Execute ./run.sh"
