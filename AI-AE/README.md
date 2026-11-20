# AI-AE — Edge Sensor Processing and Risk Inference

**Component:** Computer A / MEC-oriented node  
**Project guide:** [PinchGuard](../README.md)

The AI Application Entity (AI-AE) is a **single FastAPI process** with Layer 1 input processing, an in-process Sensor Trigger Engine and Layer 2 oneM2M request handling. It does not start a separate Layer 2 server or automatically register an `m2m:ae` resource.

## Processing contract

1. Accept `POST /api/devices/{device_id}/data` for `device1` through `device5`.
2. Reject missing, extra or incorrectly typed sensor attributes ([`device_schemas.py`](mec_safety/device_schemas.py)).
3. Store the latest accepted measurement in process memory ([`storage.py`](mec_safety/storage.py)); an HTTP response is not a historical time-series store.
4. Call the Sensor Trigger Engine with the current/previous state and the updated snapshot.
5. On a **Device3 `beam_blocked=true`** update, if the latest **Device4 `is_rotating=true`**, run the packaged classifier using Device1 counts, Device4 speed and Device5 distance.
6. Optionally send a direct TCP STOP to the **Mock PLC** for a model-predicted `CRITICAL` actionable risk.
7. Forward validated sensor values to their fixed MN-CSE FlexContainers; if inference produced a risk result, forward title-cased risk values to Device6.

The classifier was trained on **200 synthetic, heuristic-labeled examples** and is not validated for industrial hazard detection. `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` are classifier outputs; the dashboard's SAFE/WARNING labels are a separate presentation concept.

## API

| Endpoint | Operation |
|:--|:--|
| `GET /health` | Process health |
| `POST /api/devices/device1/data` | Camera-derived worker counts |
| `POST /api/devices/device2/data` | Weight measurement |
| `POST /api/devices/device3/data` | Infrared beam update and possible inference trigger |
| `POST /api/devices/device4/data` | Encoder rotation and RPM |
| `POST /api/devices/device5/data` | Distance measurement |
| `GET /api/devices/{device_id}` | Latest in-memory reading |
| `GET /api/snapshot` | All currently known readings |
| `POST /api/risk-assessment` | Separate caller-provided risk handoff |

**Example** (development server started on port 8001):

```bash
curl -fsS -X POST 'http://127.0.0.1:8001/api/devices/device1/data' -H 'Content-Type: application/json' -d '{"zone_person_count":2,"total_person_count":5}'
```

Layer 2 sends oneM2M HTTP `PUT` using `eg:Device1`–`eg:Device6` wrappers, with `X-M2M-Origin`, `X-M2M-RI` and `X-M2M-RVI`. The success check requires **HTTP 200**, **`X-M2M-RSC: 2004`**, and a matching response request ID. The controller must be configured with already existing Resource IDs from the MN-CSE seed DB; it does not automatically discover or create them.

## Local WSL development

Prepare the project-root `.env` with the correct MN-CSE address and existing Resource IDs. Start the MN-CSE first.

```bash
cd AI-AE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn mec_safety.app:app --host 127.0.0.1 --port 8001
```

**In a separate AI-AE terminal:**

```bash
cd AI-AE
source .venv/bin/activate
python -m mec_safety.send_mock_data --once
```

This sender writes to the **actual configured CSE**, not a test-only database. For a continuous simulation use `python -m mec_safety.send_mock_data --interval-seconds 1` and stop with `Ctrl+C`.

**Optional Mock PLC:** start `python -m mec_safety.demo_plc_server` in a separate terminal before starting AI-AE to test the simulated STOP path.

## Verification

```bash
cd AI-AE
source .venv/bin/activate
python -m pytest -q
python tests/check_cse_connection.py
```

The Python tests use HTTPX MockTransport and therefore **do not write to TinyIoT**. The separate connection checker is read-only. For source-run integration see [`scripts/verify-mec.sh`](../scripts/verify-mec.sh) from the project root; its mock sender **does** modify the active CSE runtime DB.

## Implementation boundaries

