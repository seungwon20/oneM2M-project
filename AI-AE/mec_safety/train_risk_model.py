from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

BASE_DIR = Path(__file__).resolve().parent
DATASET_PATH = BASE_DIR / "mock_sensor_dataset.csv"
MODEL_PATH = BASE_DIR / "risk_model.joblib"

# Keep the order identical to SensorTriggerEngine.FEATURE_COLUMNS.
FEATURE_COLUMNS = (
    "zone_person_count",
    "zone_total_count",
    "speed_rpm",
    "distance_cm",
)
LABELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
RANDOM_SEED = 42


def load_dataset() -> tuple[np.ndarray, np.ndarray]:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found: {DATASET_PATH}\n"
            "Run generate_mock_data.py first."
        )

    features: list[list[float]] = []
    targets: list[str] = []
    with DATASET_PATH.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        required = {
            "device1_zone_person_count",
            "device1_zone_total_count",
            "device4_speed_rpm",
            "device5_distance_cm",
            "risk_level",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Dataset is missing columns: {sorted(missing)}")

        for row in reader:
            features.append([
                float(row["device1_zone_person_count"]),
                float(row["device1_zone_total_count"]),
                float(row["device4_speed_rpm"]),
                float(row["device5_distance_cm"]),
            ])
            targets.append(row["risk_level"])

    if len(features) != 200:
        raise ValueError(f"Expected 200 samples, found {len(features)}")
    unexpected = set(targets) - set(LABELS)
    if unexpected:
        raise ValueError(f"Unexpected risk labels: {sorted(unexpected)}")
    if set(targets) != set(LABELS):
        raise ValueError("Every risk label must be present in the dataset")

    return np.asarray(features, dtype=np.float64), np.asarray(targets, dtype=str)


def main() -> None:
    X, y = load_dataset()
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=RANDOM_SEED,
        stratify=y,
    )

    evaluation_model = GradientBoostingClassifier(
        n_estimators=150,
        learning_rate=0.05,
        max_depth=2,
        random_state=RANDOM_SEED,
    )
    evaluation_model.fit(X_train, y_train)

    predictions = evaluation_model.predict(X_test)
    print("Test classification report:")
    print(classification_report(y_test, predictions, labels=LABELS, zero_division=0))
    print("Confusion matrix (rows=true, columns=predicted):")
    print(confusion_matrix(y_test, predictions, labels=LABELS))
    print("Label counts:", dict(Counter(y)))

    # After reporting the hold-out result, fit the deployed model on all 200 rows.
    final_model = GradientBoostingClassifier(
        n_estimators=150,
        learning_rate=0.05,
        max_depth=2,
        random_state=RANDOM_SEED,
    )
    final_model.fit(X, y)

    bundle = {
        "model": final_model,
        "feature_columns": FEATURE_COLUMNS,
        "labels": LABELS,
        "trigger_levels": ("HIGH", "CRITICAL"),
        "dataset_size": int(len(y)),
        "synthetic_data": True,
        "labeling_note": (
            "Rule-labeled mock data for software/demo validation only; "
            "not a validated industrial safety model."
        ),
    }
    joblib.dump(bundle, MODEL_PATH)
    print(f"Saved model: {MODEL_PATH}")


if __name__ == "__main__":
    main()
