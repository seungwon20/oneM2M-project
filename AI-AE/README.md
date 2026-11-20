# MEC Safety Application

This project contains Layer 1 and Layer 2 as in-process modules in one application. Layer 1
validates and stores each sensor update, then directly awaits Layer 2's internal method call.
Layer 2 maps the update to an existing FlexContainer and sends a oneM2M HTTP PUT. No separate
Layer 2 server, process, queue, or oneM2M AE registration is involved.

## Included behavior

- Receives sensor JSON payloads over HTTP
- Identifies the device by URL path (`device1` through `device5`)
- Validates the payload against the specification for each device
- Maintains only the latest valid value per device in memory
- Produces a partial or complete device snapshot
- Calls the Sensor Trigger Engine hook after validation/state update and before Layer 2
  sensor forwarding; the default engine predicts risk when device3 reports a blocked beam
  while device4 reports a rotating belt
- Uses the packaged classifier to infer a risk level from device1, device4, and device5 data;
  no risk label is required in sensor requests
- Sends each successful model prediction to the configured Device6 Risk FlexContainer;
  `triggered` remains true only for `HIGH` and `CRITICAL`
- Hands validated sensor updates directly to Layer 2, which maps each device to its configured FCNT
- Adds the MEC receive time as `received_at` to sensor FCNT updates and `evaluated_at` to risk
  updates, without changing the measurement fields or adding either timestamp to sensor input
- Exposes a separate risk-assessment handoff for caller-provided risk labels
- Uses oneM2M HTTP Binding PUT and checks HTTP status, `X-M2M-RSC`, and response `X-M2M-RI`
- Uses the CSE-confirmed resource wrappers `eg:Device1` through `eg:Device6`

## Run locally

Run the services and tests inside the same WSL Ubuntu distribution. From the project root:

```bash
cd AI-AE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Start the optional Mock PLC first in its own WSL terminal:

```bash
cd AI-AE
source .venv/bin/activate
python -m mec_safety.demo_plc_server
```

Then start AI-AE in another WSL terminal:

```bash
cd AI-AE
source .venv/bin/activate
python -m uvicorn mec_safety.app:app --host 127.0.0.1 --port 8001
```

## Layer 2 configuration

The CSE URL, Base Name, RVI, AE identity, and six Resource IDs are loaded from the project-root
`.env` by `mec_safety/config.py`. Layer 2 uses the resource-specific wrappers observed in the CSE
GET responses (`eg:Device1` through `eg:Device6`). Resource IDs are URL-encoded and
appended to the configured CSE URL. The application does not register the AE or create
resources.

The sensor HTTP body contains measurements only. Layer 1 captures the UTC receive time
after validation and passes it alongside the measurements through the in-process handoff.
Layer 2 adds that value as `received_at` to the CSE resource body. The separate risk
handoff similarly adds its UTC invocation time as `evaluated_at`. Latest-state snapshots
continue to contain only the original sensor measurement fields.

The trigger hook receives the device ID, current measurement, previous measurement (if any),
and a snapshot including the just-received value. Inference runs only for a `device3` update
with `beam_blocked: true` when the latest `device4` state has `is_rotating: true`. The model
uses the camera person counts, encoder speed, and distance measurement to predict `LOW`,
`MEDIUM`, `HIGH`, or `CRITICAL`; `triggered` is true for `HIGH` and `CRITICAL`. The latest
prediction and confidence are available in the in-process `SensorTriggerEngine` state and its
prediction is normalized to the Risk FCNT's title-case labels and sent to Device6 after the
sensor update succeeds. The sensor response includes `risk_assessment`, `risk_evaluated_at`,
and `risk_handoff` when inference ran. A failed risk handoff returns HTTP 502 and includes
both the successful sensor handoff and failed risk handoff details.
Valid sensor updates continue to Layer 2 regardless of whether a trigger is reported.

## HTTP endpoints

### Sensor ingestion

```http
POST /api/devices/device1/data
Content-Type: application/json

{"zone_person_count": 5, "total_person_count": 18}
```

### Latest device data

```http
GET /api/devices/device1
```

### Full snapshot

```http
GET /api/snapshot
```

### Risk-assessment handoff

```http
POST /api/risk-assessment
Content-Type: application/json

