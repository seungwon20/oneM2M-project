# PinchGuard Dashboard — Monitoring Web Application

**Component:** Computer B / Monitoring node  
**Project guide:** [PinchGuard](../README.md)

The dashboard contains a [FastAPI backend](app.py), [vanilla JavaScript frontend](static/app.js) and [CSS](static/styles.css), with local event storage and remote oneM2M polling through the **local IN-CSE**.

## Features implemented in this branch

- Operator dashboard showing sensor/risk conditions, visualizations, event history and event acknowledgements.
- Device1–6 polling via SP-relative requests sent to `PG_IN_CSE_URL`, then forwarded by IN-CSE to the registered MN-CSE.
- A background polling worker (default **10 seconds**) and a cached `/api/onem2m/devices` result; individual device failures are isolated.
- Separate data freshness calculations; successful remote GET is not automatically interpreted as current telemetry.
- `POST /api/sensor`, `POST /api/risk`, `POST /api/frame`, `POST /notify`, demo controls and local SQLite event storage.
- Optional synthetic camera sender; not a validated real worker detection or physical safety implementation.

## Development run (WSL / Linux)

From the **Dashboard directory**:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `PG_INGEST_KEY`, `PG_IN_CSE_ORIGIN`, `PG_MN_CSE_ID` and the six resource identifiers; use the local IN-CSE URL when running both on Computer B. **The source backend reads environment variables; export those values before starting the app**:

```bash
set -a
source .env
set +a
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1
```

Using a single Uvicorn worker avoids starting duplicate background pollers in the development configuration. The two-node **release package** provides its own `configure-monitoring` and `start-monitoring` commands and does not require this developer venv.

## Check the service

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/api/onem2m/devices
```

The second response describes the **cached polling result** and its configured/connected/device status; it does not cause an immediate network read on every request.

| Configuration | Default in `.env.example` |
|:--|:--|
| `PG_IN_CSE_URL` | `http://127.0.0.1:3001` |
| `PG_MN_CSE_POLL_SECONDS` | `10` |
| `PG_MN_CSE_FRESH_SECONDS` | `30` |
| `PG_IN_CSE_TIMEOUT` | `3` seconds |
| `PG_ENABLE_DEMO`, `PG_DEMO_SEED` | `0` for the release-style non-demo configuration |

## Tests

```bash
cd Dashboard
source .venv/bin/activate
python -m pip install -r requirements-test.txt
python -m pytest -q tests
```

These tests cover API logic, mock notification routing, synthetic inputs and **mocked** IN-CSE responses. They cannot independently certify remote MN-CSE registration, two-computer connectivity or production safety.

For the synthetic CRITICAL risk demonstration, see [`README_CRITICAL.md`](README_CRITICAL.md). For the exact remote CSE query route and expected settings, see [`README_MN_CSE_INTEGRATION.md`](README_MN_CSE_INTEGRATION.md). These documents describe different modes; a rule-based demo threshold is **not** the AI-AE classifier's learned decision boundary.

**Relevant files:** [`app.py`](app.py) · [`camera_sender.py`](camera_sender.py) · [`tests/test_api.py`](tests/test_api.py) · [`tests/test_auto_sender.py`](tests/test_auto_sender.py).
