set -euo pipefail
cd -- "$(dirname -- "$0")"
export PYTHONPATH="$PWD/python-packages:$PWD/source/src"
export PYTHONUNBUFFERED=1
if [[ "${1:-}" != --unit ]]; then
  .venv/bin/python backend_check.py >&2
fi
case "${1:-}" in
  --diagnose) exit 0 ;;
  --unit) exec .venv/bin/python test.py --unit ;;
  --test) exec .venv/bin/python test.py ;;
  --game) exec .venv/bin/python test.py --game ;;
  *) exec .venv/bin/python engine.py ;;
esac
