#!/usr/bin/env python3
"""Run one build command and keep a bounded log plus compiler samples."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workdir", type=Path, required=True)
    p.add_argument("--stage", required=True)
    p.add_argument("command", nargs=argparse.REMAINDER)
    a = p.parse_args()
    command = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not command:
        p.error("command required")
    evidence = a.workdir / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    log = evidence / f"{a.stage}.log"
    sample = evidence / "compiler-samples.log"
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    tune = re.compile(br"-mtune=cortex-a73")
    mcpu = re.compile(br"-mcpu=cortex-a53")
    kept = 0
    with log.open("wb") as out, sample.open("ab") as samp:
        assert proc.stdout is not None
        for line in proc.stdout:
            if kept < 8 * 1024 * 1024:
                out.write(line)
                kept += len(line)
            if tune.search(line) and mcpu.search(line):
                samp.write(line[:2000] + b"\n")
    rc = proc.wait()
    print(f"stage={a.stage} rc={rc} log_bytes={kept}", flush=True)
    return rc

if __name__ == "__main__":
    sys.exit(main())
