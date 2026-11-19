from __future__ import annotations

import copy
from typing import Any, Dict, Optional


class LatestSensorState:
    def __init__(self) -> None:
        self._latest: Dict[str, Dict[str, Any]] = {}

    def update(self, device_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        self._latest[device_id] = copy.deepcopy(data)
        return copy.deepcopy(self._latest[device_id])

    def get(self, device_id: str) -> Optional[Dict[str, Any]]:
        if device_id not in self._latest:
            return None
        return copy.deepcopy(self._latest[device_id])

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {key: copy.deepcopy(value) for key, value in sorted(self._latest.items())}

    def device_ids(self) -> list[str]:
        return sorted(self._latest.keys())
