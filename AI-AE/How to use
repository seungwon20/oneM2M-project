# AI-AE / TinyIoT: Running the System on WSL

Run all commands in **Bash within the same WSL Ubuntu environment**. Do not use Windows Python or PowerShell.

When opening a new terminal, first navigate to the project root before running commands such as `cd AI-AE`.

| Component | Port | Description |
|---|---:|---|
| TinyIoT MN-CSE | 3000 | oneM2M HTTP endpoint |
| AI-AE | 8001 | FastAPI sensor API |
| Mock PLC | 9001 | Optional STOP-operation simulation |

## 1. Start the MN-CSE

Prepare the project-root `.env` configuration and build the MN-CSE. Keep the server terminal running.

```bash
python3 MN-CSE/scripts/build.py
python3 MN-CSE/scripts/run.py
```

The `run.py` script copies the seed database only when the runtime database does not already exist. An existing runtime database is preserved, and the seed database is not modified directly.

## 2. Set Up the AI-AE Virtual Environment

Open another WSL terminal, navigate to the project root, and then enter the `AI-AE` directory.

```bash
cd AI-AE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 3. Start the Mock PLC and AI-AE

To test the **CRITICAL STOP** behavior, start the Mock PLC first in a separate terminal.

```bash
cd AI-AE
source .venv/bin/activate
python -m mec_safety.demo_plc_server
```

Start AI-AE in another WSL terminal.

```bash
cd AI-AE
source .venv/bin/activate
python -m uvicorn mec_safety.app:app --host 127.0.0.1 --port 8001
```

## 4. Check Connectivity, Send Sensor Data, and Run Tests

Check the AI-AE health endpoint:

```bash
curl -fsS http://127.0.0.1:8001/health
```

Check the MN-CSE Base and retrieve Device1–Device6:

```bash
cd AI-AE
source .venv/bin/activate
python tests/check_cse_connection.py
```

Send mock sensor data once. **This operation updates the MN-CSE runtime database.**

```bash
cd AI-AE
source .venv/bin/activate
python -m mec_safety.send_mock_data --once
```

For continuous transmission, use `--interval-seconds 1` instead of `--once`.

Run the unit tests:

```bash
cd AI-AE
source .venv/bin/activate
python -m pytest -q
```

To shut down MN-CSE, AI-AE, and the Mock PLC, press **Ctrl+C** in each terminal where the corresponding process is running.
