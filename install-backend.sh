set -euo pipefail
cd -- "$(dirname -- "$0")"
EXPECTED=0aace9abefbd75a24e3a1fd37e9dd1d3f992435b
[[ "$(git -C source rev-parse HEAD)" == "$EXPECTED" ]] || {
  echo "Unexpected upstream checkout; refusing to patch." >&2; exit 1;
}
export UV_PYTHON_DOWNLOADS=never
export VIRTUAL_ENV="$PWD/.venv"
export PYO3_PYTHON="$VIRTUAL_ENV/bin/python"
export PYTHONPATH="$PWD/python-packages:$PWD/source/src"
"$PYO3_PYTHON" patch-backend.py
WHEELS="$(mktemp -d "$PWD/wheels-uci.XXXXXX")"
maturin build --release --locked --compatibility linux \
  --manifest-path source/rust/allie-fast/Cargo.toml \
  --interpreter "$PYO3_PYTHON" --out "$WHEELS"
shopt -s nullglob
FILES=("$WHEELS"/allie_fast-*.whl)
[[ "${#FILES[@]}" == 1 ]] || { echo "Expected exactly one native wheel" >&2; exit 1; }
uv pip install --python "$PYO3_PYTHON" --target "$PWD/python-packages" \
  --reinstall --no-deps "${FILES[0]}"
"$PYO3_PYTHON" backend_check.py
uv pip freeze --python "$PYO3_PYTHON" > installed-requirements.txt
git -C source diff > upstream.patch
