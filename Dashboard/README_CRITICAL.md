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
cd Dashboard
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-camera.txt
export PG_INGEST_KEY='local-dev-change-me'
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

### Terminal 2 — Start the Synthetic Data Sender

```bash
cd Dashboard
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

The demo's generated visuals, sensor measurements, and risk values follow a **rule-based synthetic simulation**. The example thresholds below are *illustrative demonstration criteria*, **not** the trained AI-AE classifier's learned four-class decision boundary. The AI-AE writes `LOW / MEDIUM / HIGH / CRITICAL` model output into oneM2M Device6, while the dashboard demonstration uses the separate `SAFE / WARNING / HIGH / CRITICAL` presentation vocabulary. A CRITICAL classification does **not** demonstrate detection of a real machinery entrapment incident or the ability to stop physical industrial equipment.

**Running from GitHub:** Each `cd Dashboard` command assumes a fresh terminal opened at the root of a checkout of the `integration/in-cse-dashboard` branch. Use `cd <repository-root>/Dashboard` if your terminal starts elsewhere. The `PG_INGEST_KEY`/`PG_API_KEY` string above is an **unsafe example value for an isolated local demo only**. For network-accessible environments, use a unique secret and avoid exposing the demonstration API.

For real CSE-routed monitoring, refer to [the Dashboard README](README.md) and [the IN-CSE integration guide](README_MN_CSE_INTEGRATION.md); these are distinct from this local synthetic camera demo.
