# PinchGuard Automated Risk Scenario — Including CRITICAL

## Changes

- Expanded the original three-level risk classification (**SAFE / WARNING / HIGH**) to **four levels (SAFE / WARNING / HIGH / CRITICAL)**.
- Retained **UNKNOWN** as a separate state for missing, insufficient, or invalid sensor and assessment data.
- Updated the automated demonstration sequence to **SAFE → WARNING → HIGH → CRITICAL → HIGH → WARNING → SAFE**.
- Updated the automated sender, FastAPI endpoints (`/api/risk`, `/api/demo`, and `/notify`), web UI, and SQLite statistics.
- Added separate event counts for HIGH and CRITICAL (`stats.high_events` and `stats.critical_events`).
- Added a **CRITICAL** demonstration button and distinguished the highest risk level with magenta and deep-red visual indicators.

## Running the Demo (WSL Ubuntu)

### Terminal 1 — Start the Dashboard

```bash
cd /mnt/c/Users/minea/desktop/PinchGuard_Dashboard_CRITICAL
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-camera.txt
export PG_INGEST_KEY='local-dev-change-me'
uvicorn app:app --host 127.0.0.1 --port 8000
```

### Terminal 2 — Start the Synthetic Data Sender

```bash
cd /mnt/c/Users/minea/desktop/PinchGuard_Dashboard_CRITICAL
source .venv/bin/activate
export PG_API_KEY='local-dev-change-me'
python camera_sender.py --source synthetic --url http://localhost:8000/api/frame --fps 10 --cycle-seconds 24
```

Open **http://localhost:8000** in a Windows browser. If another server is already using port `8000`, stop it before starting this version.

For a faster demonstration cycle, change `--cycle-seconds 24` to `--cycle-seconds 12`.

## Demonstration Risk Classification Criteria

> **These are illustrative, rule-based criteria for a simulated demonstration, not validated industrial safety thresholds.**

| Risk level | Example condition |
|---|---|
| **CRITICAL** | Machinery operating + worker present + photoelectric beam interrupted + distance ≤ 20 cm |
| **HIGH** | Machinery operating + worker present + (photoelectric beam interrupted **or** distance ≤ 45 cm), excluding CRITICAL conditions |
| **WARNING** | Machinery operating + worker present + distance ≤ 105 cm, excluding higher risk levels |
| **SAFE** | Normal demonstration state that does not meet any of the above risk conditions |
| **UNKNOWN** | Required sensor data is missing, or the assessment result is no longer valid |

## Limitations

The video, sensor measurements, and risk values are generated through a **rule-based synthetic simulation**. A CRITICAL classification does **not** demonstrate detection of a real machinery entrapment incident or the ability to stop physical industrial equipment.

**Repository note:** The commands above preserve the original local WSL directory path. When running from the `integration/in-cse-dashboard` branch, use the repository's `Dashboard/` directory instead and configure the required environment variables for that setup.
