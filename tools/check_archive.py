#!/usr/bin/env python3
"""Verify a built archive's checksum, manifest and demo after extraction."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def main():
    archive = Path(sys.argv[1]).resolve()
    expected, name = archive.with_suffix(".zip256").read_text().strip().split("  ", 1)
    if name != archive.name or hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise SystemExit("Archive checksum mismatch")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with zipfile.ZipFile(archive) as bundle:
            for entry in bundle.infolist():
                if not (root / entry.filename).resolve().is_relative_to(root):
                    raise SystemExit("Unsafe archive path")
            bundle.extractall(root)
        checkout = root / archive.stem
        subprocess.run([sys.executable, "tools/verify_bundle.py"], cwd=checkout, check=True)
        completed = subprocess.run(
            [sys.executable, "workbench.py", "--store", str(root / "runs"), "run",
             "demo.experiment", "--params", '{"steps":3,"seed":7,"delay":0}'],
            cwd=checkout, check=True, capture_output=True, text=True)
        record = json.loads(completed.stdout)
        if (record["status"] != "succeeded" or record["result"]["total"] != 42
                or record["result"]["demo"] is not True):
            raise SystemExit("Extracted demo failed")
    print("Archive checksum, extracted manifest and demo verified")


if __name__ == "__main__":
    main()
