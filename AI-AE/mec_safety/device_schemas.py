from __future__ import annotations

from typing import Any, Callable, Dict


def _is_integer(value: Any) -> bool:
    return type(value) is int


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_boolean(value: Any) -> bool:
    return type(value) is bool


DEVICE_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "device1": {
        "name": "Camera",
        "required": {
            "zone_person_count": _is_integer,
            "total_person_count": _is_integer,
        },
    },
    "device2": {
        "name": "Weight Sensor",
        "required": {
            "weight_kg": _is_number,
        },
    },
    "device3": {
        "name": "Infrared Sensor",
        "required": {
            "beam_blocked": _is_boolean,
        },
    },
    "device4": {
        "name": "Encoder",
        "required": {
            "is_rotating": _is_boolean,
            "speed_rpm": _is_number,
        },
    },
    "device5": {
        "name": "Distance Sensor",
        "required": {
            "distance_cm": _is_number,
        },
    },
}


def validate_sensor_data(device_id: str, data: Any) -> Dict[str, Any]:
    if device_id not in DEVICE_SCHEMAS:
        raise ValueError(f"Unknown device_id: {device_id}")

    if not isinstance(data, dict):
        raise ValueError("Sensor payload must be a JSON object.")

    schema = DEVICE_SCHEMAS[device_id]
    expected_fields = set(schema["required"].keys())
    provided_fields = set(data.keys())

    unexpected_fields = sorted(provided_fields - expected_fields)
    if unexpected_fields:
        raise ValueError(
            f"Unexpected fields for {device_id}: {', '.join(unexpected_fields)}"
        )

    missing_fields = [field for field in sorted(expected_fields) if field not in data]
    if missing_fields:
        raise ValueError(f"Missing fields for {device_id}: {', '.join(missing_fields)}")

    for field_name, validator in schema["required"].items():
        value = data[field_name]
        if not validator(value):
            expected_type = {
                "zone_person_count": "integer",
                "total_person_count": "integer",
                "weight_kg": "number",
                "beam_blocked": "boolean",
                "is_rotating": "boolean",
                "speed_rpm": "number",
                "distance_cm": "number",
            }[field_name]
            raise ValueError(
                f"Invalid type for {device_id}.{field_name}: expected {expected_type}, "
                f"received {type(value).__name__}."
            )

    return dict(data)
