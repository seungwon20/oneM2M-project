#!/usr/bin/env python3
"""Run TinyIoT IN-CSE with its own persistent runtime directory."""

from __future__ import annotations

import shutil
import subprocess
import sys
import os
import re
from pathlib import Path


IN_CSE_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = Path(os.environ.get("IN_CSE_RUNTIME_DIR", str(IN_CSE_DIR / "runtime"))).expanduser().resolve()
SERVER = IN_CSE_DIR / "server"
SDT_SOURCE = IN_CSE_DIR / "sdt_definitions"
PROJECT_ROOT = IN_CSE_DIR.parent


def load_settings() -> dict[str, str]:
    path = Path(os.environ.get("IN_CSE_ENV_FILE", str(PROJECT_ROOT / ".env"))).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"IN-CSE environment file not found: {path}")
    settings = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"{path.name}:{line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"{path.name}:{line_number}: invalid environment variable name")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        settings[key] = value
    for key in ("IN_CSE_SERVER_IP", "IN_CSE_SERVER_PORT"):
        if not settings.get(key):
            raise ValueError(f"Missing required setting: {key}")
    try:
        port = int(settings["IN_CSE_SERVER_PORT"])
    except ValueError as exc:
        raise ValueError("IN_CSE_SERVER_PORT must be an integer from 1 to 65535.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("IN_CSE_SERVER_PORT must be an integer from 1 to 65535.")
    return settings


def main() -> int:
    if not SERVER.is_file():
        print("IN-CSE server binary is missing; run scripts/build.py first.", file=sys.stderr)
        return 1

    try:
        settings = load_settings()
    except (OSError, ValueError) as exc:
        print(f"IN-CSE configuration failed: {exc}", file=sys.stderr)
        return 1

    RUNTIME_DIR.mkdir(exist_ok=True)
    runtime_sdt = RUNTIME_DIR / "sdt_definitions"
    if SDT_SOURCE.is_dir():
        shutil.copytree(SDT_SOURCE, runtime_sdt, dirs_exist_ok=True)

    child_env = os.environ.copy()
    child_env.update(settings)
    print(f"Starting IN-CSE on configured port; runtime data is under {RUNTIME_DIR}.")
    try:
        return subprocess.run(
            [str(SERVER), "-p", settings["IN_CSE_SERVER_PORT"]],
            cwd=RUNTIME_DIR,
            env=child_env,
            check=False,
        ).returncode
    except OSError as exc:
        print(f"Could not start IN-CSE: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