{"risk_level": "High", "speed_rpm": 86.5, "distance_cm": 42.8}
```

### Continuous mock sensor sender

With MEC running on port 8001, send the packaged CSV rows continuously, excluding each row's
`risk_level` label so the MEC model makes its own prediction:

```bash
cd AI-AE
source .venv/bin/activate
python -m mec_safety.send_mock_data --interval-seconds 1
```

The sender posts device1, device2, device4, device5, then device3 for each sample so the final
request triggers inference. Device6 risk forwarding is reported for each sample. These requests
use the configured Layer 2 connection and write to the real CSE; press `Ctrl+C` to stop. Use
`--once` to send just the first sample, or `--base-url` to select another MEC URL.

## Notes

- Layer 2 performs oneM2M UPDATE only; it does not perform AE registration, resource
  creation, retrieval, deletion, or direct database access.
- There is no database or time-series history storage.
- The packaged classifier was trained on synthetic rule-labeled mock data for software/demo
  validation only; its predictions and confidence are not validated industrial safety results.
- No request retries or custom timeout policy are configured.
- The application tests use HTTPX `MockTransport`; they do not send writes to tinyIoT.
- The ML sensor-flow smoke test is `python -m pytest -q tests/test_sensor_trigger_engine.py`; it sends
  sensor requests without risk labels and exercises the packaged classifier.
- A read-only CSE check is available with `python tests/check_cse_connection.py`. It checks
  configuration, TCP, CSE Base retrieval, and the six configured FCNTs using GET only.
- The CSE check reports Resource ID matches and schema results without printing values loaded
  from `.env`.

# Rationale for Adopting an Option C–Based Architecture and Selecting System Components

## 1. Background of Architecture Selection

This system adopts **Deployment Option C**, as presented in ETSI GR MEC-DEC 050, as its reference architecture.

Option C describes an architecture in which the MEC Platform and the oneM2M MN-CSE are deployed on the same physical Edge Node. This arrangement reduces unnecessary data transfers and information exchanges between the two platforms and enables data processing within the edge environment.

Similarly, the proposed system operates an AI Application and a oneM2M CSE within a MEC environment. The AI Application receives data from external devices, performs analysis, and forwards the necessary information to the CSE. Therefore, the system's deployment structure is consistent with the co-location approach presented in Option C.

However, not all components and functionalities described in Option C have been adopted. Instead, the architecture has been selectively adapted to reflect the actual requirements and implementation scope of the proposed system.

## 2. Rationale for Excluding Specific Components and Functionalities

### 2.1. Exclusion of Multiple Application Entities (AEs)

Option C illustrates several MN-AEs operating as independent applications, including Swarm Computing, Federated Learning, and third-party Interworking Proxy Entities (IPEs).

However, the proposed system does not require multiple independent applications to perform separate services. Instead, a single AI Application receives data from multiple devices and performs AI-based analysis and decision-making.

Accordingly, rather than deploying multiple AEs separately, the system employs a single AI Application as its MN-AE.

### 2.2. Exclusion of Swarm Computing and Federated Learning

Swarm Computing and Federated Learning, as illustrated in Option C, are intended to support collaborative computation and distributed model training across multiple edge environments or applications.

The primary objective of the proposed system is to collect device data within a single MEC environment, analyze the collected information using an AI Application, and store the resulting data in a oneM2M CSE.

Since the system does not perform collaborative computation across multiple edge nodes or distributed model training, these functionalities have been excluded from the current implementation scope.

### 2.3. Exclusion of a Separate Third-Party Interworking Proxy Entity (IPE)

Option C represents the third-party IPE as a separate MN-AE responsible for interoperability between Non-oneM2M Devices and the oneM2M platform.

In the proposed system, however, a single AI Application directly receives data from external devices, processes the received information, and forwards both the necessary original data and analysis results to the oneM2M CSE.

Therefore, device data acquisition and processing are handled within the AI Application, eliminating the need to deploy a separate third-party IPE application.

Nevertheless, if the AI Application internally performs functions such as translating device-specific protocols into oneM2M resource structures or synchronizing device functionalities with corresponding oneM2M resources, those internal functions may be identified as fulfilling the role of an IPE.

### 2.4. Exclusion of oneM2M Devices and MEC Devices

The external devices that provide data to the proposed system are classified as **Non-oneM2M Devices**, as they do not directly support the oneM2M standard.

Consequently, oneM2M Devices and MEC Devices have not been included as separate architectural components.

Data from each external device is transmitted to the AI Application through its respective communication mechanism. The AI Application then selects the necessary information and stores it in the CSE.

### 2.5. Exclusion of Cloud IN-CSE and IN-AE Components

The current implementation does not establish a separate cloud-based IN-CSE to provide centralized service management and data synchronization through integration with the edge MN-CSE.

Accordingly, the Cloud IN-CSE, IN-AE, and the associated Mcc interworking between these components have been excluded from the current implementation architecture.

If integration with a cloud-based oneM2M platform or centralized data synchronization and management across multiple edge CSEs become necessary, these components may be incorporated in future extensions.

## 3. Final Architecture Configuration

The proposed system preserves the fundamental deployment structure of Option C while incorporating only the components necessary for its actual implementation.

The final architecture consists of the following components:

- **Non-oneM2M Devices:** Multiple external devices responsible for providing input data.
- **AI Application (MN-AE):** Responsible for receiving device data, performing AI-based analysis and decision-making, and selecting the information to be stored.
- **oneM2M MN-CSE:** Responsible for managing device-specific original data and AI analysis results through Container and ContentInstance resources.
- **MEC Platform:** Provides the MEC execution environment and associated service functionalities.

The AI Application and MN-CSE are deployed within the same MEC environment while operating as separate execution components.

The AI Application accesses the MN-CSE through the **Mca reference point**, organizes device-specific information into separate Container resources, and manages individual data records as ContentInstance resources.

As a result, the proposed system adopts a simplified MEC–oneM2M integration architecture based on Deployment Option C. It retains the core co-location principle while excluding components that are unnecessary for the current implementation objectives, including multiple independent AEs, distributed computing and learning functionalities, and a separate IPE application.
