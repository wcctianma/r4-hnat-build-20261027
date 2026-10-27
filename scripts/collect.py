#!/usr/bin/env python3
"""Collect firmware names, hashes, and a short manifest. No secrets."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

WANTED = (
    "sysupgrade.itb",
    "sdcard.img.gz",
    "recovery.itb",
    "sha256sums",
    "config.buildinfo",
    "feeds.buildinfo",
    "version.buildinfo",
)

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workdir", type=Path, required=True)
    a = p.parse_args()
    ow = a.workdir / "openwrt"
    out = a.workdir / "delivery"
    out.mkdir(parents=True, exist_ok=True)
    evidence = a.workdir / "evidence"
    evidence.mkdir(exist_ok=True)
    bin_dir = ow / "bin"
    files = []
    if bin_dir.is_dir():
        for path in bin_dir.rglob("*"):
            if path.is_file() and (path.name in WANTED or path.name.endswith(WANTED)):
                files.append(path)
    manifest = []
    for path in sorted(files):
        manifest.append({
            "name": path.name,
            "rel": str(path.relative_to(ow)),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    (evidence / "artifacts.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if files:
        with tarfile.open(out / "firmware.tar.xz", "w:xz") as tar:
            for path in files:
                tar.add(path, arcname=str(path.relative_to(ow)))
    else:
        (out / "BUILD-INCOMPLETE.txt").write_text("No firmware outputs yet.\n")
    for name in ("compiler-samples.log", "artifacts.json", "disk.txt", "missing-packages.txt", "providers.json"):
        src = evidence / name
        if src.is_file():
            (out / name).write_bytes(src.read_bytes())
    print(json.dumps({"files": len(manifest)}, indent=2))

if __name__ == "__main__":
    main()
