from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path
from typing import Any, Dict, Iterable

import httpx


DATASET_PATH = Path(__file__).resolve().with_name("mock_sensor_dataset.csv")
DEFAULT_BASE_URL = "http://127.0.0.1:8001"


def _boolean(row: Dict[str, str], field: str) -> bool:
    value = row[field]
    if value == "True":
        return True
    if value == "False":
        return False
    raise ValueError(f"{field} must be True or False, got {value!r}")


def load_mock_rows(path: Path = DATASET_PATH) -> list[Dict[str, str]]:
    required_fields = {
        "sample_id",
        "device1_zone_person_count",
        "device1_zone_total_count",
        "device2_weight_kg",
        "device3_beam_blocked",
        "device4_is_rotating",
        "device4_speed_rpm",
        "device5_distance_cm",
    }
    with path.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        missing_fields = required_fields - set(reader.fieldnames or ())
        if missing_fields:
            raise ValueError(f"Dataset is missing columns: {sorted(missing_fields)}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"Dataset contains no samples: {path}")
    return rows


def sensor_updates(row: Dict[str, str]) -> Iterable[tuple[str, Dict[str, Any]]]:
    yield "device1", {
        "zone_person_count": int(row["device1_zone_person_count"]),
        "total_person_count": int(row["device1_zone_total_count"]),
    }
    yield "device2", {"weight_kg": float(row["device2_weight_kg"])}
    yield "device4", {
        "is_rotating": _boolean(row, "device4_is_rotating"),
        "speed_rpm": float(row["device4_speed_rpm"]),
    }
    yield "device5", {"distance_cm": float(row["device5_distance_cm"])}
    yield "device3", {
        "beam_blocked": _boolean(row, "device3_beam_blocked"),
    }


def send_sample(client: httpx.Client, base_url: str, row: Dict[str, str]) -> None:
    sample_id = row["sample_id"]
    for device_id, payload in sensor_updates(row):
        response = client.post(
            f"{base_url}/api/devices/{device_id}/data",
            json=payload,
        )
        response.raise_for_status()
        result = response.json()
        handoff = result.get("handoff", {})
        print(
            f"[{sample_id}] {device_id}: HTTP {response.status_code}; "
            f"Layer2 success={handoff.get('success')} "
            f"RSC={handoff.get('x_m2m_rsc')}",
            flush=True,
        )

        if device_id == "device3":
            risk_assessment = result.get("risk_assessment")
            risk_handoff = result.get("risk_handoff")
            if not isinstance(risk_assessment, dict) or not isinstance(
                risk_handoff, dict
            ):
                raise RuntimeError(
                    "MEC did not return an ML risk handoff. "
                    "Restart it with the latest application code."
                )
            if not risk_handoff.get("success"):
                raise RuntimeError(f"Device6 handoff failed: {risk_handoff}")
            print(
                f"[{sample_id}] ML={risk_assessment['risk_level']}; "
                f"triggered={result['triggered']}; "
                f"Device6 success={risk_handoff['success']} "
                f"RSC={risk_handoff.get('x_m2m_rsc')}",
                flush=True,
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Continuously send mock sensor rows to MEC without sending "
            "the dataset's risk_level labels."
        )
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Send only the first dataset sample, then exit.",
    )
    args = parser.parse_args()
    if args.interval_seconds < 0:
        parser.error("--interval-seconds must be non-negative")

    base_url = args.base_url.rstrip("/")
    rows = load_mock_rows()
    with httpx.Client(timeout=30.0, trust_env=False) as client:
        health = client.get(f"{base_url}/health")
        health.raise_for_status()
        print(f"MEC healthy at {base_url}; Ctrl+C to stop.", flush=True)

        try:
            while True:
                for row in rows:
                    retry_delay = max(args.interval_seconds, 1.0)
                    while True:
                        try:
                            send_sample(client, base_url, row)
                            break
                        except (httpx.HTTPError, RuntimeError) as exc:
                            print(
                                f"[{row['sample_id']}] Send failed: {exc}; "
                                f"retrying in {retry_delay:g}s.",
                                flush=True,
                            )
                            time.sleep(retry_delay)
                            retry_delay = min(retry_delay * 2, 30.0)
                    if args.once:
                        return
                    time.sleep(args.interval_seconds)
        except KeyboardInterrupt:
            print("\nMock data sender stopped.", flush=True)


if __name__ == "__main__":
    main()
