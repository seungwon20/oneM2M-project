#!/usr/bin/env python3
"""Configure and build the TinyIoT MN-CSE from the project-root .env."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path


MN_CSE_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = MN_CSE_DIR.parent
ENV_PATH = PROJECT_ROOT / ".env"
EXAMPLE_PATH = PROJECT_ROOT / ".env.example"
SEED_DB = MN_CSE_DIR / "data.db"

REQUIRED_ENV = (
    "TINYIOT_SERVER_TYPE",
    "TINYIOT_SERVER_IP",
    "TINYIOT_SERVER_PORT",
    "TINYIOT_CSE_BASE_NAME",
    "TINYIOT_CSE_BASE_RI",
    "TINYIOT_CSE_BASE_SP_ID",
    "CSE_BASE_URL",
    "CSE_BASE_NAME",
    "CSE_RVI",
    "AE_ID",
    "FCNT_DEVICE1_RI",
    "FCNT_DEVICE2_RI",
    "FCNT_DEVICE3_RI",
    "FCNT_DEVICE4_RI",
    "FCNT_DEVICE5_RI",
    "FCNT_RISK_RI",
)

RESOURCE_CONFIG = (
    ("Device1", "FCNT_DEVICE1_RI", {"zone_person_count", "total_person_count", "received_at"}),
    ("Device2", "FCNT_DEVICE2_RI", {"weight_kg", "received_at"}),
    ("Device3", "FCNT_DEVICE3_RI", {"beam_blocked", "received_at"}),
    ("Device4", "FCNT_DEVICE4_RI", {"is_rotating", "speed_rpm", "received_at"}),
    ("Device5", "FCNT_DEVICE5_RI", {"distance_cm", "received_at"}),
    ("Device6", "FCNT_RISK_RI", {"risk_level", "speed_rpm", "distance_cm", "evaluated_at"}),
)


def seed_base_ri(base_name: str) -> str:
    if not SEED_DB.is_file():
        raise FileNotFoundError(f"Seed database not found: {SEED_DB}")
    try:
        connection = sqlite3.connect(f"file:{SEED_DB.as_posix()}?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT ri FROM general WHERE rn = ? AND ty = 5",
                (base_name,),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise ValueError(f"Cannot read CSE Base settings from seed DB: {exc}") from exc
    if not row or not row[0]:
        raise ValueError("Seed DB does not contain the configured CSE Base RI.")
    return row[0]


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
        key = key.strip()
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"{path.name}:{line_number}: invalid environment variable name")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def initialize_local_env() -> None:
    base_ri = seed_base_ri("TinyIoT")
    defaults = {
        "CSE_BASE_URL": "http://127.0.0.1:3000",
        "CSE_BASE_NAME": "TinyIoT",
        "CSE_RVI": "3",
        "TINYIOT_SERVER_TYPE": "mn",
        "TINYIOT_SERVER_IP": "127.0.0.1",
        "TINYIOT_SERVER_PORT": "3000",
        "TINYIOT_CSE_BASE_NAME": "TinyIoT",
        "TINYIOT_CSE_BASE_RI": base_ri,
    }
    if not ENV_PATH.exists():
        if not EXAMPLE_PATH.is_file():
            raise FileNotFoundError(f"Environment template not found: {EXAMPLE_PATH}")
        ENV_PATH.write_text(EXAMPLE_PATH.read_text(encoding="utf-8-sig"), encoding="utf-8")

    lines = ENV_PATH.read_text(encoding="utf-8-sig").splitlines()
    seen: set[str] = set()
    updated: list[str] = []
    for line in lines:
        match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match and match.group(1) in defaults:
            key = match.group(1)
            updated.append(f"{key}={defaults[key]}")
            seen.add(key)
        else:
            updated.append(line)
    for key, value in defaults.items():
        if key not in seen:
            updated.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(updated) + "\n", encoding="utf-8")
    print("Local integration settings updated in project-root .env; values were not printed.")


def validate_environment(env: dict[str, str]) -> str:
    missing = [key for key in REQUIRED_ENV if not env.get(key, "").strip()]
    if missing:
        raise ValueError("Missing required .env setting(s): " + ", ".join(missing))

    placeholders = [
        key for key in REQUIRED_ENV
        if env[key].strip().startswith("YOUR_")
    ]
    if placeholders:
        raise ValueError(
            "Replace placeholder .env setting(s) before building: "
            + ", ".join(placeholders)
        )

    if env["TINYIOT_SERVER_TYPE"].lower() != "mn":
        raise ValueError("TINYIOT_SERVER_TYPE must be 'mn' for this single-MEC setup.")
    try:
        ipaddress.IPv4Address(env["TINYIOT_SERVER_IP"])
    except ipaddress.AddressValueError as exc:
        raise ValueError("TINYIOT_SERVER_IP must be a valid IPv4 address.") from exc
    try:
        port = int(env["TINYIOT_SERVER_PORT"])
    except ValueError as exc:
        raise ValueError("TINYIOT_SERVER_PORT must be an integer from 1 to 65535.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("TINYIOT_SERVER_PORT must be an integer from 1 to 65535.")

    if env["CSE_BASE_URL"].rstrip("/") != "http://127.0.0.1:3000":
        raise ValueError("CSE_BASE_URL must be http://127.0.0.1:3000 for this local integration.")
    if env["CSE_BASE_NAME"] != env["TINYIOT_CSE_BASE_NAME"]:
        raise ValueError("CSE_BASE_NAME and TINYIOT_CSE_BASE_NAME must match.")
    if env["CSE_RVI"] not in {"1", "2", "2a", "3", "4", "5"}:
        raise ValueError("CSE_RVI must be one of 1, 2, 2a, 3, 4, or 5.")
    if not env["TINYIOT_CSE_BASE_SP_ID"].strip():
        raise ValueError("TINYIOT_CSE_BASE_SP_ID must not be empty.")
    return env["CSE_RVI"]


def validate_seed_db(env: dict[str, str]) -> None:
    if not SEED_DB.is_file():
        raise ValueError(f"Seed database not found: {SEED_DB}")
    try:
        connection = sqlite3.connect(f"file:{SEED_DB.as_posix()}?mode=ro", uri=True)
        try:
            base_rows = connection.execute(
                "SELECT ri FROM general WHERE rn = ? AND ty = 5",
                (env["TINYIOT_CSE_BASE_NAME"],),
            ).fetchall()
            if len(base_rows) != 1 or base_rows[0][0] != env["TINYIOT_CSE_BASE_RI"]:
                raise ValueError("Seed DB CSE Base Name/RI does not match the .env configuration.")

            for resource_name, env_key, expected_fields in RESOURCE_CONFIG:
                rows = connection.execute(
                    "SELECT g.ri, f.custom_attrs FROM general g "
                    "JOIN fcnt f ON f.id = g.id WHERE g.rn = ? AND g.ty = 28",
                    (resource_name,),
                ).fetchall()
                if len(rows) != 1:
                    raise ValueError(f"Seed DB must contain exactly one {resource_name} FlexContainer.")
                resource_id, custom_attrs = rows[0]
                if resource_id != env[env_key]:
                    raise ValueError(
                        f".env {env_key} does not match the existing {resource_name} resource ID."
                    )
                try:
                    actual_fields = set(json.loads(custom_attrs or "{}"))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Seed DB {resource_name} custom attributes are invalid JSON.") from exc
                if actual_fields != expected_fields:
                    raise ValueError(
                        f"Seed DB {resource_name} fields do not match the AI-AE payload schema."
                    )
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise ValueError(f"Cannot validate TinyIoT seed DB: {exc}") from exc
    print("Seed DB Base and Device1-Device6 Resource IDs/schemas match AI-AE configuration.")


def require_commands(*commands: str) -> None:
    native_path = "/usr/bin:/bin:/usr/sbin:/sbin"
    missing = [
        command for command in commands
        if shutil.which(command, path=native_path) is None
    ]
    if missing:
        raise RuntimeError(
            "Missing build tool(s): " + ", ".join(missing)
            + ". Run this script in the supported Linux/WSL build environment."
        )


def generate_build_files(env: dict[str, str], rvi: str) -> None:
    definitions = {
        "SERVER_TYPE": "MN_CSE",
        "SERVER_IP": json.dumps(env["TINYIOT_SERVER_IP"]),
        "SERVER_PORT": json.dumps(env["TINYIOT_SERVER_PORT"]),
        "CSE_BASE_NAME": json.dumps(env["TINYIOT_CSE_BASE_NAME"]),
        "CSE_BASE_RI": json.dumps(env["TINYIOT_CSE_BASE_RI"]),
        "CSE_BASE_SP_ID": json.dumps(env["TINYIOT_CSE_BASE_SP_ID"]),
        "CSE_RVI": f"RVI_{rvi}",
        "REMOTE_CSE_ID": json.dumps(""),
        "REMOTE_CSE_NAME": json.dumps(""),
        "REMOTE_CSE_HOST": json.dumps(""),
        "REMOTE_CSE_SP_ID": json.dumps(""),
        "REMOTE_CSE_PORT": "0",
        "DB_SQLITE": "1",
        "DB_POSTGRESQL": "1",
        "DB_TYPE": "DB_SQLITE",
        "ADMIN_AE_ID": json.dumps("CAdmin"),
        "DEFAULT_ACOP": "ACOP_CREATE",
        "ALLOWED_REMOTE_CSE_ID": json.dumps(
            env.get("ALLOWED_REMOTE_CSE_ID")
            or f'{env.get("REMOTE_CSE_ID", "")},/{env["TINYIOT_CSE_BASE_RI"]}'.lstrip(",")
        ),
        "MONO_THREAD": "0",
        "MAX_PAYLOAD_SIZE": "65536",
        "MAX_URI_SIZE": "1024",
        "MAX_ATTRIBUTE_SIZE": "4096",
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
    template = MN_CSE_DIR / "config.h.in"
    if not template.is_file():
        raise ValueError(f"TinyIoT config template not found: {template.name}")
    config_text = template.read_text(encoding="utf-8")
    for macro, value in definitions.items():
        pattern = rf"^#undef {re.escape(macro)}\s*$"
        config_text, replacements = re.subn(
            pattern, f"#define {macro} {value}", config_text, count=1, flags=re.MULTILINE
        )
        if replacements != 1:
            raise ValueError(f"config.h.in must contain exactly one #undef for {macro}.")

    generated_header = MN_CSE_DIR / "config.h"
    generated_header.write_text(config_text, encoding="utf-8")
    makefile_template = MN_CSE_DIR / "Makefile.in"
    if not makefile_template.is_file():
        raise ValueError(f"TinyIoT make template not found: {makefile_template.name}")
    generated_makefile = MN_CSE_DIR / "Makefile"
    shutil.copyfile(makefile_template, generated_makefile)
    generated_time = time.time() - 5
    os.utime(generated_header, (generated_time, generated_time))
    os.utime(generated_makefile, (generated_time, generated_time))
    print("Generated config.h and Makefile from project-root .env and tracked templates.")


def run(command: list[str], *, cwd: Path) -> None:
    print("+ " + " ".join(command), flush=True)
    env = os.environ.copy()
    env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    subprocess.run(command, cwd=cwd, check=True, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--init-local-env",
        action="store_true",
        help="set known local integration values in .env without changing credentials or Resource IDs",
    )
    args = parser.parse_args()

    try:
        if args.init_local_env:
            initialize_local_env()
        env = parse_env(ENV_PATH)
        rvi = validate_environment(env)
        validate_seed_db(env)
        require_commands("make", "gcc", "pkg-config")
        generate_build_files(env, rvi)
        run(["make", "clean"], cwd=MN_CSE_DIR)
        run(["make", "-j2"], cwd=MN_CSE_DIR)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"MN-CSE build failed: {exc}", file=sys.stderr)
        return 1

    print("MN-CSE build completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
