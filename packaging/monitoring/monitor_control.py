from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


PACKAGE_SOURCE = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_SOURCE.parents[1]


def package_root() -> Path:
    override = os.environ.get("MONITORING_PACKAGE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parents[2]
    return Path(__file__).resolve().parents[2]


def _build_info(root: Path) -> dict[str, Any]:
    path = root / "config" / "build-info.json"
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Monitoring package build metadata is missing or invalid.") from exc
    required = ("in_cse_base_name", "in_cse_id", "in_cse_rvi", "mn_cse_id")
    missing = [key for key in required if not isinstance(info.get(key), str) or not info[key]]
    if missing:
        raise ValueError("Monitoring package metadata is missing: " + ", ".join(missing))
    devices = info.get("mn_device_resource_ids")
    expected_devices = tuple(f"Device{i}" for i in range(1, 7))
    if not isinstance(devices, dict) or any(
        not isinstance(devices.get(device), str) or not devices[device]
        for device in expected_devices
    ):
        raise ValueError("Monitoring package metadata is missing Device1-Device6 Resource IDs.")
    return info


def configure(root: Path) -> None:
    env_path = root / "config" / ".env"
    template = root / "config" / ".env.example"
    if env_path.exists():
        raise FileExistsError("config/.env already exists; it was not overwritten.")
    if not template.is_file():
        raise FileNotFoundError(f"Configuration template not found: {template}")
    info = _build_info(root)
    generated = {
        "PG_IN_CSE_URL": "http://127.0.0.1:3001",
        "PG_MN_CSE_ID": info["mn_cse_id"],
        "PG_IN_CSE_RVI": info["in_cse_rvi"],
    }
    generated.update({
        f"PG_MN_DEVICE{i}_RI": info["mn_device_resource_ids"][f"Device{i}"]
        for i in range(1, 7)
    })
    lines = []
    for line in template.read_text(encoding="utf-8").splitlines():
        key, separator, _ = line.partition("=")
        key = key.strip()
        lines.append(f"{key}={generated[key]}" if separator and key in generated else line)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Created config/.env. Set the Monitoring Node address, PG_IN_CSE_ORIGIN to the MEC AE_ID, and PG_INGEST_KEY.")


def _read_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError("config/.env is missing; run ./scripts/configure-monitoring first.")
    values = {}
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
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _port(settings: dict[str, str], key: str) -> int:
    try:
        value = int(settings[key])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer from 1 to 65535.") from exc
    if not 1 <= value <= 65535:
        raise ValueError(f"{key} must be an integer from 1 to 65535.")
    return value


def _settings(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    settings = _read_env(root / "config" / ".env")
    info = _build_info(root)
    required = (
        "IN_CSE_SERVER_IP", "IN_CSE_SERVER_PORT", "PG_DASHBOARD_HOST",
        "PG_DASHBOARD_PORT", "PG_DB_PATH", "PG_INGEST_KEY", "PG_IN_CSE_URL",
        "PG_MN_CSE_ID", "PG_IN_CSE_ORIGIN", "PG_IN_CSE_RVI",
        *(f"PG_MN_DEVICE{i}_RI" for i in range(1, 7)),
    )
    missing = [key for key in required if not settings.get(key, "").strip()]
    placeholders = [
        key for key in required
        if settings.get(key, "").strip().upper().startswith(
            ("YOUR_", "PLACEHOLDER", "REPLACE_", "CHANGE_", "CHANGEME", "TODO", "TBD")
        )
    ]
    if missing:
        raise ValueError("Missing package setting(s): " + ", ".join(missing))
    if placeholders:
        raise ValueError("Replace package placeholder setting(s): " + ", ".join(placeholders))
    if any(character in settings["IN_CSE_SERVER_IP"] for character in ("/", ":", " ", "\t")):
        raise ValueError("IN_CSE_SERVER_IP must be a host name or IPv4 address without a scheme or port.")
    _port(settings, "IN_CSE_SERVER_PORT")
    _port(settings, "PG_DASHBOARD_PORT")
    if settings["PG_MN_CSE_ID"].strip("/") != info["mn_cse_id"].strip("/"):
        raise ValueError("PG_MN_CSE_ID does not match the TinyIoT identifier used for this package.")
    if settings["PG_IN_CSE_RVI"] != info["in_cse_rvi"]:
        raise ValueError("PG_IN_CSE_RVI does not match the IN-CSE binary.")
    for index in range(1, 7):
        device = f"Device{index}"
        if settings[f"PG_MN_DEVICE{index}_RI"] != info["mn_device_resource_ids"][device]:
            raise ValueError(f"PG_MN_DEVICE{index}_RI does not match the bundled MEC Seed DB.")
    endpoint = urlsplit(settings["PG_IN_CSE_URL"])
    if endpoint.scheme != "http" or not endpoint.hostname or endpoint.path:
        raise ValueError("PG_IN_CSE_URL must be an HTTP origin without a path.")
    if len(settings["PG_INGEST_KEY"]) < 16:
        raise ValueError("PG_INGEST_KEY must contain at least 16 characters.")
    return settings, info


def _paths(root: Path, service: str) -> tuple[Path, Path, Path]:
    executable = (
        root / "bin" / "tinyiot-in-cse"
        if service == "in-cse"
        else root / "bin" / "dashboard" / "dashboard"
    )
    return (
        executable,
        root / "runtime" / "pid" / f"{service}.pid",
        root / "runtime" / "logs" / f"{service}.log",
    )


def _is_running(pid_file: Path, executable: Path) -> bool:
    if not pid_file.is_file():
        return False
    try:
        pid = int(pid_file.read_text(encoding="ascii").strip())
        os.kill(pid, 0)
        running = Path(f"/proc/{pid}/exe").resolve() == executable.resolve()
    except ProcessLookupError:
        running = False
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Cannot verify the process in {pid_file.name}.") from exc
    if not running:
        pid_file.unlink(missing_ok=True)
    return running


def _launch(executable: Path, args: list[str], cwd: Path, env: dict[str, str],
            pid_file: Path, log_file: Path) -> None:
    if not executable.is_file():
        raise FileNotFoundError(f"Package executable not found: {executable}")
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("ab") as output:
        process = subprocess.Popen(
            [str(executable), *args], cwd=cwd, env=env,
            stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            close_fds=True, start_new_session=True,
        )
    pid_file.write_text(f"{process.pid}\n", encoding="ascii")


def _http_ok(url: str, headers: dict[str, str], expected_rsc: str | None = None) -> bool:
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=1.5) as response:
            return response.status == 200 and (
                expected_rsc is None or response.headers.get("X-M2M-RSC") == expected_rsc
            )
    except (URLError, TimeoutError, OSError):
        return False


def _check_in_cse(settings: dict[str, str], info: dict[str, str]) -> bool:
    url = f"http://127.0.0.1:{settings['IN_CSE_SERVER_PORT']}/{quote(info['in_cse_base_name'], safe='')}?rcn=1"
    headers = {
        "Accept": "application/json",
        "X-M2M-Origin": settings["PG_IN_CSE_ORIGIN"],
        "X-M2M-RI": "monitoring-package-health",
        "X-M2M-RVI": settings["PG_IN_CSE_RVI"],
    }
    return _http_ok(url, headers, "2000")


def _check_dashboard(settings: dict[str, str]) -> bool:
    url = f"http://127.0.0.1:{settings['PG_DASHBOARD_PORT']}/health"
    return _http_ok(url, {})


def _wait(name: str, pid_file: Path, executable: Path, check, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _is_running(pid_file, executable):
            raise RuntimeError(f"{name} exited before becoming healthy; inspect its package log.")
        if check():
            return
        time.sleep(0.5)
    raise RuntimeError(f"{name} did not become healthy within {timeout:g} seconds.")


def _stop(root: Path, service: str) -> bool:
    executable, pid_file, _ = _paths(root, service)
    if not _is_running(pid_file, executable):
        return False
    pid = int(pid_file.read_text(encoding="ascii").strip())
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 10
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


def start(root: Path) -> None:
    settings, info = _settings(root)
    services = ("in-cse", "dashboard")
    for service in services:
        executable, pid_file, _ = _paths(root, service)
        if _is_running(pid_file, executable):
            raise RuntimeError(f"{service} is already running.")

    runtime = root / "runtime"
    runtime.mkdir(exist_ok=True)
    child_env = os.environ.copy()
    child_env.update(settings)
    child_env["PG_DB_PATH"] = str((root / settings["PG_DB_PATH"]).resolve())
    child_env["IN_CSE_SERVER_IP"] = settings["IN_CSE_SERVER_IP"]
    child_env["IN_CSE_SERVER_PORT"] = settings["IN_CSE_SERVER_PORT"]
    child_env["IN_CSE_DASHBOARD_ORIGINATOR"] = settings["PG_IN_CSE_ORIGIN"]
    in_cse, in_pid, in_log = _paths(root, "in-cse")
    dashboard, dashboard_pid, dashboard_log = _paths(root, "dashboard")
    try:
        _launch(in_cse, ["-p", settings["IN_CSE_SERVER_PORT"]], runtime,
                child_env, in_pid, in_log)
        _wait("IN-CSE", in_pid, in_cse, lambda: _check_in_cse(settings, info))
        _launch(dashboard, [], root, child_env, dashboard_pid, dashboard_log)
        _wait("Dashboard", dashboard_pid, dashboard, lambda: _check_dashboard(settings))
    except (OSError, RuntimeError, ValueError):
        _stop(root, "dashboard")
        _stop(root, "in-cse")
        raise
    print("Monitoring Node started: IN-CSE and Dashboard are healthy.")
    print(f"Dashboard listens on configured port {settings['PG_DASHBOARD_PORT']}.")
    print("MEC registration and cross-computer connectivity are asynchronous and must be checked separately.")


def status(root: Path) -> int:
    settings, info = _settings(root)
    states = {}
    for service in ("in-cse", "dashboard"):
        executable, pid_file, _ = _paths(root, service)
        states[service] = _is_running(pid_file, executable)
        print(f"{service}: {'running' if states[service] else 'stopped'}")
    if states["in-cse"]:
        print(f"IN-CSE health: {'ok' if _check_in_cse(settings, info) else 'failed'}")
    if states["dashboard"]:
        print(f"Dashboard health: {'ok' if _check_dashboard(settings) else 'failed'}")
        url = f"http://127.0.0.1:{settings['PG_DASHBOARD_PORT']}/api/onem2m/devices"
        try:
            with urlopen(url, timeout=2) as response:
                body = json.loads(response.read(256_000))
            print(f"MEC data via IN-CSE: {'connected' if body.get('connected') else 'not connected'}")
        except (URLError, TimeoutError, OSError, json.JSONDecodeError):
            print("MEC data via IN-CSE: unavailable")
    return 0 if all(states.values()) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage the standalone Monitoring package.")
    parser.add_argument("command", choices=("configure", "start", "stop", "status", "healthcheck"))
    args = parser.parse_args(argv)
    root = package_root()
    try:
        if args.command == "configure":
            configure(root)
            return 0
        if args.command == "start":
            start(root)
            return 0
        if args.command == "stop":
            stopped = [_stop(root, service) for service in ("dashboard", "in-cse")]
            print("Monitoring services stopped." if any(stopped) else "Monitoring services are not running.")
            return 0
        return status(root)
    except (FileNotFoundError, FileExistsError, OSError, RuntimeError, ValueError) as exc:
        print(f"Monitoring {args.command} failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
