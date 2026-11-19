from __future__ import annotations

import sys
from pathlib import Path

import pytest


PACKAGE_SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_SOURCE))

import build_package


def test_in_cse_package_identity_is_fixed_and_mec_access_is_limited():
    settings = build_package._in_cse_build_settings(
        {"CSE_RVI": "3", "TINYIOT_CSE_BASE_SP_ID": "example.invalid"},
        "seed-mn-id",
    )

    assert settings["IN_CSE_CSE_BASE_NAME"] == "PinchGuardIN"
    assert settings["IN_CSE_CSE_BASE_RI"] == "PinchGuardIN"
    assert settings["IN_CSE_ALLOWED_REMOTE_CSE_ID"] == "/seed-mn-id"
    assert settings["IN_CSE_RVI"] == "3"
    assert settings["IN_CSE_CSE_BASE_SP_ID"] == "example.invalid"
    assert "IN_CSE_ADMIN_AE_ID" not in settings


@pytest.mark.parametrize(
    "source_env, message",
    [
        ({"CSE_RVI": "invalid", "TINYIOT_CSE_BASE_SP_ID": "sp"}, "CSE_RVI"),
        ({"CSE_RVI": "3", "TINYIOT_CSE_BASE_SP_ID": "YOUR_SP_ID"}, "SP_ID"),
    ],
)
def test_in_cse_package_identity_rejects_invalid_mec_settings(source_env, message):
    with pytest.raises(ValueError, match=message):
        build_package._in_cse_build_settings(source_env, "seed-mn-id")


def test_dashboard_build_rejects_missing_runtime_dependency(monkeypatch):
    def find_spec(module):
        return None if module == "PIL" else object()

    monkeypatch.setattr(build_package.importlib.util, "find_spec", find_spec)

    with pytest.raises(RuntimeError, match="PIL"):
        build_package._check_dashboard_build_dependencies()
