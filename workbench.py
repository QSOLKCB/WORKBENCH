#!/usr/bin/env python3
"""Run the source checkout without installing a package."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from qsol_workbench.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
