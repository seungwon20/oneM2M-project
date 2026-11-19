from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request

from .device_schemas import DEVICE_SCHEMAS, validate_sensor_data
from .layer2 import Layer2Handoff, VALID_RISK_LEVELS
from .sensorTriggerEngine import SensorTriggerEngine
from .storage import LatestSensorState
from contextlib import asynccontextmanager
from .demo_plc_client import DemoPLCClient


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

def create_app(
    layer2: Layer2Handoff | None = None,
    trigger_engine: SensorTriggerEngine | None = None,
    plc_client: DemoPLCClient | None = None,
) -> FastAPI:
    state = LatestSensorState()
    layer2 = layer2 or Layer2Handoff()
    trigger_engine = trigger_engine or SensorTriggerEngine()
    plc_client = plc_client or DemoPLCClient()
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await plc_client.connect()
        except OSError as exc:
            print(f"[AI APPLICATION] PLC connection failed: {exc}")

        yield

        await plc_client.close()

    app = FastAPI(
        title="MEC Safety Application",
        lifespan=lifespan
    )

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/devices/{device_id}/data")
    async def ingest_sensor(device_id: str, request: Request) -> Dict[str, Any]:
        if device_id not in DEVICE_SCHEMAS:
            raise HTTPException(status_code=404, detail=f"Unknown device_id: {device_id}")

        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

        try:
            valid_payload = validate_sensor_data(device_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        received_at = _utc_timestamp()
        previous_data = state.get(device_id)
        state.update(device_id, valid_payload)
        triggered = trigger_engine.evaluate(
            device_id,
            valid_payload,
            previous_data,
            state.snapshot(),
        )
        risk_payload = trigger_engine.get_risk_payload()
        plc_result = None
        if (
            triggered
            and risk_payload is not None
            and risk_payload["risk_level"] =="CRITICAL"
        ) :
            plc_result = await plc_client.request_stop()


        handoff = await layer2.update_sensor(
            device_id, valid_payload, received_at=received_at
        )
        if not handoff["success"]:
            raise HTTPException(status_code=502, detail=handoff)
        response: Dict[str, Any] = {
            "status": "accepted",
            "device_id": device_id,
            "data": valid_payload,
            "received_at": received_at,
            "triggered": triggered,
            "handoff": handoff,
        }
        if plc_result is not None:
            response["plc_result"] = plc_result
            
        if risk_payload is not None:
            risk_assessment = {
                **risk_payload,
                "risk_level": risk_payload["risk_level"].title(),
            }
            evaluated_at = _utc_timestamp()
            risk_handoff = await layer2.update_risk(
                risk_assessment, evaluated_at=evaluated_at
            )
            if not risk_handoff["success"]:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "sensor_handoff": handoff,
                        "risk_assessment": risk_assessment,
                        "risk_handoff": risk_handoff,
                    },
                )
            response["risk_assessment"] = risk_assessment
            response["risk_evaluated_at"] = evaluated_at
            response["risk_handoff"] = risk_handoff
        return response

    @app.get("/api/devices/{device_id}")
    async def get_latest_device_data(device_id: str) -> Dict[str, Any]:
        if device_id not in DEVICE_SCHEMAS:
            raise HTTPException(status_code=404, detail=f"Unknown device_id: {device_id}")

        value = state.get(device_id)
        if value is None:
            raise HTTPException(status_code=404, detail=f"No data received for {device_id} yet.")

        return {"device_id": device_id, "data": value}

    @app.get("/api/snapshot")
    async def get_snapshot() -> Dict[str, Any]:
        return {"snapshot": state.snapshot()}

    @app.post("/api/risk-assessment")
    async def risk_assessment(request: Request) -> Dict[str, Any]:
        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Risk assessment payload must be a JSON object.")

        required = {"risk_level", "speed_rpm", "distance_cm"}
        if set(payload.keys()) != required:
            raise HTTPException(
                status_code=400,
                detail="Risk assessment payload must contain exactly: risk_level, speed_rpm, distance_cm.",
            )

        risk_level = payload["risk_level"]
        if not isinstance(risk_level, str) or risk_level not in VALID_RISK_LEVELS:
            raise HTTPException(
                status_code=400,
                detail="risk_level must be Low, Medium, High, or Critical.",
            )
        for field in ("speed_rpm", "distance_cm"):
            value = payload[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise HTTPException(status_code=400, detail=f"{field} must be a number.")

        evaluated_at = _utc_timestamp()
        result = await layer2.update_risk(payload, evaluated_at=evaluated_at)
        if not result["success"]:
            raise HTTPException(status_code=502, detail=result)

        return {
            "status": "accepted",
            "risk_assessment": payload,
            "evaluated_at": evaluated_at,
            "handoff": result,
        }

    return app


app = create_app()
