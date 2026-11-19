from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


PACKAGE_SOURCE = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_SOURCE.parents[1]
BUILD_SCRIPT = PROJECT_ROOT / "MN-CSE" / "scripts" / "build.py"
PYINSTALLER_REQUIREMENTS = PACKAGE_SOURCE / "requirements-build.txt"
PACKAGE_NAME = "MEC-Package-Linux-x86_64"


def _load_tinyiot_build_module():
    spec = importlib.util.spec_from_file_location("tinyiot_build", BUILD_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the MN-CSE build configuration module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _collect_python_licenses(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    metadata_lines = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name", "unknown")
        version = distribution.version
        license_name = distribution.metadata.get("License", "See included license file")
        metadata_lines.append(f"{name} {version}: {license_name}")
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
        for package_file in distribution.files or ():
            file_name = Path(package_file).name
            if not re.match(r"^(LICENSE|COPYING|NOTICE)(\..*)?$", file_name, re.IGNORECASE):
                continue
            source = Path(distribution.locate_file(package_file))
            if source.is_file():
                shutil.copy2(source, destination / f"{safe_name}-{file_name}")
    (destination / "PACKAGE-METADATA.txt").write_text(
        "\n".join(sorted(metadata_lines)) + "\n",
        encoding="utf-8",
    )


def _run_pyinstaller(
    *,
    entrypoint: Path,
    name: str,
    dist_path: Path,
    work_path: Path,
    spec_path: Path,
    extra_args: list[str],
) -> Path:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        name,
        "--distpath",
        str(dist_path),
        "--workpath",
        str(work_path),
        "--specpath",
        str(spec_path),
        *extra_args,
        str(entrypoint),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "AI-AE")
    subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)
    result = dist_path / name
    if not result.is_dir():
        raise RuntimeError(f"PyInstaller did not create its expected output: {result}")
    return result


def _write_archive(package_root: Path, archive_path: Path) -> None:
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(package_root.rglob("*")):
            archive.add(path, arcname=path.relative_to(package_root.parent))

    hasher = hashlib.sha256()
    with archive_path.open("rb") as package_file:
        for chunk in iter(lambda: package_file.read(1024 * 1024), b""):
            hasher.update(chunk)
    archive_path.with_suffix(archive_path.suffix + ".sha256").write_text(
        f"{hasher.hexdigest()}  {archive_path.name}\n",
        encoding="ascii",
    )


def build_package(output_dir: Path) -> Path:
    if platform.system() != "Linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise RuntimeError("MEC package builds are currently supported only on Linux x86_64.")
    if not BUILD_SCRIPT.is_file():
        raise FileNotFoundError(f"MN-CSE build script not found: {BUILD_SCRIPT}")
    if importlib.util.find_spec("PyInstaller") is None:
        raise RuntimeError(
            "PyInstaller is missing. Install packaging/mec/requirements-build.txt first."
        )

    output_dir = output_dir.expanduser().resolve()
    archive_path = output_dir.with_suffix(".tar.gz")
    checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
    if output_dir.exists() or archive_path.exists() or checksum_path.exists():
        raise FileExistsError(
            f"Package output already exists: {output_dir}. Choose a new --output-dir."
        )

    build_module = _load_tinyiot_build_module()
    source_env = build_module.parse_env(build_module.ENV_PATH)
    rvi = build_module.validate_environment(source_env)
    build_module.validate_seed_db(source_env)
    subprocess.run([sys.executable, str(BUILD_SCRIPT)], cwd=PROJECT_ROOT, check=True)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mec-package-build-") as temporary:
        temporary_root = Path(temporary)
        dist_path = temporary_root / "pyinstaller-dist"
        work_path = temporary_root / "pyinstaller-work"
        spec_path = temporary_root / "pyinstaller-spec"
        staged_root = temporary_root / PACKAGE_NAME

        ai_dist = _run_pyinstaller(
            entrypoint=PACKAGE_SOURCE / "ai_ae_entry.py",
            name="ai-ae",
            dist_path=dist_path,
            work_path=work_path / "ai-ae",
            spec_path=spec_path / "ai-ae",
            extra_args=[
                "--add-data",
                f"{PROJECT_ROOT / 'AI-AE' / 'mec_safety' / 'risk_model.joblib'}:mec_safety",
                "--collect-all",
                "sklearn",
                "--collect-all",
                "scipy",
                "--collect-submodules",
                "uvicorn",
            ],
        )
        control_dist = _run_pyinstaller(
            entrypoint=PACKAGE_SOURCE / "mec_control.py",
            name="mec-control",
            dist_path=dist_path,
            work_path=work_path / "mec-control",
            spec_path=spec_path / "mec-control",
            extra_args=["--collect-all", "httpx", "--collect-all", "dotenv"],
        )

        (staged_root / "bin").mkdir(parents=True)
        shutil.copytree(ai_dist, staged_root / "bin" / "ai-ae")
        shutil.copytree(control_dist, staged_root / "bin" / "mec-control")
        tinyiot = staged_root / "bin" / "tinyiot-mn-cse"
        shutil.copy2(PROJECT_ROOT / "MN-CSE" / "server", tinyiot)
        tinyiot.chmod(tinyiot.stat().st_mode | 0o111)

        (staged_root / "config").mkdir()
        shutil.copy2(
            PACKAGE_SOURCE / "templates" / ".env.example",
            staged_root / "config" / ".env.example",
        )
        (staged_root / "config" / "build-info.json").write_text(
            json.dumps(
                {
                    "platform": "linux-x86_64",
                    "cse_rvi": rvi,
                    "tinyiot_cse_base_sp_id": source_env["TINYIOT_CSE_BASE_SP_ID"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        (staged_root / "data").mkdir()
        shutil.copy2(
            PROJECT_ROOT / "MN-CSE" / "data.db",
            staged_root / "data" / "seed.db",
        )
        shutil.copytree(
            PROJECT_ROOT / "MN-CSE" / "sdt_definitions",
            staged_root / "share" / "sdt_definitions",
        )
        (staged_root / "models").mkdir()
        shutil.copy2(
            PROJECT_ROOT / "AI-AE" / "mec_safety" / "risk_model.joblib",
            staged_root / "models" / "risk_model.joblib",
        )

        for directory in ("runtime/logs", "runtime/pid"):
            (staged_root / directory).mkdir(parents=True, exist_ok=True)

        (staged_root / "scripts").mkdir()
        for source in (PACKAGE_SOURCE / "scripts").iterdir():
            destination = staged_root / "scripts" / source.name
            shutil.copy2(source, destination)
            destination.chmod(destination.stat().st_mode | 0o111)

        (staged_root / "licenses").mkdir()
        shutil.copy2(
            PROJECT_ROOT / "MN-CSE" / "app" / "LICENSE",
            staged_root / "licenses" / "TinyIoT-LICENSE",
        )
        _collect_python_licenses(staged_root / "licenses" / "python")
        shutil.copy2(PACKAGE_SOURCE / "README.md", staged_root / "README.md")

        final_package = temporary_root / PACKAGE_NAME
        shutil.move(str(final_package), output_dir)

    _write_archive(output_dir, archive_path)
    print(f"Created MEC package directory: {output_dir}")
    print(f"Created archive and SHA-256 file: {archive_path}")
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the standalone MEC package.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PACKAGE_SOURCE / "dist" / PACKAGE_NAME,
        help="new package output directory (must not already exist)",
    )
    args = parser.parse_args()
    try:
        build_package(args.output_dir)
    except (FileExistsError, FileNotFoundError, OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"MEC package build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
