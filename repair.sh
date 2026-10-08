#!/usr/bin/env bash
set -euo pipefail
PACKAGE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="${1:-${XDG_DATA_HOME:-$HOME/.local/share}/allie-uci-0aace9ab}"
[[ "$ROOT" == /* ]] || { echo "Use an absolute installation path." >&2; exit 1; }
[[ -x "$ROOT/runtime/bin/allie-env" && -x "$ROOT/.venv/bin/python" && -d "$ROOT/source/.git" ]] || {
  echo "Not an existing Allie installation: $ROOT" >&2; exit 1;
}
ROOT="$(cd -- "$ROOT" && pwd -P)"
for FILE in install-backend.sh patch-backend.py backend_check.py engine.py test.py run.sh; do
  if [[ "$PACKAGE_DIR" != "$ROOT" ]]; then
    cp -- "$PACKAGE_DIR/$FILE" "$ROOT/$FILE"
  fi
done
"$ROOT/runtime/bin/allie-env" "$ROOT/install-backend.sh" 2>&1 | tee "$ROOT/repair.log"
"$ROOT/allie-uci" --unit
"$ROOT/allie-uci" --test 2>&1 | tee "$ROOT/model-tests.log"
echo "Repair and model/UCI tests passed."
