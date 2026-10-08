#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == --inside ]]; then
set -euo pipefail
cd -- "$2"
export UV_PYTHON_DOWNLOADS=never
export SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.crt
if [[ ! -d source/.git ]]; then
  git init source
  git -C source remote add origin https://github.com/y0mingzhang/allie.git
  git -C source fetch --depth 1 origin 0aace9abefbd75a24e3a1fd37e9dd1d3f992435b
  git -C source checkout --detach FETCH_HEAD
fi
[[ -x .venv/bin/python ]] || python3.12 -m venv .venv
if [[ "${3:-}" != --native-only ]]; then
uv pip install --python .venv/bin/python --index-url https://download.pytorch.org/whl/cpu 'torch==2.10.0'
uv pip install --python .venv/bin/python 'numpy>=1.26,<3' 'scipy>=1.11' \
  'chess>=1.10' 'huggingface-hub>=0.20' 'safetensors>=0.4' 'pytest>=8'
fi
EXPECTED=0aace9abefbd75a24e3a1fd37e9dd1d3f992435b
[[ "$(git -C source rev-parse HEAD)" == "$EXPECTED" ]] || {
  echo "Unexpected upstream checkout; refusing to patch." >&2; exit 1;
}
.venv/bin/python - <<'PATCH'
from pathlib import Path
def replace(path, old, new):
    p = Path(path)
    s = p.read_text()
    if new in s:
        return
    if s.count(old) != 1:
        raise RuntimeError(f"Unexpected upstream source: {path}")
    p.write_text(s.replace(old, new))
p = Path("source/rust/allie-fast/src/lib.rs")
s = p.read_text()
addition = """
// One UCI worker per process. Stop is checked between native KL batches.
pub static UCI_STOP: std::sync::atomic::AtomicBool =
    std::sync::atomic::AtomicBool::new(false);

#[pyfunction]
fn uci_stop(value: bool) {
    UCI_STOP.store(value, std::sync::atomic::Ordering::Relaxed);
}
"""
if "pub static UCI_STOP:" not in s:
    p.write_text(s + addition)
replace(str(p), '    m.add("INTERFACE", INTERFACE)?;',
    '    m.add("INTERFACE", INTERFACE)?;\n'
    '    m.add_function(wrap_pyfunction!(uci_stop, m)?)?;')
replace("source/rust/allie-fast/src/search/kl.rs",
    "(t + self.lag <= deadline).then(",
    "(!crate::UCI_STOP.load(std::sync::atomic::Ordering::Relaxed)"
    " && t + self.lag <= deadline).then(")
PATCH
export UV_PYTHON_DOWNLOADS=never
export VIRTUAL_ENV="$PWD/.venv"
export PYO3_PYTHON="$VIRTUAL_ENV/bin/python"
export PYTHONPATH="$PWD/python-packages:$PWD/source/src"
WHEELS="$(mktemp -d "$PWD/wheels-uci.XXXXXX")"
maturin build --release --locked --compatibility linux \
  --manifest-path source/rust/allie-fast/Cargo.toml \
  --interpreter "$PYO3_PYTHON" --out "$WHEELS"
shopt -s nullglob
FILES=("$WHEELS"/allie_fast-*.whl)
[[ "${#FILES[@]}" == 1 ]] || { echo "Expected exactly one native wheel" >&2; exit 1; }
uv pip install --python "$PYO3_PYTHON" --target "$PWD/python-packages" \
  --reinstall --no-deps "${FILES[0]}"
"$PYO3_PYTHON" -c 'from engine import check_backend; lib = check_backend(); print("PASS: native backend", lib.__file__)'
uv pip freeze --python "$PYO3_PYTHON" > installed-requirements.txt
git -C source diff > upstream.patch

if [[ "${3:-}" == --native-only ]]; then exit 0; fi
if [[ ! -s model-path.txt ]] || [[ ! -f "$(cat model-path.txt)/model.safetensors" ]]; then
.venv/bin/python - <<'DOWNLOAD'
import json
from pathlib import Path
from huggingface_hub import HfApi, snapshot_download
repo = "yimingzhang/allie-2.0"
revision = HfApi().model_info(repo).sha
location = snapshot_download(repo, revision=revision,
    allow_patterns=["config.json", "model.safetensors"])
Path("model-path.txt").write_text(location)
Path("model-revision.json").write_text(json.dumps(
    {"repository": repo, "revision": revision, "path": location}, indent=2))
DOWNLOAD
fi
.venv/bin/python engine.py --unit
.venv/bin/python engine.py --test

  exit 0
fi
PACKAGE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
[[ "$(uname -sm)" == "Linux x86_64" ]] || { echo "Requires x86_64 Linux." >&2; exit 1; }
command -v nix-build >/dev/null
ROOT="${1:-${XDG_DATA_HOME:-$HOME/.local/share}/allie-uci-0aace9ab}"
[[ "$ROOT" == /* ]] || { echo "Use an absolute installation path." >&2; exit 1; }
if [[ -e "$ROOT" && ! -d "$ROOT/source/.git" ]]; then
  echo "Not an existing Allie installation: $ROOT" >&2; exit 1
fi
mkdir -p -- "$ROOT"
ROOT="$(cd -- "$ROOT" && pwd -P)"
for FILE in install.sh start.sh engine.py shell.nix; do
  if [[ "$PACKAGE_DIR" != "$ROOT" ]]; then cp -- "$PACKAGE_DIR/$FILE" "$ROOT/$FILE"; fi
done
nix-build "$ROOT/shell.nix" -o "$ROOT/runtime"
NIX_BASH="$(nix-build --no-out-link -E 'let p = import (builtins.fetchTarball "https://github.com/NixOS/nixpkgs/archive/e7439b6b14ad3cc35d05608ebca9bce01a25f5f8.tar.gz") { system = "x86_64-linux"; }; in p.bash')"
# An absolute interpreter lets En Croissant launch the installed script directly.
{
  printf '#!%s/bin/bash\n' "$NIX_BASH"
  tail -n +2 "$PACKAGE_DIR/start.sh"
} > "$ROOT/start.sh.new"
mv -- "$ROOT/start.sh.new" "$ROOT/start.sh"
chmod +x "$ROOT/start.sh"
# Retain the binary path used by existing En Croissant configurations.
ln -sfn -- start.sh "$ROOT/allie-uci"
"$ROOT/runtime/bin/allie-env" "$ROOT/install.sh" --inside "$ROOT" 2>&1 | tee "$ROOT/install.log"
printf '\nEn Croissant: %s/start.sh\n' "$ROOT"
