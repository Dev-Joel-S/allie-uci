"""Validate the pinned native extension before loading model weights."""
import importlib
import sys
from pathlib import Path

def check_backend():
    try:
        lib = importlib.import_module("allie_fast")
    except ImportError as exc:
        raise RuntimeError(
            f"Cannot import allie_fast with {sys.executable}: {exc}. "
            "Run repair.sh from the updated repository.") from exc
    expected = Path(__file__).resolve().parent / "python-packages"
    location = getattr(lib, "__file__", None)
    if not location or not Path(location).resolve().is_relative_to(expected.resolve()):
        raise RuntimeError(f"Wrong allie_fast location: {location}; expected {expected}")
    missing = [name for name in
               ("Engine", "Server", "Position", "KL", "Coverage", "place", "uci_stop")
               if not hasattr(lib, name)]
    if getattr(lib, "INTERFACE", None) != 2 or missing:
        raise RuntimeError(
            f"Incompatible allie_fast at {location}: "
            f"INTERFACE={getattr(lib, 'INTERFACE', None)}, missing={missing}. "
            "Run repair.sh. The module does not require an attribute named fast.")
    lib.uci_stop(False)
    return lib

if __name__ == "__main__":
    lib = check_backend()
    print(f"PASS: native backend {lib.__file__}, INTERFACE=2, UCI cancellation")
