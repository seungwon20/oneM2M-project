from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PACKAGE_SOURCE = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_SOURCE.parents[1]
sys.path.insert(0, str(PACKAGE_SOURCE))

import mec_control
from mec_control import configure_mec, read_seed_settings, validate_settings
from dotenv import dotenv_values


def _package_root(tmp_path: Path) -> Path:
    root = tmp_path / "MEC-Package"
    (root / "config").mkdir(parents=True)
    (root / "data").mkdir()
    shutil.copy2(PROJECT_ROOT / "MN-CSE" / "data.db", root / "data" / "seed.db")
    shutil.copy2(
        PACKAGE_SOURCE / "templates" / ".env.example",
        root / "config" / ".env.example",
    )
    (root / "config" / "build-info.json").write_text(
        json.dumps(
            {
                "cse_rvi": "3",
                "tinyiot_cse_base_sp_id": "test-provider.example",
            }
        ),
        encoding="utf-8",
    )
    return root


def test_configure_populates_seed_mapping_and_preserves_operator_placeholders(tmp_path):
    root = _package_root(tmp_path)

    configure_mec(root)

    seed_settings = read_seed_settings(root / "data" / "seed.db")
    settings = dotenv_values(root / "config" / ".env")
    mapped_keys = (
        "CSE_BASE_NAME",
        "TINYIOT_CSE_BASE_NAME",
        "TINYIOT_CSE_BASE_RI",
        "FCNT_DEVICE1_RI",
        "FCNT_DEVICE2_RI",
        "FCNT_DEVICE3_RI",
        "FCNT_DEVICE4_RI",
        "FCNT_DEVICE5_RI",
        "FCNT_RISK_RI",
    )
    assert all(settings[key] == seed_settings[key] for key in mapped_keys)
    assert settings["CSE_RVI"] == "3"
    assert settings["TINYIOT_CSE_BASE_SP_ID"] == "test-provider.example"
    assert settings["AE_ID"] == "YOUR_AE_ORIGINATOR"
    assert settings["TINYIOT_SERVER_IP"] == "YOUR_MEC_LAN_IP"


def test_configure_does_not_overwrite_existing_package_configuration(tmp_path):
    root = _package_root(tmp_path)
    configure_mec(root)
    config_path = root / "config" / ".env"
    original = config_path.read_text(encoding="utf-8")

    with pytest.raises(FileExistsError, match="not overwritten"):
        configure_mec(root)

    assert config_path.read_text(encoding="utf-8") == original


def test_validate_settings_rejects_placeholders(tmp_path):
    root = _package_root(tmp_path)
    configure_mec(root)
    settings = {
        key: value
        for key, value in dotenv_values(root / "config" / ".env").items()
        if value is not None
    }

    with pytest.raises(ValueError, match="AE_ID.*TINYIOT_SERVER_IP"):
        validate_settings(root, settings)


def test_validate_settings_checks_runtime_url_and_seed_mapping(tmp_path):
    root = _package_root(tmp_path)
    configure_mec(root)
    settings = {
        key: value
        for key, value in dotenv_values(root / "config" / ".env").items()
        if value is not None
    }
    settings["AE_ID"] = "test-originator"
    settings["TINYIOT_SERVER_IP"] = "127.0.0.1"
    settings["REMOTE_CSE_ID"] = "/test-in"
    settings["REMOTE_CSE_NAME"] = "TestIN"
    settings["REMOTE_CSE_HOST"] = "monitoring.test"

    validate_settings(root, settings)

    settings["CSE_BASE_URL"] = "http://127.0.0.1:3001"
    with pytest.raises(ValueError, match="CSE_BASE_URL"):
        validate_settings(root, settings)

    settings["CSE_BASE_URL"] = "http://127.0.0.1:3000"
    settings["FCNT_DEVICE1_RI"] = "not-the-seed-resource"
    with pytest.raises(ValueError, match="FCNT_DEVICE1_RI"):
        validate_settings(root, settings)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"status": "ok"}, True),
        ({"status": "starting"}, False),
        ([], False),
        (None, False),
    ],
)
def test_ai_health_check_requires_status_object(monkeypatch, payload, expected):
    response = SimpleNamespace(status_code=200, json=lambda: payload)
    monkeypatch.setattr(mec_control.httpx, "get", lambda *args, **kwargs: response)

    assert mec_control._check_ai({"AI_AE_PORT": "8000"}) is expected
