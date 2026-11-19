#!/usr/bin/env python3
"""Run TinyIoT using an isolated runtime copy of its seed database."""

from __future__ import annotations

import shutil
import subprocess
import sys
import os
from pathlib import Path


MN_CSE_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = Path(os.environ.get("TINYIOT_RUNTIME_DIR", str(MN_CSE_DIR / "runtime"))).expanduser().resolve()
SEED_DB = MN_CSE_DIR / "data.db"
SERVER = MN_CSE_DIR / "server"
SDT_SOURCE = MN_CSE_DIR / "sdt_definitions"


def main() -> int:
    if not SERVER.is_file():
        print("MN-CSE server binary is missing; run scripts/build.py first.", file=sys.stderr)
        return 1
    if not SEED_DB.is_file():
        print("MN-CSE seed database is missing.", file=sys.stderr)
        return 1
    if not SDT_SOURCE.is_dir():
        print("MN-CSE SDT definitions directory is missing.", file=sys.stderr)
        return 1

    RUNTIME_DIR.mkdir(exist_ok=True)
    runtime_db = RUNTIME_DIR / "data.db"
    if not runtime_db.exists():
        shutil.copy2(SEED_DB, runtime_db)
        print("Initialized runtime DB from the bundled seed DB.")
    else:
        print("Using existing runtime DB; seed DB was not copied over it.")

    runtime_sdt = RUNTIME_DIR / "sdt_definitions"
    shutil.copytree(SDT_SOURCE, runtime_sdt, dirs_exist_ok=True)
    print(f"Starting MN-CSE on the configured port; runtime data is under {RUNTIME_DIR}.")
    try:
        return subprocess.run([str(SERVER)], cwd=RUNTIME_DIR, check=False).returncode
    except OSError as exc:
        print(f"Could not start MN-CSE: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
