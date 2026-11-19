#!/usr/bin/env python3
"""Configure and build the TinyIoT IN-CSE from the project-root .env."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import argparse
from pathlib import Path


IN_CSE_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = IN_CSE_DIR.parent
ENV_PATH = PROJECT_ROOT / ".env"

REQUIRED_ENV = (
    "IN_CSE_SERVER_IP",
    "IN_CSE_SERVER_PORT",
    "IN_CSE_CSE_BASE_NAME",
    "IN_CSE_CSE_BASE_RI",
    "IN_CSE_CSE_BASE_SP_ID",
    "IN_CSE_RVI",
    "IN_CSE_ADMIN_AE_ID",
    "IN_CSE_ALLOWED_REMOTE_CSE_ID",
)


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
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
        values[key] = value
    return values


def validate_environment(env: dict[str, str]) -> str:
    missing = [key for key in REQUIRED_ENV if not env.get(key, "").strip()]
    if missing:
        raise ValueError("Missing required .env setting(s): " + ", ".join(missing))
    placeholders = [
        key for key in REQUIRED_ENV
        if env[key].strip().upper().startswith(
            ("YOUR_", "PLACEHOLDER", "REPLACE_", "CHANGE_", "CHANGEME", "TODO", "TBD")
        )
    ]
    if placeholders:
        raise ValueError("Replace placeholder .env setting(s): " + ", ".join(placeholders))
    try:
        port = int(env["IN_CSE_SERVER_PORT"])
    except ValueError as exc:
        raise ValueError("IN_CSE_SERVER_PORT must be an integer from 1 to 65535.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("IN_CSE_SERVER_PORT must be an integer from 1 to 65535.")
    if env["IN_CSE_RVI"] not in {"1", "2", "2a", "3", "4", "5"}:
        raise ValueError("IN_CSE_RVI must be one of 1, 2, 2a, 3, 4, or 5.")
    for key in ("IN_CSE_SERVER_IP", "IN_CSE_CSE_BASE_NAME", "IN_CSE_CSE_BASE_RI",
                "IN_CSE_CSE_BASE_SP_ID", "IN_CSE_ADMIN_AE_ID"):
        if any(character in env[key] for character in ('"', "\n", "\r")):
            raise ValueError(f"{key} contains an unsupported character.")
    if any(character in env["IN_CSE_SERVER_IP"] for character in ("/", ":", " ", "\t")):
        raise ValueError("IN_CSE_SERVER_IP must be a host name or IPv4 address without a scheme or port.")
    for key in ("IN_CSE_CSE_BASE_NAME", "IN_CSE_CSE_BASE_RI"):
        if "/" in env[key] or not env[key]:
            raise ValueError(f"{key} must be a non-empty single path segment.")
    return env["IN_CSE_RVI"]


def generate_config(env: dict[str, str], rvi: str) -> None:
    definitions = {
        "SERVER_TYPE": "IN_CSE",
        "SERVER_IP": json.dumps(env["IN_CSE_SERVER_IP"]),
        "SERVER_PORT": json.dumps(env["IN_CSE_SERVER_PORT"]),
        "CSE_BASE_NAME": json.dumps(env["IN_CSE_CSE_BASE_NAME"]),
        "CSE_BASE_RI": json.dumps(env["IN_CSE_CSE_BASE_RI"]),
        "CSE_BASE_SP_ID": json.dumps(env["IN_CSE_CSE_BASE_SP_ID"]),
        "CSE_RVI": f"RVI_{rvi.upper()}",
        "REMOTE_CSE_ID": json.dumps(""),
        "REMOTE_CSE_NAME": json.dumps(""),
        "REMOTE_CSE_HOST": json.dumps(""),
        "REMOTE_CSE_SP_ID": json.dumps(""),
        "REMOTE_CSE_PORT": "0",
        "DB_SQLITE": "1",
        "DB_POSTGRESQL": "1",
        "DB_TYPE": "DB_SQLITE",
        "ADMIN_AE_ID": json.dumps(env["IN_CSE_ADMIN_AE_ID"]),
        "DEFAULT_ACOP": "ACOP_CREATE",
        "ALLOWED_REMOTE_CSE_ID": json.dumps(env["IN_CSE_ALLOWED_REMOTE_CSE_ID"]),
        "MONO_THREAD": "0",
        "MAX_PAYLOAD_SIZE": "65536",
        "MAX_URI_SIZE": "1024",
        "MAX_ATTRIBUTE_SIZE": "4096",
        "MAX_TREE_VIEWER_SIZE": "65536",
        "DEFAULT_EXPIRE_TIME": "-63072000",
        "SOCKET_TIMEOUT": "3",
        "MAX_URI_LENGTH": "1024",
        "DEFAULT_MAX_NR_INSTANCES": "1000",
        "DEFAULT_MAX_BYTE_SIZE": "65536",
        "DEFAULT_MAX_INSTANCE_AGE": "157680000",
        "ALLOW_CIN_RN": "true",
        "DEFAULT_CONSISTENCY_POLICY": "CSY_ABANDON_MEMBER",
        "DEFAULT_DISCOVERY_LIMIT": "150",
        "LOG_LEVEL": "LOG_LEVEL_INFO",
        "LOG_BUFFER_SIZE": "MAX_PAYLOAD_SIZE",
        "DEFAULT_DISCOVERY_SORT": "SORT_DESC",
    }
    template = IN_CSE_DIR / "config.h.in"
    text = template.read_text(encoding="utf-8")
    for macro, value in definitions.items():
        text, replacements = re.subn(
            rf"^#undef {re.escape(macro)}\s*$",
            f"#define {macro} {value}",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if replacements != 1:
            raise ValueError(f"IN-CSE/config.h.in must contain exactly one #undef for {macro}.")
    (IN_CSE_DIR / "config.h").write_text(text, encoding="utf-8")


def run(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    env = os.environ.copy()
    env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    subprocess.run(command, cwd=IN_CSE_DIR, check=True, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ENV_PATH,
                        help="environment file (defaults to the project-root .env)")
    args = parser.parse_args()
    try:
        env = parse_env(args.env_file)
        rvi = validate_environment(env)
        missing = [command for command in ("make", "gcc", "pkg-config") if shutil.which(command) is None]
        if missing:
            raise RuntimeError("Missing build tool(s): " + ", ".join(missing))
        generate_config(env, rvi)
        run(["make", "clean"])
        run(["make", "-j2"])
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"IN-CSE build failed: {exc}", file=sys.stderr)
        return 1
    print("IN-CSE build completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
