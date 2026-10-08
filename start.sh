#!/usr/bin/env bash
set -euo pipefail
ROOT="${ALLIE_UCI_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/allie-uci-0aace9ab}"
if [[ ! -x "$ROOT/allie-uci" ]]; then
  printf 'Allie fehlt in: %s\nZuerst ausführen: bash install.sh\n' "$ROOT" >&2
  exit 1
fi
exec "$ROOT/allie-uci" "$@"
