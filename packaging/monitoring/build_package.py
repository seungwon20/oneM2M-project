from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


PACKAGE_SOURCE = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_SOURCE.parents[1]
PACKAGE_NAME = "Monitoring-Package-Linux-x86_64"
IN_BUILD_SCRIPT = PROJECT_ROOT / "IN-CSE" / "scripts" / "build.py"
MN_BUILD_SCRIPT = PROJECT_ROOT / "MN-CSE" / "scripts" / "build.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load build module: {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_pyinstaller(entrypoint: Path, name: str, dist: Path, work: Path,
                     spec: Path, extra_args: list[str], python_path: Path | None = None) -> Path:
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
        "--name", name, "--distpath", str(dist), "--workpath", str(work),
        "--specpath", str(spec), *extra_args, str(entrypoint),
    ]
    env = os.environ.copy()
    if python_path is not None:
        env["PYTHONPATH"] = str(python_path)
    subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)
    result = dist / name
    if not result.is_dir():
        raise RuntimeError(f"PyInstaller did not create its expected output: {result}")
    return result


def _write_archive(package_root: Path, archive_path: Path) -> None:
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(package_root.rglob("*")):
            archive.add(path, arcname=path.relative_to(package_root.parent))
    digest = hashlib.sha256()
    with archive_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    archive_path.with_suffix(archive_path.suffix + ".sha256").write_text(
        f"{digest.hexdigest()}  {archive_path.name}\n", encoding="ascii"
    )


def build_package(output_dir: Path) -> Path:
    if platform.system() != "Linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise RuntimeError("Monitoring package builds are currently supported only on Linux x86_64.")
    if importlib.util.find_spec("PyInstaller") is None:
        raise RuntimeError("PyInstaller is missing; install packaging/monitoring/requirements-build.txt.")

    mn_build = _load_module(MN_BUILD_SCRIPT, "mn_cse_build")
    in_build = _load_module(IN_BUILD_SCRIPT, "in_cse_build")
    source_env = mn_build.parse_env(PROJECT_ROOT / ".env")
    mn_build.validate_environment(source_env)
    mn_build.validate_seed_db(source_env)
    in_env = in_build.parse_env(PROJECT_ROOT / ".env")
    in_rvi = in_build.validate_environment(in_env)
    if source_env.get("CSE_RVI") != in_rvi:
        raise ValueError("IN_CSE_RVI must match the MEC CSE_RVI.")
    if source_env.get("TINYIOT_CSE_BASE_SP_ID") != in_env.get("IN_CSE_CSE_BASE_SP_ID"):
        raise ValueError("The IN-CSE and MN-CSE SP IDs must match.")
    allowed = {
        value.strip()
        for value in in_env["IN_CSE_ALLOWED_REMOTE_CSE_ID"].split(",")
        if value.strip()
    }
    if f'/{source_env["TINYIOT_CSE_BASE_RI"]}' not in allowed:
        raise ValueError("IN_CSE_ALLOWED_REMOTE_CSE_ID must allow the MEC MN-CSE ID.")

    output_dir = output_dir.expanduser().resolve()
    archive_path = output_dir.with_suffix(".tar.gz")
    checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
    if output_dir.exists() or archive_path.exists() or checksum_path.exists():
        raise FileExistsError(f"Package output already exists: {output_dir}. Choose a new --output-dir.")

    subprocess.run([sys.executable, str(IN_BUILD_SCRIPT)], cwd=PROJECT_ROOT, check=True)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="monitoring-package-build-") as temporary:
        work_root = Path(temporary)
        dist = work_root / "dist"
        work = work_root / "work"
        specs = work_root / "spec"
        staged = work_root / PACKAGE_NAME

        control = _run_pyinstaller(
            PACKAGE_SOURCE / "monitor_control.py", "monitor-control", dist,
            work / "monitor-control", specs / "monitor-control", [],
        )
        dashboard = _run_pyinstaller(
            PACKAGE_SOURCE / "dashboard_entry.py", "dashboard", dist,
            work / "dashboard", specs / "dashboard",
            [
                "--paths", str(PROJECT_ROOT / "Dashboard"),
                "--add-data", f"{PROJECT_ROOT / 'Dashboard' / 'static'}:static",
                "--collect-all", "uvicorn",
                "--collect-all", "PIL",
            ],
            PROJECT_ROOT / "Dashboard",
        )

        (staged / "bin").mkdir(parents=True)
        shutil.copytree(control, staged / "bin" / "monitor-control")
        shutil.copytree(dashboard, staged / "bin" / "dashboard")
        shutil.copy2(PROJECT_ROOT / "IN-CSE" / "server", staged / "bin" / "tinyiot-in-cse")
        (staged / "bin" / "tinyiot-in-cse").chmod(0o755)
        (staged / "config").mkdir()
        shutil.copy2(PACKAGE_SOURCE / "templates" / ".env.example", staged / "config" / ".env.example")
        (staged / "config" / "build-info.json").write_text(
            json.dumps(
                {
                    "platform": "linux-x86_64",
                    "in_cse_base_name": in_env["IN_CSE_CSE_BASE_NAME"],
                    "in_cse_rvi": in_rvi,
                    "mn_cse_id": source_env["TINYIOT_CSE_BASE_RI"],
                },
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        for directory in ("runtime/logs", "runtime/pid"):
            (staged / directory).mkdir(parents=True, exist_ok=True)
        (staged / "scripts").mkdir()
        for source in (PACKAGE_SOURCE / "scripts").iterdir():
            destination = staged / "scripts" / source.name
            shutil.copy2(source, destination)
            destination.chmod(destination.stat().st_mode | 0o111)
        shutil.copy2(PACKAGE_SOURCE / "README.md", staged / "README.md")
        shutil.move(str(staged), output_dir)

    _write_archive(output_dir, archive_path)
    print(f"Created Monitoring package directory: {output_dir}")
    print(f"Created archive and SHA-256 file: {archive_path}")
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the standalone Monitoring package.")
    parser.add_argument("--output-dir", type=Path,
                        default=PACKAGE_SOURCE / "dist" / PACKAGE_NAME)
    args = parser.parse_args()
    try:
        build_package(args.output_dir)
    except (FileExistsError, FileNotFoundError, OSError, RuntimeError, ValueError,
            subprocess.CalledProcessError) as exc:
        print(f"Monitoring package build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
