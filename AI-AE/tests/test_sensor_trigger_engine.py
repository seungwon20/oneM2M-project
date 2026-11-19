from __future__ import annotations

import json
from urllib.parse import quote

import httpx
from fastapi.testclient import TestClient

from mec_safety.app import create_app
from mec_safety.config import Layer2Config
from mec_safety.layer2 import FCNT_WRAPPERS, Layer2Handoff
from mec_safety.sensorTriggerEngine import SensorTriggerEngine


def test_sensor_requests_run_model_without_client_supplied_risk_label():
    forwarded_requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        forwarded_requests.append(request)
        return httpx.Response(
            200,
            headers={
                "X-M2M-RSC": "2004",
                "X-M2M-RI": request.headers["X-M2M-RI"],
            },
            json={},
        )

    engine = SensorTriggerEngine()
    layer2 = Layer2Handoff(transport=httpx.MockTransport(respond))
    client = TestClient(create_app(layer2=layer2, trigger_engine=engine))

    sensor_updates = [
        ("device1", {"zone_person_count": 3, "total_person_count": 8}),
        ("device4", {"is_rotating": True, "speed_rpm": 1200.0}),
        ("device5", {"distance_cm": 10.0}),
        ("device3", {"beam_blocked": True}),
    ]
    responses = [
        client.post(f"/api/devices/{device_id}/data", json=data)
        for device_id, data in sensor_updates
    ]

    assert all(response.status_code == 200 for response in responses)
    assert all("risk_level" not in data for _, data in sensor_updates)
    assert engine.last_risk_level in {"HIGH", "CRITICAL"}
    assert engine.last_confidence is not None
    assert 0.0 <= engine.last_confidence <= 1.0
    assert engine.get_risk_payload() == {
        "risk_level": engine.last_risk_level,
        "speed_rpm": 1200.0,
        "distance_cm": 10.0,
    }
    assert responses[-1].json()["triggered"] is True
    final_response = responses[-1].json()
    assert final_response["risk_assessment"] == {
        "risk_level": engine.last_risk_level.title(),
        "speed_rpm": 1200.0,
        "distance_cm": 10.0,
    }
    assert final_response["risk_handoff"]["success"] is True
    assert len(forwarded_requests) == len(sensor_updates) + 1
    risk_request = forwarded_requests[-1]
    assert risk_request.method == "PUT"
    assert risk_request.url.raw_path.endswith(
        ("/" + quote(Layer2Config.FCNT_RI["risk"], safe="-")).encode()
    )
    risk_body = json.loads(risk_request.content)
    assert set(risk_body) == {FCNT_WRAPPERS["risk"]}
    assert {
        key: value
        for key, value in risk_body[FCNT_WRAPPERS["risk"]].items()
        if key != "evaluated_at"
    } == final_response["risk_assessment"]
    assert risk_body[FCNT_WRAPPERS["risk"]]["evaluated_at"] == final_response[
        "risk_evaluated_at"
    ]


def test_sensor_request_reports_failed_risk_handoff():
    forwarded_requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        forwarded_requests.append(request)
        is_risk_update = b'"eg:Device6"' in request.content
        return httpx.Response(
            403 if is_risk_update else 200,
            headers={
                "X-M2M-RSC": "4103" if is_risk_update else "2004",
                "X-M2M-RI": request.headers["X-M2M-RI"],
            },
            json={},
        )

    client = TestClient(
        create_app(
            layer2=Layer2Handoff(transport=httpx.MockTransport(respond)),
            trigger_engine=SensorTriggerEngine(),
        )
    )
    for device_id, data in [
        ("device1", {"zone_person_count": 3, "total_person_count": 8}),
        ("device4", {"is_rotating": True, "speed_rpm": 1200.0}),
        ("device5", {"distance_cm": 10.0}),
    ]:
        assert client.post(f"/api/devices/{device_id}/data", json=data).status_code == 200

    response = client.post(
        "/api/devices/device3/data",
        json={"beam_blocked": True},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["sensor_handoff"]["success"] is True
    assert detail["risk_handoff"]["success"] is False
    assert detail["risk_handoff"]["http_status"] == 403
    assert len(forwarded_requests) == 5
