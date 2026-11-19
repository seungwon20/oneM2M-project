from __future__ import annotations

import sys
from pathlib import Path

import httpx


sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_cse_connection import _print_resource_result, _tcp_check, _validate_config


def test_resource_check_output_redacts_configured_resource_id(capsys):
    secret_ri = "configured-resource-id-must-not-be-printed"
    response = httpx.Response(
        200,
        headers={"X-M2M-RSC": "2000"},
        json={
            "eg:Device1": {
                "ri": secret_ri,
                "ty": 28,
                "cnd": "org.onem2m.common.moduleclass",
                "zone_person_count": 1,
                "total_person_count": 2,
                "received_at": "2026-01-01T00:00:00Z",
            }
        },
    )

    retrieval_ok, schema_ok = _print_resource_result(
        "Camera",
        secret_ri,
        response,
        "request-id-must-not-be-printed",
        {"zone_person_count", "total_person_count", "received_at"},
        "eg:Device1",
    )

    output = capsys.readouterr().out
    assert retrieval_ok and schema_ok
    assert "RI match=PASS" in output
    assert secret_ri not in output
    assert "request-id-must-not-be-printed" not in output


def test_config_preflight_does_not_echo_invalid_url():
    secret_host = "private-host-must-not-be-printed"

    class Config:
        CSE_BASE_URL = f"http://{secret_host}:invalid"
        CSE_BASE_NAME = "TinyIoT"
        AE_ID = "private-originator-must-not-be-printed"
        CSE_RVI = "3"
        FCNT_RI = {
            "device1": "private-ri",
            "device2": "private-ri",
            "device3": "private-ri",
            "device4": "private-ri",
            "device5": "private-ri",
            "risk": "private-ri",
        }

    errors, _ = _validate_config(Config)

    assert errors
    assert all(secret_host not in error for error in errors)
    assert all("private-originator" not in error for error in errors)
    assert all("private-ri" not in error for error in errors)


def test_tcp_check_does_not_echo_destination(monkeypatch):
    secret_host = "private-host-must-not-be-printed"

    def fail_connection(*args, **kwargs):
        raise OSError(f"failed to reach {secret_host}")

    monkeypatch.setattr("check_cse_connection.socket.create_connection", fail_connection)

    connected, message = _tcp_check(secret_host, 3000)

    assert not connected
    assert secret_host not in message
