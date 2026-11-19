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

```powershell
python -m pip install -r requirements.txt
python -m uvicorn mec_safety.app:app --host 0.0.0.0 --port 8001
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

```powershell
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
- The ML sensor-flow smoke test is `pytest -q tests\test_sensor_trigger_engine.py`; it sends
  sensor requests without risk labels and exercises the packaged classifier.
- A read-only CSE check is available with `python tests\check_cse_connection.py`. It checks
  configuration, TCP, CSE Base retrieval, and the six configured FCNTs using GET only.
- The CSE and all six FCNT GET requests were reachable in the latest check. The server
  returned specialized `eg:Device1` through `eg:Device6` wrappers.

# Option C 기반 아키텍처 적용 및 구성 요소 선택 사유

## 1. 아키텍처 선정 배경

본 시스템은 ETSI GR MEC-DEC 050에서 제시하는 Deployment Option C를 기본 아키텍처로 선정하였다.

Option C는 MEC Platform과 oneM2M MN-CSE를 동일한 물리적 Edge Node에 배치하는 구조로, 두 플랫폼 간 불필요한 데이터 이동과 정보 교환을 줄이고 Edge 환경에서 데이터를 처리할 수 있다는 특징이 있다.

본 시스템 역시 MEC 환경 내에서 AI Application과 oneM2M CSE를 운영하며, AI Application이 외부 기기로부터 데이터를 수신하고 분석한 후 필요한 데이터를 CSE에 전달하는 구조이므로 Option C의 배치 방식과 부합한다.

다만 Option C에 제시된 모든 구성 요소와 기능을 그대로 적용하지는 않았다. 본 시스템의 실제 기능과 구현 범위를 고려하여 필요한 구성 요소만 반영하였다.

## 2. 구성 요소 및 기능의 제외 사유

### 2.1 다수의 AE(Application Entity) 구성 제외

Option C에서는 Swarm Computing, Federated Learning, 3rd Party IPE 등 여러 MN-AE를 개별 애플리케이션으로 구성하고 있다.

그러나 본 시스템에서는 여러 애플리케이션이 각각 독립적으로 서비스를 수행하는 구조가 아니라, 하나의 AI Application이 여러 기기로부터 데이터를 수신하고 AI 분석 및 판단을 수행한다.

따라서 다수의 AE를 별도로 구성하지 않고, 단일 AI Application을 MN-AE로 구성하였다.

### 2.2 Swarm Computing 및 Federated Learning 기능 제외

Option C에 포함된 Swarm Computing과 Federated Learning은 여러 Edge 환경 또는 애플리케이션 간의 협력적 연산 및 분산 학습을 지원하기 위한 구성 요소이다.

본 시스템의 목적은 단일 MEC 환경에서 수집한 기기 데이터를 AI Application이 분석하고, 그 결과를 oneM2M CSE에 저장하는 것이다.

따라서 다중 Edge 간 협력 연산이나 분산 모델 학습을 수행하지 않으므로 해당 기능들은 구현 범위에서 제외하였다.

### 2.3 별도의 3rd Party IPE 구성 제외

Option C에는 Non-oneM2M Device와 oneM2M 플랫폼 사이의 연동을 담당하는 3rd Party IPE가 별도의 MN-AE로 표현되어 있다.

본 시스템에서는 하나의 AI Application이 외부 기기로부터 데이터를 직접 수신하고, 해당 데이터를 분석하여 필요한 원본 데이터와 분석 결과를 oneM2M CSE에 전달한다.

이에 따라 기기 데이터 수신 및 처리 기능을 AI Application에서 담당하도록 구성하였으며, 별도의 3rd Party IPE 애플리케이션은 분리하여 구성하지 않았다.

단, AI Application 내부에서 기기별 프로토콜을 oneM2M 리소스 구조로 변환하거나 기기 기능과 리소스 간 동기화를 수행하는 경우에는 해당 내부 기능을 IPE의 역할로 구분할 수 있다.

### 2.4 oneM2M Device 및 MEC Device 구성 제외

본 시스템에서 데이터를 제공하는 외부 기기들은 oneM2M 표준을 직접 지원하지 않는 Non-oneM2M Device로 구성된다.

따라서 oneM2M Device 및 MEC Device를 별도 구성 요소로 포함하지 않았다. 각 기기의 데이터는 기기별 통신 방식에 따라 AI Application으로 전달되며, AI Application이 필요한 데이터를 선별하여 CSE에 저장한다.

### 2.5 Cloud IN-CSE 및 IN-AE 구성 제외

본 구현 범위에서는 Cloud에 별도의 IN-CSE를 구축하여 Edge MN-CSE와 연동하는 중앙 집중형 서비스 관리 및 데이터 동기화 기능을 구현하지 않는다.

따라서 Cloud IN-CSE와 IN-AE 및 이들 사이의 Mcc 연동은 현재 구현 아키텍처에서 제외한다.

※ 추후 Cloud 기반 oneM2M 플랫폼과 연동하거나 다수의 Edge CSE 간 데이터 동기화 및 관리가 필요한 경우 해당 구성을 확장할 수 있다.

## 3. 최종 아키텍처 구성

본 시스템은 Option C의 기본적인 배치 구조를 유지하면서 실제 구현에 필요한 구성 요소만 적용하였다.

- **Non-oneM2M Device:** 외부 데이터를 제공하는 다수의 기기
- **AI Application (MN-AE):** 기기 데이터 수신, AI 분석 및 판단, 저장 대상 데이터 선별
- **oneM2M MN-CSE:** Container 및 ContentInstance를 통한 기기별 원본 데이터와 AI 분석 결과 관리
- **MEC Platform:** MEC 환경 및 관련 서비스 기능 제공

AI Application과 MN-CSE는 동일한 MEC 환경에 배치하되, 별도의 실행 구성 요소로 운영한다. AI Application은 Mca를 통해 MN-CSE에 접근하며, 기기별 데이터를 Container에 구분하여 저장하고 실제 데이터는 ContentInstance로 관리한다.

결과적으로 본 시스템은 Option C를 기반으로 하되, 다중 AE, 분산 연산 및 학습 기능, 별도의 IPE 애플리케이션 등 현재 구현 목적에 필요하지 않은 요소를 제외한 단순화된 MEC-oneM2M 연동 구조로 설계하였다.