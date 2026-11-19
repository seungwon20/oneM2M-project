from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

import httpx
from dotenv import dotenv_values


RESOURCE_NAMES = {
    "FCNT_DEVICE1_RI": "Device1",
    "FCNT_DEVICE2_RI": "Device2",
    "FCNT_DEVICE3_RI": "Device3",
    "FCNT_DEVICE4_RI": "Device4",
    "FCNT_DEVICE5_RI": "Device5",
    "FCNT_RISK_RI": "Device6",
}
REQUIRED_SETTINGS = (
    "CSE_BASE_URL",
    "CSE_BASE_NAME",
    "CSE_RVI",
    "AE_NAME",
    "AE_ID",
    *RESOURCE_NAMES,
    "TINYIOT_SERVER_TYPE",
    "TINYIOT_SERVER_IP",
    "TINYIOT_SERVER_PORT",
    "TINYIOT_CSE_BASE_NAME",
    "TINYIOT_CSE_BASE_RI",
    "TINYIOT_CSE_BASE_SP_ID",
    "AI_AE_HOST",
    "AI_AE_PORT",
)
PLACEHOLDER_PREFIXES = (
    "YOUR_",
    "PLACEHOLDER",
    "AUTO_FROM_",
    "REPLACE_",
    "CHANGE_",
    "CHANGEME",
    "TODO",
    "TBD",
)


