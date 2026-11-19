from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Set

import joblib
import numpy as np


class SensorTriggerEngine:
    """Run a trained risk classifier only when the infrared/encoder trigger fires.

    evaluate() returns True for HIGH or CRITICAL predictions by default.
    The most recent prediction can be read from last_risk_level and
    last_risk_payload for forwarding to the oneM2M Risk FlexContainer.
    """

    FEATURE_COLUMNS = (
        "zone_person_count",
        "zone_total_count",
        "speed_rpm",
        "distance_cm",
    )
    VALID_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

    def __init__(
        self,
        model_path: Optional[str | Path] = None,
        trigger_levels: Optional[Set[str]] = None,
    ) -> None:
        resolved_model_path = (
            Path(model_path).expanduser().resolve()
            if model_path is not None
            else Path(__file__).resolve().with_name("risk_model.joblib")
        )
        if not resolved_model_path.is_file():
            raise FileNotFoundError(
                f"Risk model not found: {resolved_model_path}. "
                "Run train_risk_model.py first."
            )

        bundle = joblib.load(resolved_model_path)
        if not isinstance(bundle, dict) or "model" not in bundle:
            raise ValueError("Invalid model bundle: expected a dict with 'model'.")
        if tuple(bundle.get("feature_columns", ())) != self.FEATURE_COLUMNS:
            raise ValueError("Model feature order does not match SensorTriggerEngine.")

        self.model = bundle["model"]
        model_labels = set(getattr(self.model, "classes_", ()))
        if model_labels != self.VALID_LEVELS:
            raise ValueError(
                f"Model labels must be {sorted(self.VALID_LEVELS)}, "
                f"got {sorted(model_labels)}"
            )

        self.trigger_levels = set(trigger_levels or {"HIGH", "CRITICAL"})
        if not self.trigger_levels <= self.VALID_LEVELS:
            raise ValueError("trigger_levels contains an unsupported risk label")

        self.last_risk_level: Optional[str] = None
        self.last_confidence: Optional[float] = None
        self.last_risk_payload: Optional[Dict[str, Any]] = None
        self.last_error: Optional[str] = None    
    @staticmethod
    def _get_number(
        snapshot: Dict[str, Dict[str, Any]],
        device_id: str,
        field: str,
        *,
        integer: bool = False,
    ) -> float:
        device_data = snapshot.get(device_id)
        if not isinstance(device_data, dict) or field not in device_data:
            raise ValueError(f"Missing {device_id}.{field} in latest_snapshot")

        value = device_data[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{device_id}.{field} must be numeric")
        numeric = float(value)
        if not np.isfinite(numeric) or numeric < 0:
            raise ValueError(f"{device_id}.{field} must be finite and non-negative")
        if integer and not numeric.is_integer():
            raise ValueError(f"{device_id}.{field} must be an integer")
        return numeric

    def evaluate(
        self,
        device_id: str,
        current_data: Dict[str, Any],
        previous_data: Optional[Dict[str, Any]],
        latest_snapshot: Dict[str, Dict[str, Any]],
    ) -> bool:
        # Clear the previous event's result so stale Risk data is not reused.
        self.last_risk_level = None
        self.last_confidence = None
        self.last_risk_payload = None
        self.last_error = None

        # Device 3 (Infrared) is the trigger source.
        if device_id != "device3":
            return False
        if current_data.get("beam_blocked") is not True:
            return False

        # Only evaluate when Device 4 (Encoder) reports that the belt is moving.
        encoder_data = latest_snapshot.get("device4", {})
        if not isinstance(encoder_data, dict) or encoder_data.get("is_rotating") is not True:
            return False

        return self.ML_evaluate(latest_snapshot)

    def ML_evaluate(self, latest_snapshot: Dict[str, Dict[str, Any]]) -> bool:
        """Predict LOW/MEDIUM/HIGH/CRITICAL and return the alert decision."""
        try:
            zone_person_count = self._get_number(
                latest_snapshot, "device1", "zone_person_count", integer=True
            )
            zone_total_count = self._get_number(
                latest_snapshot, "device1", "total_person_count", integer=True
            )
            speed_rpm = self._get_number(
                latest_snapshot, "device4", "speed_rpm"
            )
            distance_cm = self._get_number(
                latest_snapshot, "device5", "distance_cm"
            )

            if zone_person_count > zone_total_count:
                raise ValueError(
                    "device1.zone_person_count cannot exceed zone_total_count"
                )

            features = np.asarray([[
                zone_person_count,
                zone_total_count,
                speed_rpm,
                distance_cm,
            ]], dtype=np.float64)

            predicted_level = str(self.model.predict(features)[0])
            if predicted_level not in self.VALID_LEVELS:
                raise ValueError(f"Model returned an unknown risk label: {predicted_level}")

            self.last_risk_level = predicted_level
            if hasattr(self.model, "predict_proba"):
                probabilities = self.model.predict_proba(features)[0]
                self.last_confidence = float(np.max(probabilities))

            # This payload maps to the project's Risk FlexContainer fields.
            self.last_risk_payload = {
                "risk_level": predicted_level,
                "speed_rpm": speed_rpm,
                "distance_cm": distance_cm,
            }

            # True means an actionable high-severity risk was predicted.
            return predicted_level in self.trigger_levels

        except (TypeError, ValueError, KeyError) as exc:
            # Fail closed: invalid/incomplete snapshots do not create a positive alert.
            self.last_error = str(exc)
            return False

    def get_risk_payload(self) -> Optional[Dict[str, Any]]:
        """Return a copy of the latest Risk FlexContainer payload, if available."""
        return dict(self.last_risk_payload) if self.last_risk_payload is not None else None
