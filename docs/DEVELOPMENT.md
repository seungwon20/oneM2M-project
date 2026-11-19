# 개발 가이드

## 개발 환경

개발 및 검증 환경은 WSL Ubuntu/Linux입니다. MN-CSE 빌드, AI-AE, Mock PLC, 검증 스크립트와
테스트를 같은 WSL 배포판에서 실행합니다. Windows Python이나 PowerShell은 사용하지 않습니다.

필요한 도구와 개발 라이브러리:

```bash
sudo apt-get update
sudo apt-get install -y build-essential pkg-config libssl-dev libwebsockets-dev python3-venv
```

현재 checkout이 `/mnt/c/`에 있으면 빌드와 설치가 느릴 수 있습니다. 새 clone은
`~/projects/oneM2M-project` 같은 WSL Linux 파일시스템 경로를 권장합니다. 기존 작업 디렉터리는
임의로 이동하지 않습니다.

## 저장소와 컴포넌트 상태

저장소에는 AI-AE와 TinyIoT MN-CSE 소스가 있습니다. Dashboard는 별도 개발 완료 상태이나
아직 저장소에 통합되지 않았습니다. 현재 통합은 단일 MEC, 고정 CSE Base 및 Resource ID를
기준으로 합니다.

## AI-AE 구조 및 개발 원칙

| 파일 또는 모듈 | 역할 |
|---|---|
| `mec_safety/app.py` | FastAPI application, HTTP endpoint, 요청 흐름 |
| `mec_safety/device_schemas.py` | device별 sensor payload 검증 |
| `mec_safety/storage.py` | 프로세스 메모리에 최신 device 값 보관 |
| `mec_safety/sensorTriggerEngine.py` | trigger 조건과 ML 위험도 추론 |
| `mec_safety/layer2.py` | oneM2M HTTP PUT |
| `mec_safety/config.py` | 환경변수와 FlexContainer 설정 |
| `mec_safety/demo_plc_client.py` | PLC TCP 클라이언트 |
| `mec_safety/demo_plc_server.py` | PLC 모의 서버 |
| `mec_safety/send_mock_data.py` | mock sensor 송신기 |
| `mec_safety/train_risk_model.py` | mock 데이터로 모델 생성 |
| `mec_safety/risk_model.joblib` | 데모 모델 |

- 실제 소스와 검증된 동작을 우선하고 계획/미구현 동작은 구분합니다.
- Sensor payload는 `device_schemas.py`의 field 규칙을 따릅니다.
- 모델 추론은 명시된 trigger 조건을 통과한 경우에만 수행합니다.
- CSE update 성공과 AI-AE 응답 성공 기준을 분리합니다.
- 민감한 `.env` 값을 테스트, 문서, 화면 출력 및 로그에 포함하지 않습니다.
- 데모 모델은 산업 안전 검증 모델로 표현하지 않습니다.
- Dashboard 내부 구현은 소스를 통합하기 전 추측하지 않습니다.

## AI-AE 가상환경 및 실행

프로젝트 루트에서 가상환경과 의존성을 준비합니다.

```bash
cd AI-AE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

프로젝트 루트 `.env`가 준비되어 있고 MN-CSE가 실행 중이어야 합니다. CRITICAL PLC 경로를
확인할 때는 첫 번째 터미널에서 Mock PLC를 먼저 시작합니다.

```bash
cd AI-AE
source .venv/bin/activate
python -m mec_safety.demo_plc_server
```

다른 WSL 터미널에서 AI-AE를 시작합니다.

```bash
cd AI-AE
source .venv/bin/activate
python -m uvicorn mec_safety.app:app --host 127.0.0.1 --port 8001 --reload
```

Health 확인:

```bash
curl -fsS http://127.0.0.1:8001/health
```

Mock Sensor 송신은 별도 터미널에서 수행합니다. 이 명령은 실제 runtime DB를 수정합니다.

```bash
cd AI-AE
source .venv/bin/activate
python -m mec_safety.send_mock_data --interval-seconds 1
```

중지는 실행 터미널에서 `Ctrl+C`를 누릅니다.

## API 수동 확인

아래 예시는 WSL shell에서 수행하며 현재 실행 중인 AI-AE에 센서 데이터를 POST합니다.

```bash
curl -fsS http://127.0.0.1:8001/health

curl -fsS -X POST http://127.0.0.1:8001/api/devices/device3/data \
  -H 'Content-Type: application/json' \
  -d '{"beam_blocked":true}'

