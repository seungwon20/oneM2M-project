from __future__ import annotations

import csv
import random
from pathlib import Path

OUTPUT_PATH = Path(__file__).resolve().parent / "mock_sensor_dataset.csv"
RANDOM_SEED = 42
SAMPLES_PER_CLASS = 50
LABELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def label_from_safety_heuristic(
    zone_person_count: int,
    zone_total_count: int,
    speed_rpm: float,
    distance_cm: float,
) -> tuple[str, int]:
    """Create transparent synthetic labels for a demo dataset.

    This is a mock labeling heuristic, not an industrial safety standard.
    """
    if zone_person_count == 0:
        return "LOW", 0

    proximity_points = (
        3 if distance_cm <= 20 else
        2 if distance_cm <= 40 else
        1 if distance_cm <= 75 else 0
    )
    speed_points = (
        3 if speed_rpm >= 1100 else
        2 if speed_rpm >= 750 else
        1 if speed_rpm >= 350 else 0
    )
    occupancy_points = 2 if zone_person_count >= 3 else 1
    crowding_points = 1 if zone_total_count >= 5 else 0

    score = proximity_points + speed_points + occupancy_points + crowding_points
    if score <= 2:
        level = "LOW"
    elif score <= 4:
        level = "MEDIUM"
    elif score <= 6:
        level = "HIGH"
    else:
        level = "CRITICAL"
    return level, score


def generate_rows() -> list[dict[str, object]]:
    rng = random.Random(RANDOM_SEED)
    rows: list[dict[str, object]] = []
    counts = {label: 0 for label in LABELS}
    attempts = 0
    max_attempts = 1_000_000

    # All rows represent snapshots that passed the trigger gate:
    # device3.beam_blocked == True and device4.is_rotating == True.
    while any(counts[label] < SAMPLES_PER_CLASS for label in LABELS):
        attempts += 1
        if attempts > max_attempts:
            raise RuntimeError(f"Could not generate balanced dataset: {counts}")

        zone_person_count = rng.randint(0, 3)
        zone_total_count = rng.randint(zone_person_count, 8)
        weight_kg = round(rng.uniform(42.0, 115.0), 1)
        speed_rpm = round(rng.uniform(50.0, 1500.0), 1)
        distance_cm = round(rng.uniform(5.0, 180.0), 1)

        risk_level, _ = label_from_safety_heuristic(
            zone_person_count=zone_person_count,
            zone_total_count=zone_total_count,
            speed_rpm=speed_rpm,
            distance_cm=distance_cm,
        )
        if counts[risk_level] >= SAMPLES_PER_CLASS:
            continue

        sample_no = sum(counts.values()) + 1
        rows.append({
            "sample_id": f"sample_{sample_no:03d}",
            "device1_zone_person_count": zone_person_count,
            "device1_zone_total_count": zone_total_count,
            "device2_weight_kg": weight_kg,
            "device3_beam_blocked": True,
            "device4_is_rotating": True,
            "device4_speed_rpm": speed_rpm,
            "device5_distance_cm": distance_cm,
            "risk_level": risk_level,
        })
        counts[risk_level] += 1

    rng.shuffle(rows)
    # Re-number after shuffling so the IDs follow the CSV row order.
    for index, row in enumerate(rows, start=1):
        row["sample_id"] = f"sample_{index:03d}"
    return rows


def main() -> None:
    rows = generate_rows()
    columns = list(rows[0].keys())
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows)} rows: {OUTPUT_PATH}")
    print("Label counts:")
    for label in LABELS:
        print(f"  {label}: {sum(row['risk_level'] == label for row in rows)}")


if __name__ == "__main__":
    main()