- Timestamp fields (`received_at`, `evaluated_at`) are injected during forwarding, not supplied by the sensor sender.
- Layer 2 has no independent queue or database and no general retry/timeout policy. The mock sender may retry its own HTTP requests.
- The input cache does not guarantee a maximum age for every feature, and the optional PLC simulation is neither transactional with CSE writes nor a physical safety function.
- The released MEC package starts AI-AE and MN-CSE; the Mock PLC demo is a separate optional source-run component.

**Key source:** [`app.py`](mec_safety/app.py) · [`sensorTriggerEngine.py`](mec_safety/sensorTriggerEngine.py) · [`layer2.py`](mec_safety/layer2.py) · [`train_risk_model.py`](mec_safety/train_risk_model.py).

## Option C-inspired architecture rationale

The **co-location idea** is drawn from [ETSI GR MEC-DEC 050, Deployment Option C](https://www.etsi.org/deliver/etsi_gr/MEC-DEC/001_099/050/04.01.01_60/gr_MEC-DEC050v040101p.pdf). The implementation places the FastAPI AI-AE process and TinyIoT MN-CSE process together on **Computer A**, a MEC-*oriented* edge node. **It does not deploy or register with an operational ETSI MEC Platform.** The AI-AE communicates over oneM2M HTTP to seeded resources, but its code does **not** create/register an `m2m:ae` resource in the CSE.

### Why not deploy multiple MN-AEs?

Input validation, latest-state maintenance, sensor-triggered model invocation and oneM2M writes are implemented in **one** Python application, with separate MN-CSE and (optional) Mock PLC processes. There are no independently registered swarm-computing, federated-learning or third-party IPE AEs. A software module performing JSON → `eg:DeviceN` mapping offers an **interworking-like function**; this alone does not establish a complete oneM2M IPE implementation or a multi-protocol industrial gateway.

### Why omit swarm computing and federated learning?

The project uses a single Gradient Boosting model trained on synthetic demonstration data. It does not exchange model parameters among edge nodes, perform federated aggregation, or coordinate a distributed swarm. Those options are outside the implemented scope.

### What devices and resources are actually used?

Current inputs are **simulated non-oneM2M sensor measurements submitted over HTTP**; real production cameras, proprietary device-protocol adapters and MEC Devices have not been validated. Validated values update six specialized **SDT-based FlexContainers (type 28)** in the MN-CSE. This project does **not** write its primary sensor/risk values to a Container/ContentInstance time-series tree. The state in `MN-CSE/runtime/data.db` is the mutable resource store; the seed DB is only an initialization source.

### Is an IN-CSE included?

**Yes.** The integration branch contains a separately deployed **Monitoring Node (Computer B)** with TinyIoT IN-CSE and a Dashboard. The MN-CSE on Computer A has a Remote CSE registration/retry path; the Dashboard backend queries its local IN-CSE, which forwards oneM2M SP-relative GET requests to the registered MN-CSE POA. This is **not a Cloud IN-CSE deployment** and has not been verified on two physical hosts by the published local WSL/loopback test. Claiming that all IN-CSE/Mcc functionality was excluded is inaccurate.

### Selected elements and omissions

| Element | Selected implementation | Not claimed |
|:--|:--|:--|
| Edge AI-AE and MN-CSE co-location | Separate processes on Computer A; oneM2M HTTP PUT | MEC Platform orchestration or ETSI service-registration APIs |
| Data adapter | Application-side validation and `eg:DeviceN` mapping | Separate registered third-party IPE |
| Machine learning | One locally executed model with synthetic training data | Federated or distributed training |
| Device representation | Six predefined, schema-checked FlexContainers | Primary Container/ContentInstance history |
| Remote monitoring | IN-CSE and Dashboard on Computer B | Cloud IN-CSE, automatic handover or validated multi-host LAN |
| Emergency response | Direct TCP Mock PLC STOP simulator | Safety-certified physical actuator control |

The system should therefore be described as **an Option C-inspired, co-located MEC–oneM2M software prototype with a separate Monitoring IN-CSE**, not a complete realization of every Option C platform, AE, IPE or cloud capability. The main project's [architecture and configuration reference](../README.md#option-c-inspired-component-selection) describes the full two-node layout.
