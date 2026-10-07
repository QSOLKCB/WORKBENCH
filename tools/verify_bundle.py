#!/usr/bin/env python3
"""Verify extracted bundle files against MANIFEST.sha256; no dependencies."""
import hashlib
from pathlib import Path
import sys
from build_bundle import source_files

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
checked = 0
seen = set()
for line in (root / "MANIFEST.sha256").read_text().splitlines():
    expected, relative = line.split("  ", 1)
    if relative in seen:
        raise SystemExit(f"Duplicate manifest entry: {relative}")
    seen.add(relative)
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise SystemExit(f"Missing or unsafe file: {relative}")
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"Checksum mismatch: {relative}")
    checked += 1
actual_files = {path.relative_to(root).as_posix() for path in source_files(root)}
if seen != actual_files:
    raise SystemExit(f"Manifest coverage mismatch: {sorted(seen ^ actual_files)}")
print(f"Verified {checked} files against MANIFEST.sha256")
