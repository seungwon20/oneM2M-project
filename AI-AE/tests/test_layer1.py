from __future__ import annotations

import json
from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from mec_safety.app import create_app
from mec_safety.config import Layer2Config
from mec_safety.layer2 import FCNT_WRAPPERS, Layer2Handoff


def _client(
    *, status_code: int = 200, rsc: str = "2004"
) -> tuple[TestClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            status_code,
            headers={
                "X-M2M-RSC": rsc,
                "X-M2M-RI": request.headers["X-M2M-RI"],
            },
            json={},
        )

    layer2 = Layer2Handoff(transport=httpx.MockTransport(respond))
    return TestClient(create_app(layer2)), requests


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_sensor_post_is_handed_directly_to_layer2_with_schema_timestamp():
    client, requests = _client()
    data = {"zone_person_count": 5, "total_person_count": 18}

    response = client.post("/api/devices/device1/data", json=data)

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == data
    _timestamp(body["received_at"])
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "PUT"
    assert request.headers["X-M2M-Origin"] == Layer2Config.AE_ID
    assert request.headers["X-M2M-RVI"] == "3"
    assert request.headers["X-M2M-RI"] == body["handoff"]["request_id"]
    assert json.loads(request.content) == {
        "eg:Device1": {**data, "received_at": body["received_at"]}
    }
    assert body["triggered"] is False


def test_trigger_hook_runs_before_layer2_and_gets_full_latest_snapshot():
    order = []
    camera = {"zone_person_count": 5, "total_person_count": 18}

    class TriggerEngine:
        def evaluate(self, device_id, current_data, previous_data, latest_snapshot):
            order.append("trigger")
            assert device_id == "device1"
            assert current_data == camera
            assert previous_data is None
            assert latest_snapshot == {"device1": camera}
            return True

        def get_risk_payload(self):
            return None

    class Layer2:
        async def update_sensor(self, _device_id, _data, *, received_at):
            order.append("layer2")
            assert _device_id == "device1"
            assert _data == camera
            assert received_at
            return {"success": True, "request_id": "test-request"}

    client = TestClient(create_app(Layer2(), TriggerEngine()))

    response = client.post("/api/devices/device1/data", json=camera)

    assert response.status_code == 200
    assert response.json()["triggered"] is True
    assert order == ["trigger", "layer2"]
    assert client.get("/api/snapshot").json()["snapshot"] == {"device1": camera}


@pytest.mark.parametrize(
    ("device_id", "data"),
    [
        ("device1", {"zone_person_count": 5, "total_person_count": 18}),
        ("device2", {"weight_kg": 35.75}),
        ("device3", {"beam_blocked": True}),
        ("device4", {"is_rotating": True, "speed_rpm": 86.5}),
        ("device5", {"distance_cm": 42.8}),
    ],
)
def test_all_sensor_schemas_map_to_the_matching_cse_wrapper(device_id, data):
    client, requests = _client()

    response = client.post(f"/api/devices/{device_id}/data", json=data)

    assert response.status_code == 200
    resource = json.loads(requests[0].content)
    assert set(resource) == {FCNT_WRAPPERS[device_id]}
    assert {key: value for key, value in resource[FCNT_WRAPPERS[device_id]].items()
            if key != "received_at"} == data
    _timestamp(resource[FCNT_WRAPPERS[device_id]]["received_at"])


def test_invalid_sensor_payload_is_not_handed_off():
    client, requests = _client()

    response = client.post(
        "/api/devices/device2/data",
        json={"weight_kg": "35.75"},
    )

    assert response.status_code == 400
    assert requests == []


def test_latest_snapshot_contains_measurements_not_cse_metadata():
    client, _ = _client()
    camera = {"zone_person_count": 5, "total_person_count": 18}
    client.post("/api/devices/device1/data", json=camera)
    client.post("/api/devices/device2/data", json={"weight_kg": 20.5})
    client.post("/api/devices/device2/data", json={"weight_kg": 35.75})

    snapshot = client.get("/api/snapshot").json()["snapshot"]

    assert snapshot == {
        "device1": camera,
        "device2": {"weight_kg": 35.75},
    }


def test_risk_handoff_adds_evaluated_at_and_uses_risk_wrapper():
    client, requests = _client()
    data = {"risk_level": "High", "speed_rpm": 86.5, "distance_cm": 42.8}

    response = client.post("/api/risk-assessment", json=data)

    assert response.status_code == 200
    body = response.json()
    assert body["risk_assessment"] == data
    _timestamp(body["evaluated_at"])
    assert json.loads(requests[0].content) == {
        "eg:Device6": {**data, "evaluated_at": body["evaluated_at"]}
    }


def test_cse_failure_is_reported_instead_of_success():
    client, requests = _client(status_code=403, rsc="4103")

    response = client.post(
        "/api/devices/device5/data",
        json={"distance_cm": 42.8},
    )

    assert response.status_code == 502
    assert response.json()["detail"]["success"] is False
    assert response.json()["detail"]["http_status"] == 403
    assert len(requests) == 1


def test_partial_snapshot_is_supported():
    client, _ = _client()

    assert client.get("/api/snapshot").json()["snapshot"] == {}
    client.post("/api/devices/device5/data", json={"distance_cm": 42.8})
    assert client.get("/api/snapshot").json()["snapshot"] == {
        "device5": {"distance_cm": 42.8}
    }