curl -fsS http://127.0.0.1:8001/api/snapshot
```

device3 요청은 최신 device4 상태가 `is_rotating=true`일 때 위험도 추론 trigger 조건을 만족할
수 있습니다. 실제 trigger 상태에 따라 결과가 달라집니다.

## 테스트 및 CSE 검증

AI-AE 단위 테스트:

```bash
cd AI-AE
source .venv/bin/activate
python -m pytest -q
```

모델 흐름 관련 테스트만 실행하려면:

```bash
python -m pytest -q tests/test_sensor_trigger_engine.py
```

HTTPX `MockTransport` 기반 테스트는 실제 MN-CSE에 쓰지 않습니다. 실제 MN-CSE가 실행 중일 때
다음 checker는 CSE Base와 Device1~6에 대해 GET만 실행하고 RI/schema 일치 여부를 확인합니다.
출력에는 설정값을 표시하지 않습니다.

```bash
python tests/check_cse_connection.py
```

프로젝트 루트에서 MN-CSE build 검증 및 컴파일:

```bash
cd "$(git rev-parse --show-toplevel)"
python3 MN-CSE/scripts/build.py --init-local-env
python3 MN-CSE/scripts/build.py
```

첫 명령은 확인된 로컬 기본값을 설정하되 기존 Originator/Resource ID를 보존합니다. 필수
SP ID처럼 seed DB에서 얻을 수 없는 값은 `.env`에 직접 준비해야 합니다. 두 번째 명령은
환경설정, seed DB의 고정 Base/Resource ID 및 schema를 검증한 다음 빌드합니다.

MN-CSE 실행:

```bash
cd "$(git rev-parse --show-toplevel)"
python3 MN-CSE/scripts/run.py
```

`MN-CSE/data.db`는 seed이고 `MN-CSE/runtime/data.db`는 runtime database입니다. 기존 runtime DB는
다시 실행할 때 seed로 덮어쓰지 않습니다. `config.h` 및 `Makefile`은 생성 파일이며 직접 편집하거나
커밋하지 않습니다.

전체 MEC 통합 검증은 MN-CSE, AI-AE, Mock PLC가 실행 중일 때 루트에서 수행합니다.

```bash
cd "$(git rev-parse --show-toplevel)"
bash scripts/verify-mec.sh
```

스크립트는 서비스를 종료하거나 DB를 초기화하지 않습니다. Mock Sensor 전송으로 runtime DB가
변경됩니다. 모델이 예측한 CRITICAL 입력이 없으면 STOP 검증은 미실행으로 표시됩니다.

현재 확인하지 않은 결과는 통과로 기록하지 말고, 단위 테스트와 실제 서비스 통합 결과를
구분합니다.

## 모델 재학습

데이터 생성과 모델 학습은 데모 목적입니다. AI-AE 가상환경을 활성화한 상태에서:

```bash
cd AI-AE
source .venv/bin/activate
python -m mec_safety.generate_mock_data
python -m mec_safety.train_risk_model
```

학습은 `mock_sensor_dataset.csv`의 규칙 레이블을 사용해 `risk_model.joblib`을 갱신합니다.
산업 안전 결과를 대체하지 않으며, 재생성된 모델을 사용하는 경우 관련 테스트를 다시 실행합니다.

## Git 저장소 개발 방식

1. 작업 전 변경사항과 기존 문서 충돌을 확인합니다.
2. 기능별로 작고 검토 가능한 변경을 나눕니다.
3. `.env`, runtime DB, 빌드 산출물과 로컬 가상환경은 커밋하지 않습니다.
4. 코드 변경은 관련 최소 테스트와 빌드로 검증합니다.
5. 실제 구현, 검증 결과, 향후 계획을 문서에서 분리합니다.

루트 `.env`는 Git 추적 대상이 아닙니다. 민감한 값은 `git diff`, 로그, 문제 보고 및 문서에
붙이지 않습니다.

## 컴포넌트 통합 주의사항

- AI-AE payload와 TinyIoT Device1~Device6 FlexContainer schema를 함께 검증합니다.
- Resource ID는 기존 seed DB 기준으로 유지하고 build 검증에서 mismatch를 차단합니다.
- `MN-CSE/data.db`는 seed로 보존하고 서버는 `runtime/data.db`에서 실행합니다.
- `TINYIOT_SERVER_IP`는 POA 광고 주소이며 listener bind 주소 `0.0.0.0`과 구분합니다.
- Registrar/Remote CSE가 확정되기 전 관련 환경변수를 설정하지 않습니다.
- Dashboard 소스, 프레임워크, 포트, 실행 명령은 통합 후 실제 파일을 기준으로 문서화합니다.
