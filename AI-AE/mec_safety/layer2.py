from __future__ import annotations

import uuid
from typing import Any, Dict
from urllib.parse import quote

import httpx

from .config import Layer2Config
from .device_schemas import validate_sensor_data


FCNT_WRAPPERS = {
    "device1": "eg:Device1",
    "device2": "eg:Device2",
    "device3": "eg:Device3",
    "device4": "eg:Device4",
    "device5": "eg:Device5",
    "risk": "eg:Device6",
}
DEVICE_TARGETS = {
    device_id: device_id
    for device_id in ("device1", "device2", "device3", "device4", "device5")
}
VALID_RISK_LEVELS = {"Low", "Medium", "High", "Critical"}


class Layer2Handoff:
    def __init__(
        self,
        config: Layer2Config | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config or Layer2Config
        self._transport = transport

    async def update_sensor(
        self, device_id: str, data: Dict[str, Any], *, received_at: str
    ) -> Dict[str, Any]:
        target = DEVICE_TARGETS.get(device_id)
        if target is None:
            return {
                "success": False,
                "device_id": device_id,
                "error": f"Unknown device_id: {device_id}",
            }
        if not isinstance(data, dict):
            return {
                "success": False,
                "device_id": device_id,
                "error": "Sensor handoff data must be an object.",
            }

        if not isinstance(received_at, str) or not received_at.strip():
            return {
                "success": False,
                "device_id": device_id,
                "error": "received_at must be a non-empty timestamp string.",
            }
        try:
            sensor_data = validate_sensor_data(device_id, data)
        except ValueError as exc:
            return {"success": False, "device_id": device_id, "error": str(exc)}

        resource_data = {**sensor_data, "received_at": received_at}
        return await self._update(target, resource_data, device_id=device_id)

    async def update_risk(
        self, data: Dict[str, Any], *, evaluated_at: str
    ) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return {
                "success": False,
                "error": "Risk assessment data must be an object.",
            }

        required = {"risk_level", "speed_rpm", "distance_cm"}
        if set(data) != required:
            return {
                "success": False,
                "error": (
                    "Risk assessment data must contain exactly: "
                    "risk_level, speed_rpm, distance_cm."
                ),
            }
        if not isinstance(evaluated_at, str) or not evaluated_at.strip():
            return {
                "success": False,
                "error": "evaluated_at must be a non-empty timestamp string.",
            }

        risk_level = data["risk_level"]
        if not isinstance(risk_level, str) or risk_level not in VALID_RISK_LEVELS:
            return {
                "success": False,
                "error": "risk_level must be Low, Medium, High, or Critical.",
            }
        for field in ("speed_rpm", "distance_cm"):
            value = data[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return {
                    "success": False,
                    "error": f"{field} must be a number.",
                }

        resource_data = {**data, "evaluated_at": evaluated_at}
        return await self._update("risk", resource_data)

    async def _update(
        self, target: str, data: Dict[str, Any], device_id: str | None = None
    ) -> Dict[str, Any]:
        resource_id = self._config.FCNT_RI.get(target)
        missing = [
            name for name, value in (
                ("CSE_BASE_URL", self._config.CSE_BASE_URL),
                ("AE_ID", self._config.AE_ID),
                ("CSE_RVI", self._config.CSE_RVI),
                (f"FCNT_RI[{target}]", resource_id),
            )
            if not isinstance(value, str) or not value.strip()
        ]
        if missing:
            return {
                "success": False,
                "device_id": device_id,
                "target": None,
                "error": "Missing Layer 2 configuration: " + ", ".join(missing),
            }

        request_id = str(uuid.uuid4())
        target_uri = (
            self._config.CSE_BASE_URL.rstrip("/")
            + "/"
            + quote(resource_id, safe="-")
        )
        body = {FCNT_WRAPPERS[target]: data}
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-M2M-Origin": self._config.AE_ID,
            "X-M2M-RI": request_id,
            "X-M2M-RVI": self._config.CSE_RVI,
        }

        try:
            async with httpx.AsyncClient(
                timeout=None, transport=self._transport
            ) as client:
                response = await client.put(target_uri, json=body, headers=headers)
        except httpx.HTTPError as exc:
            return {
                "success": False,
                "device_id": device_id,
                "target": target_uri,
                "http_status": None,
                "x_m2m_rsc": None,
                "request_id": request_id,
                "error": str(exc),
            }

        response_rsc = response.headers.get("X-M2M-RSC")
        response_request_id = response.headers.get("X-M2M-RI")
        success = (
            response.status_code == 200
            and response_rsc == "2004"
            and response_request_id == request_id
        )
        result: Dict[str, Any] = {
            "success": success,
            "device_id": device_id,
            "target": target_uri,
            "http_status": response.status_code,
            "x_m2m_rsc": response_rsc,
            "request_id": request_id,
        }
        if not success:
            result["response_request_id"] = response_request_id
            result["error"] = response.text
        return result
