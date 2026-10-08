#!/usr/bin/env bash
# Allie 2.0 Calibrated UCI / NixOS x86_64. Experimental; not runtime-tested here.
set -euo pipefail
PACKAGE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
[[ "$(uname -sm)" == "Linux x86_64" ]] || { echo "Requires x86_64 Linux / NixOS."; exit 1; }
command -v nix-build >/dev/null || { echo "nix-build is required."; exit 1; }
ROOT="${1:-${XDG_DATA_HOME:-$HOME/.local/share}/allie-uci-0aace9ab}"
[[ "$ROOT" == /* ]] || { echo "Use an absolute installation path."; exit 1; }
[[ ! -e "$ROOT" ]] || { echo "Already exists: $ROOT (choose a new directory)."; exit 1; }
mkdir -p "$ROOT"
ROOT="$(cd "$ROOT" && pwd -P)"
trap 'echo "Installation failed. Files and logs remain in: $ROOT" >&2' ERR
cp -- "$PACKAGE_DIR/environment.nix" "$ROOT/environment.nix"
nix-build "$ROOT/environment.nix" -o "$ROOT/runtime"
for FILE in build.sh install-backend.sh patch-backend.py backend_check.py; do
  cp -- "$PACKAGE_DIR/$FILE" "$ROOT/$FILE"
done

cp -- "$PACKAGE_DIR/engine.py" "$ROOT/engine.py"

cp -- "$PACKAGE_DIR/test.py" "$ROOT/test.py"

cp -- "$PACKAGE_DIR/run.sh" "$ROOT/run.sh"
# Use an absolute Nix-store Bash interpreter; no /usr/bin/env dependency in the GUI.
NIX_BASH="$(nix-build --no-out-link -E \
 'let p = import (builtins.fetchTarball "https://github.com/NixOS/nixpkgs/archive/e7439b6b14ad3cc35d05608ebca9bce01a25f5f8.tar.gz") { system = "x86_64-linux"; }; in p.bash')"
{
  printf '#!%s/bin/bash\n' "$NIX_BASH"
  printf 'set -euo pipefail\n'
  printf 'ROOT=%q\n' "$ROOT"
  printf 'exec "$ROOT/runtime/bin/allie-env" "$ROOT/run.sh" "$@"\n'
} > "$ROOT/allie-uci"
chmod +x "$ROOT/allie-uci"
cp -- "$PACKAGE_DIR/README.txt" "$ROOT/README.txt"

"$ROOT/runtime/bin/allie-env" "$ROOT/build.sh" 2>&1 | tee "$ROOT/install.log"
"$ROOT/allie-uci" --unit 2>&1 | tee "$ROOT/unit-tests.log"
"$ROOT/allie-uci" --test 2>&1 | tee "$ROOT/model-tests.log"
trap - ERR
printf '\nInstalled; included UCI/model checks passed on this machine.\n'
printf 'En Croissant -> Engines -> Add New -> Local -> Binary:\n%s/allie-uci\n' "$ROOT"
printf 'Full game test: %q --game\n' "$ROOT/allie-uci"
printf 'Set BaseTime to the initial seconds of your actual game.\n'
