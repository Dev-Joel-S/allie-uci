set -euo pipefail
cd -- "$(dirname -- "$0")"
export UV_PYTHON_DOWNLOADS=never
export SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.crt
git init source
git -C source remote add origin https://github.com/y0mingzhang/allie.git
git -C source fetch --depth 1 origin 0aace9abefbd75a24e3a1fd37e9dd1d3f992435b
git -C source checkout --detach FETCH_HEAD
python3.12 -m venv .venv
uv pip install --python .venv/bin/python --index-url https://download.pytorch.org/whl/cpu 'torch==2.10.0'
uv pip install --python .venv/bin/python 'numpy>=1.26,<3' 'scipy>=1.11' \
  'chess>=1.10' 'huggingface-hub>=0.20' 'safetensors>=0.4' 'pytest>=8'
bash install-backend.sh
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
