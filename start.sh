#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ "${1:-}" == --inside ]]; then
  ROOT="$2"
  shift 2
  cd -- "$ROOT"
  export PYTHONPATH="$ROOT/python-packages:$ROOT/source/src"
  export PYTHONUNBUFFERED=1
  exec "$ROOT/.venv/bin/python" "$ROOT/engine.py" "$@"
fi
if [[ -x "$HERE/runtime/bin/allie-env" ]]; then
  ROOT="$HERE"
else
  ROOT="${ALLIE_UCI_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/allie-uci-0aace9ab}"
fi
[[ "$ROOT" == /* ]] || { echo "Use an absolute installation path." >&2; exit 1; }
[[ -x "$ROOT/runtime/bin/allie-env" ]] || { echo "Run install.sh first." >&2; exit 1; }
exec "$ROOT/runtime/bin/allie-env" "$ROOT/start.sh" --inside "$ROOT" "$@"
