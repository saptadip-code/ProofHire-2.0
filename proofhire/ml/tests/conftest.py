"""Path setup so `pytest ml/tests -q` works with or without PYTHONPATH=backend (Member 1)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "backend", ROOT / "ml" / "data", ROOT / "ml"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
