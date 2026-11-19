# Dashboard ↔ IN-CSE ↔ MN-CSE

The Dashboard does not contact the MEC MN-CSE directly. Its backend polls the
Monitoring Node's IN-CSE, which forwards oneM2M requests to the registered
remote MN-CSE.

## Configuration

In the default topology the Dashboard and IN-CSE run on the same Monitoring
Node, so `PG_IN_CSE_URL=http://127.0.0.1:3001` is appropriate. Configure the
registered MN-CSE identifier and a Dashboard originator permitted by the
IN-CSE access-control policy. If the Dashboard is intentionally moved to a
different host from IN-CSE, use a routable IN-CSE address instead. The MEC
MN-CSE is reached through IN-CSE forwarding; its POA must be routable from the
Monitoring Node and must not advertise MEC loopback.

The polling request uses the oneM2M SP-relative path:

```text
GET /~/<MN-CSE-ID>/Device1
X-M2M-Origin: <Dashboard originator>
X-M2M-RVI: <configured RVI>
```

`Device1` through `Device6` are queried independently. A failed request for one
device does not hide the other results. The source timestamp is used to
calculate freshness; successful polling does not imply fresh sensor data.

## Local development

```bash
cd Dashboard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
set -a
source .env
set +a
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1
```

The single worker avoids duplicate background pollers. Verify the app with
`curl -fsS http://127.0.0.1:8000/health` and the CSE polling status with
`curl -fsS http://127.0.0.1:8000/api/onem2m/devices`.

The API tests mock the oneM2M response. They do not prove registration,
forwarding, or cross-computer network connectivity; those require a live
Monitoring Node and MEC Node.
