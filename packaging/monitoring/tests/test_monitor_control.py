from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest


PACKAGE_SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_SOURCE))

import monitor_control


def _package_root(tmp_path: Path) -> Path:
    root = tmp_path / "Monitoring-Package"
    (root / "config").mkdir(parents=True)
    shutil.copy2(
        PACKAGE_SOURCE / "templates" / ".env.example",
        root / "config" / ".env.example",
    )
    (root / "config" / "build-info.json").write_text(
        json.dumps({
            "in_cse_base_name": "TestIN",
            "in_cse_id": "test-in-id",
            "in_cse_rvi": "3",
            "mn_cse_id": "test-mn",
            "mn_device_resource_ids": {
                f"Device{i}": f"test-device-{i}-ri" for i in range(1, 7)
            },
        }),
        encoding="utf-8",
    )
    return root


def test_configure_populates_build_values_without_overwriting(tmp_path: Path):
    root = _package_root(tmp_path)
    monitor_control.configure(root)
    settings = monitor_control._read_env(root / "config" / ".env")

    assert settings["PG_IN_CSE_URL"] == "http://127.0.0.1:3001"
    assert settings["PG_MN_CSE_ID"] == "test-mn"
    assert settings["PG_IN_CSE_ORIGIN"] == "YOUR_MEC_AE_ID"
    assert settings["PG_IN_CSE_RVI"] == "3"
    assert settings["PG_MN_DEVICE1_RI"] == "test-device-1-ri"
    assert settings["PG_MN_DEVICE6_RI"] == "test-device-6-ri"
    with pytest.raises(FileExistsError, match="not overwritten"):
        monitor_control.configure(root)


def test_settings_reject_placeholders_and_mismatched_cse_id(tmp_path: Path):
    root = _package_root(tmp_path)
    monitor_control.configure(root)
    env_path = root / "config" / ".env"
    settings = monitor_control._read_env(env_path)
    settings.update({
        "IN_CSE_SERVER_IP": "192.0.2.10",
        "PG_INGEST_KEY": "test-key-with-more-than-16-chars",
        "PG_IN_CSE_ORIGIN": "test-dashboard",
        "PG_MN_CSE_ID": "wrong-id",
    })
    env_path.write_text(
        "\n".join(f"{key}={value}" for key, value in settings.items()) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="PG_MN_CSE_ID"):
        monitor_control._settings(root)


def test_settings_accepts_operator_dashboard_originator(tmp_path: Path):
    root = _package_root(tmp_path)
    monitor_control.configure(root)
    env_path = root / "config" / ".env"
    settings = monitor_control._read_env(env_path)
    settings.update({
        "IN_CSE_SERVER_IP": "192.0.2.10",
        "PG_INGEST_KEY": "test-key-with-more-than-16-chars",
        "PG_IN_CSE_ORIGIN": "operator-dashboard",
    })
    env_path.write_text(
        "\n".join(f"{key}={value}" for key, value in settings.items()) + "\n",
        encoding="utf-8",
    )

    validated, _ = monitor_control._settings(root)
    assert validated["PG_IN_CSE_ORIGIN"] == "operator-dashboard"


def test_settings_rejects_resource_id_mismatch(tmp_path: Path):
    root = _package_root(tmp_path)
    monitor_control.configure(root)
    env_path = root / "config" / ".env"
    settings = monitor_control._read_env(env_path)
    settings.update({
        "IN_CSE_SERVER_IP": "192.0.2.10",
        "PG_INGEST_KEY": "test-key-with-more-than-16-chars",
        "PG_IN_CSE_ORIGIN": "operator-dashboard",
        "PG_MN_DEVICE1_RI": "wrong-ri",
    })
    env_path.write_text(
        "\n".join(f"{key}={value}" for key, value in settings.items()) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="PG_MN_DEVICE1_RI"):
        monitor_control._settings(root)


def test_start_passes_dashboard_originator_to_in_cse(tmp_path: Path, monkeypatch):
    root = _package_root(tmp_path)
    monitor_control.configure(root)
    env_path = root / "config" / ".env"
    settings = monitor_control._read_env(env_path)
    settings.update({
        "IN_CSE_SERVER_IP": "192.0.2.10",
        "PG_INGEST_KEY": "test-key-with-more-than-16-chars",
        "PG_IN_CSE_ORIGIN": "operator-dashboard",
    })
    env_path.write_text(
        "\n".join(f"{key}={value}" for key, value in settings.items()) + "\n",
        encoding="utf-8",
    )

    launched = []
    monkeypatch.setattr(monitor_control, "_is_running", lambda *_: False)
    monkeypatch.setattr(
        monitor_control,
        "_launch",
        lambda executable, args, cwd, env, pid_file, log_file: launched.append(env.copy()),
    )
    monkeypatch.setattr(monitor_control, "_wait", lambda *_args, **_kwargs: None)

    monitor_control.start(root)

    assert len(launched) == 2
    assert launched[0]["IN_CSE_DASHBOARD_ORIGINATOR"] == "operator-dashboard"