def package_root() -> Path:
    override = os.environ.get("MEC_PACKAGE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parents[2]
    return Path(__file__).resolve().parents[2]


def read_seed_settings(seed_db: Path) -> dict[str, str]:
    if not seed_db.is_file():
        raise FileNotFoundError(f"Seed database not found: {seed_db}")
    try:
        connection = sqlite3.connect(f"file:{seed_db.as_posix()}?mode=ro", uri=True)
        try:
            bases = connection.execute(
                "SELECT g.rn, g.ri FROM general g "
                "JOIN cb ON cb.id = g.id WHERE g.ty = 5"
            ).fetchall()
            if len(bases) != 1:
                raise ValueError("Seed database must contain exactly one CSE Base.")
            base_name, base_ri = bases[0]
            if not all((base_name, base_ri)):
                raise ValueError("Seed database CSE Base settings are incomplete.")

            settings = {
                "CSE_BASE_NAME": base_name,
                "TINYIOT_CSE_BASE_NAME": base_name,
                "TINYIOT_CSE_BASE_RI": base_ri,
            }
            for key, resource_name in RESOURCE_NAMES.items():
                rows = connection.execute(
                    "SELECT ri FROM general WHERE rn = ? AND ty = 28",
                    (resource_name,),
                ).fetchall()
                if len(rows) != 1 or not rows[0][0]:
                    raise ValueError(
                        f"Seed database must contain exactly one {resource_name} FlexContainer."
                    )
                settings[key] = rows[0][0]
            return settings
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise ValueError(f"Cannot read package seed database: {exc}") from exc


def _read_build_info(root: Path) -> dict[str, str]:
    info_path = root / "config" / "build-info.json"
    if not info_path.is_file():
        raise FileNotFoundError(f"Package build metadata not found: {info_path}")
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Package build metadata is invalid JSON.") from exc
    rvi = info.get("cse_rvi")
    if not isinstance(rvi, str) or not rvi:
        raise ValueError("Package build metadata does not contain CSE_RVI.")
    sp_id = info.get("tinyiot_cse_base_sp_id")
    if not isinstance(sp_id, str) or not sp_id:
        raise ValueError("Package build metadata does not contain the TinyIoT SP ID.")
    return {"CSE_RVI": rvi, "TINYIOT_CSE_BASE_SP_ID": sp_id}


def configure_mec(root: Path) -> None:
    config_dir = root / "config"
    env_path = config_dir / ".env"
    template_path = config_dir / ".env.example"
    if env_path.exists():
        raise FileExistsError("config/.env already exists; it was not overwritten.")
    if not template_path.is_file():
        raise FileNotFoundError(f"Configuration template not found: {template_path}")

    generated = read_seed_settings(root / "data" / "seed.db")
    generated.update(_read_build_info(root))
    lines: list[str] = []
    for line in template_path.read_text(encoding="utf-8").splitlines():
        key, separator, _ = line.partition("=")
        key = key.strip()
        if separator and key in generated:
            lines.append(f"{key}={generated[key]}")
        else:
            lines.append(line)
    if set(generated) - {
        line.partition("=")[0].strip()
        for line in lines
        if "=" in line and not line.lstrip().startswith("#")
    }:
        raise ValueError("Configuration template is missing generated settings.")

    config_dir.mkdir(parents=True, exist_ok=True)
    temp_path = env_path.with_name(".env.tmp")
    temp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temp_path.replace(env_path)
    print("Created config/.env from the bundled seed. Set AE_ID and TINYIOT_SERVER_IP before starting.")


def _load_settings(root: Path) -> dict[str, str]:
    env_path = root / "config" / ".env"
    if not env_path.is_file():
        raise FileNotFoundError("config/.env is missing; run ./scripts/configure-mec first.")
    parsed = dotenv_values(env_path)
    return {key: value.strip() for key, value in parsed.items() if value is not None}


def _port(settings: dict[str, str], key: str) -> int:
    try:
        value = int(settings[key])
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer from 1 to 65535.") from exc
    if not 1 <= value <= 65535:
        raise ValueError(f"{key} must be an integer from 1 to 65535.")
    return value


def validate_settings(root: Path, settings: dict[str, str]) -> None:
    missing = [key for key in REQUIRED_SETTINGS if not settings.get(key, "").strip()]
    placeholders = [
        key
        for key in REQUIRED_SETTINGS
        if settings.get(key, "").strip().upper().startswith(PLACEHOLDER_PREFIXES)
    ]
    if missing:
        raise ValueError("Missing package setting(s): " + ", ".join(missing))
    if placeholders:
        raise ValueError(
            "Replace package placeholder setting(s): " + ", ".join(placeholders)
        )

    seed_settings = read_seed_settings(root / "data" / "seed.db")
    build_info = _read_build_info(root)
    if settings["TINYIOT_SERVER_TYPE"].lower() != "mn":
        raise ValueError("TINYIOT_SERVER_TYPE must be 'mn'.")
    try:
        address = ipaddress.ip_address(settings["TINYIOT_SERVER_IP"])
    except ValueError as exc:
        raise ValueError("TINYIOT_SERVER_IP must be a reachable IPv4 address.") from exc
    if address.version != 4:
        raise ValueError("TINYIOT_SERVER_IP must be a reachable IPv4 address.")

    server_port = _port(settings, "TINYIOT_SERVER_PORT")
    _port(settings, "AI_AE_PORT")
    expected_url = f"http://127.0.0.1:{server_port}"
    if settings["CSE_BASE_URL"].rstrip("/") != expected_url:
        raise ValueError("CSE_BASE_URL must use 127.0.0.1 and TINYIOT_SERVER_PORT.")
    if settings["CSE_RVI"] != build_info["CSE_RVI"]:
        raise ValueError("CSE_RVI does not match the TinyIoT binary in this package.")

    for key in (
        "CSE_BASE_NAME",
        "TINYIOT_CSE_BASE_NAME",
        "TINYIOT_CSE_BASE_RI",
        *RESOURCE_NAMES,
    ):
        if settings[key] != seed_settings[key]:
            raise ValueError(f"{key} does not match the bundled seed database.")
    if settings["TINYIOT_CSE_BASE_SP_ID"] != build_info["TINYIOT_CSE_BASE_SP_ID"]:
        raise ValueError("TINYIOT_CSE_BASE_SP_ID does not match the TinyIoT binary.")


def _service_paths(root: Path, service: str) -> tuple[Path, Path, Path]:
    if service == "mn-cse":
        executable = root / "bin" / "tinyiot-mn-cse"
    else:
        executable = root / "bin" / "ai-ae" / "ai-ae"
    pid_file = root / "runtime" / "pid" / f"{service}.pid"
    log_file = root / "runtime" / "logs" / f"{service}.log"
    return executable, pid_file, log_file


def _process_running(pid_file: Path, executable: Path) -> bool:
    if not pid_file.is_file():
        return False
    try:
        pid = int(pid_file.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        pid_file.unlink(missing_ok=True)
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        return False
    except PermissionError as exc:
        raise RuntimeError(f"Cannot inspect process recorded in {pid_file.name}.") from exc
    try:
        running_executable = Path(f"/proc/{pid}/exe").resolve()
    except OSError as exc:
        raise RuntimeError(f"Cannot verify process recorded in {pid_file.name}.") from exc
    if running_executable != executable.resolve():
        raise RuntimeError(
            f"{pid_file.name} points to a different process; refusing to signal it."
        )
    return True


def _launch(
    executable: Path,
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    pid_file: Path,
    log_file: Path,
) -> None:
    if not executable.is_file():
        raise FileNotFoundError(f"Package executable not found: {executable}")
    log_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("ab") as output:
        process = subprocess.Popen(
            [str(executable), *args],
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            close_fds=True,
            start_new_session=True,
        )
    pid_file.write_text(f"{process.pid}\n", encoding="ascii")


def _check_cse(settings: dict[str, str]) -> bool:
    url = (
        settings["CSE_BASE_URL"].rstrip("/")
        + "/"
        + quote(settings["CSE_BASE_NAME"], safe="")
        + "?rcn=1"
    )
    headers = {
        "Accept": "application/json",
        "X-M2M-Origin": settings["AE_ID"],
        "X-M2M-RI": "mec-package-healthcheck",
        "X-M2M-RVI": settings["CSE_RVI"],
    }
    try:
        response = httpx.get(url, headers=headers, timeout=1.5, trust_env=False)
    except httpx.HTTPError:
        return False
    return response.status_code == 200 and response.headers.get("X-M2M-RSC") == "2000"


def _check_ai(settings: dict[str, str]) -> bool:
    url = f"http://127.0.0.1:{settings['AI_AE_PORT']}/health"
    try:
        response = httpx.get(url, timeout=1.5, trust_env=False)
    except httpx.HTTPError:
        return False
    if response.status_code != 200:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("status") == "ok"


def _wait_for_service(
    name: str,
    pid_file: Path,
    executable: Path,
    check,
    timeout: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _process_running(pid_file, executable):
            raise RuntimeError(f"{name} exited before becoming healthy; inspect its log.")
        if check():
            return
        time.sleep(0.5)
    raise RuntimeError(f"{name} did not become healthy within {timeout:g} seconds.")


def _terminate(root: Path, service: str, timeout: float = 10.0) -> bool:
    executable, pid_file, _ = _service_paths(root, service)
    if not _process_running(pid_file, executable):
        return False
    pid = int(pid_file.read_text(encoding="ascii").strip())
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pid_file.unlink(missing_ok=True)
            return True
        time.sleep(0.2)
    os.kill(pid, signal.SIGKILL)
    pid_file.unlink(missing_ok=True)
    return True


def start_mec(root: Path) -> None:
    settings = _load_settings(root)
    validate_settings(root, settings)
    services = ("mn-cse", "ai-ae")
    for service in services:
        executable, pid_file, _ = _service_paths(root, service)
        if _process_running(pid_file, executable):
            raise RuntimeError(f"{service} is already running.")

    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    runtime_db = runtime / "data.db"
    if not runtime_db.exists():
        temporary_db = runtime / "data.db.tmp"
        shutil.copy2(root / "data" / "seed.db", temporary_db)
        temporary_db.replace(runtime_db)
    shutil.copytree(
        root / "share" / "sdt_definitions",
        runtime / "sdt_definitions",
        dirs_exist_ok=True,
    )

    child_env = os.environ.copy()
    child_env.update(settings)
    server, server_pid, server_log = _service_paths(root, "mn-cse")
    ai_ae, ai_pid, ai_log = _service_paths(root, "ai-ae")
    try:
        _launch(
            server,
            ["-p", settings["TINYIOT_SERVER_PORT"]],
            cwd=runtime,
            env=child_env,
            pid_file=server_pid,
            log_file=server_log,
        )
        _wait_for_service("MN-CSE", server_pid, server, lambda: _check_cse(settings))

        ai_env = child_env.copy()
        ai_env["ONE_M2M_ENV_FILE"] = str(root / "config" / ".env")
        _launch(
            ai_ae,
            [],
            cwd=root,
            env=ai_env,
            pid_file=ai_pid,
            log_file=ai_log,
        )
        _wait_for_service("AI-AE", ai_pid, ai_ae, lambda: _check_ai(settings))
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        cleanup_errors = []
        for service in ("ai-ae", "mn-cse"):
            try:
                _terminate(root, service)
            except (OSError, RuntimeError) as exc:
                cleanup_errors.append(f"{service}: {exc}")
        if cleanup_errors:
            raise RuntimeError(
                "MEC startup failed and cleanup was incomplete: "
                + "; ".join(cleanup_errors)
            )
        raise
    print("MEC started: MN-CSE and AI-AE are healthy.")


def stop_mec(root: Path) -> None:
    stopped = []
    errors = []
    for service in ("ai-ae", "mn-cse"):
        try:
            if _terminate(root, service):
                stopped.append(service)
        except (OSError, RuntimeError) as exc:
            errors.append(f"{service}: {exc}")
    for service in stopped:
        print(f"Stopped {service}.")
    if errors:
        raise RuntimeError("; ".join(errors))
    if not stopped:
        print("MEC services are not running.")


def check_status(root: Path, *, verbose: bool) -> int:
    states = {}
    for service in ("mn-cse", "ai-ae"):
        executable, pid_file, _ = _service_paths(root, service)
        states[service] = _process_running(pid_file, executable)
        print(f"{service}: {'running' if states[service] else 'stopped'}")

    if not all(states.values()):
        return 1
    settings = _load_settings(root)
    cse_ok = _check_cse(settings)
    ai_ok = _check_ai(settings)
    print(f"MN-CSE health: {'ok' if cse_ok else 'failed'}")
    print(f"AI-AE health: {'ok' if ai_ok else 'failed'}")
    if verbose and not (cse_ok and ai_ok):
        print("Inspect runtime/logs/mn-cse.log and runtime/logs/ai-ae.log.")
    return 0 if cse_ok and ai_ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage the standalone MEC package.")
    parser.add_argument(
        "command",
        choices=("configure", "start", "stop", "status", "healthcheck"),
    )
    args = parser.parse_args(argv)
    root = package_root()

    try:
        if args.command == "configure":
            configure_mec(root)
            return 0
        if args.command == "start":
            start_mec(root)
            return 0
        if args.command == "stop":
            stop_mec(root)
            return 0
        return check_status(root, verbose=args.command == "healthcheck")
    except (FileNotFoundError, FileExistsError, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"MEC {args.command} failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
