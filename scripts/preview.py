"""Load sample leads into the board so you can iterate on the design without
waiting for a real collection run.

    python scripts/preview.py        # load samples
    python scripts/preview.py --clear # back to empty

Then: cd docs && python -m http.server 8000
"""
import json, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "docs" / "data" / "leads.json"

if "--clear" in sys.argv:
    TARGET.write_text(json.dumps(
        {"generated_at": None,
         "counts": {"total": 0, "priority": 0, "watch": 0, "logged": 0},
         "leads": []}, indent=2))
    print("cleared")
else:
    shutil.copy(ROOT / "scripts" / "demo_leads.json", TARGET)
    print("sample leads loaded — these are fabricated, do not act on them")
