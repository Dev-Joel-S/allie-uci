set -euo pipefail
cd -- "$(dirname -- "$0")"
export PYTHONPATH="$PWD/source/src"
export PYTHONUNBUFFERED=1
case "${1:-}" in
  --unit) exec .venv/bin/python test.py --unit ;;
  --test) exec .venv/bin/python test.py ;;
  --game) exec .venv/bin/python test.py --game ;;
  *) exec .venv/bin/python engine.py ;;
esac
