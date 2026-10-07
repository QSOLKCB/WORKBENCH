#!/usr/bin/env python3
"""Build a deterministic ZIP, its .zip256 checksum, and an internal manifest."""
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {"__pycache__", ".git", ".workbench", ".venv", "build", "dist"}


def source_files(root=ROOT):
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in EXCLUDED or part.endswith(".egg-info") for part in relative.parts):
            continue
        if path.suffix == ".pyc" or relative == Path("MANIFEST.sha256"):
            continue
        if path.is_symlink():
            raise ValueError(f"Unexpected symlink: {relative}")
        if path.is_file():
            yield path


def main():
    paths = list(source_files())
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT).as_posix()}" for p in paths]
    manifest = ROOT / "MANIFEST.sha256"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    archive = ROOT.parent / (ROOT.name + ".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(paths + [manifest]):
            name = ROOT.name + "/" + path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 7, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes())
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    sidecar = archive.with_suffix(".zip256")
    sidecar.write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    print(f"ZIP: {archive}\nFiles: {len(paths)+1}\nBytes: {archive.stat().st_size}\nSHA256: {checksum}\nChecksum: {sidecar}")


if __name__ == "__main__":
    main()
