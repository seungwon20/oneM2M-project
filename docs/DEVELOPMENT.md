# 개발 가이드

## 개발 환경

개발 및 네이티브 빌드 환경은 WSL Ubuntu/Linux입니다. MN-CSE, IN-CSE, AI-AE, Dashboard와
테스트는 WSL Python/GCC를 사용합니다. Windows Python이나 PowerShell을 빌드 및 테스트에
사용하지 않습니다.

```bash
sudo apt-get update
sudo apt-get install -y build-essential pkg-config libssl-dev libwebsockets-dev python3-venv
```

현재 checkout이 `/mnt/c/`에 있으면 C 빌드와 파일 접근이 느릴 수 있습니다. 새 clone은
`~/projects/oneM2M-project` 등 WSL Linux 파일시스템 위치를 권장합니다. 기존 작업 디렉터리를
임의로 이동하거나 덮어쓰지 않습니다.

## 저장소와 컴포넌트 상태

AI-AE, TinyIoT MN-CSE, TinyIoT IN-CSE 및 PinchGuard Dashboard 소스가 저장소에 통합되어
있습니다. 단일 MEC를 기준으로 Computer A에는 AI-AE+MN-CSE, Computer B에는 IN-CSE+Dashboard를
배치합니다. IN-CSE 등록과 Dashboard의 원격 조회 경로는 구현되어 있지만, 별도 컴퓨터 간
실제 LAN 통합은 아직 검증 완료로 간주하지 않습니다.

## 컴포넌트 개발 원칙

### AI-AE

| 파일/모듈 | 역할 |
|---|---|
| `mec_safety/app.py` | FastAPI application과 센서 endpoint |
| `mec_safety/device_schemas.py` | sensor payload validation |
| `mec_safety/storage.py` | 프로세스 메모리의 최신 device 값 |
| `mec_safety/sensorTriggerEngine.py` | trigger 조건과 ML 위험도 추론 |
| `mec_safety/layer2.py` | oneM2M HTTP 업데이트 |
| `mec_safety/config.py` | root `.env` 설정 및 FlexContainer 구성 |
| `mec_safety/demo_plc_client.py`, `demo_plc_server.py` | 선택적 PLC demo 경로 |

- 입력 schema는 `device_schemas.py`, 출력 리소스 schema는 Seed DB와 같이 변경/검증합니다.
- 모델 추론은 trigger 조건 및 최신 device 상태에 의존하므로 테스트에서 입력 조건을 명시합니다.
- CSE update 결과와 AI-AE HTTP 응답 결과를 구분합니다.
- mock dataset/model은 데모 목적으로만 사용하며 인증된 산업 안전 시스템으로 표현하지 않습니다.

### MN-CSE / IN-CSE

- `data.db`는 초기 Seed DB이며 직접 수정하지 않습니다. runtime 데이터는 `runtime/`에 둡니다.
- `scripts/build.py`는 root `.env`를 읽고 설정/seed schema를 확인한 후 header와 실행 파일을
  생성합니다. 생성 파일을 직접 편집하지 않습니다.
- `TINYIOT_SERVER_IP`/`IN_CSE_SERVER_IP`는 POA 광고 주소이며 listener bind 주소와 다릅니다.
- MEC MN-CSE의 Remote CSE endpoint는 프로세스 환경에서 읽으며, 등록 실패가 로컬 CSE 기동을
  막지 않도록 재시도합니다.
- IN-CSE forwarding을 테스트할 때 CSE ID, Base name, SP ID, RVI, POA와 access-control을
  양쪽 설정 및 Seed DB와 대조합니다.

### Dashboard

- Live 조회는 Dashboard Backend → 같은 Monitoring Node의 IN-CSE → 등록된 MN-CSE 경로입니다.
- Dashboard가 직접 MN-CSE 주소를 조립하거나 다른 컴퓨터의 loopback을 사용하지 않습니다.
- UI의 stale/unavailable 상태와 실제 수신 timestamp를 구분합니다.
- SQLite, 로그, camera upload 등 runtime 파일은 소스 및 패키지 코드와 분리합니다.

## AI-AE 개발 및 테스트

```bash
cd AI-AE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

MN-CSE 및 root `.env`를 준비한 뒤 실제 연결 확인:

```bash
python tests/check_cse_connection.py
```

이 checker는 CSE Base와 Device1~Device6 조회를 수행합니다. 단위 테스트의 MockTransport 결과와
실제 CSE 통신 결과를 혼동하지 않습니다.

## MN-CSE 개발/실행

프로젝트 루트에서:

```bash
python3 MN-CSE/scripts/build.py --init-local-env
# root .env에서 제공되지 않는 필수 ID 및 SP ID를 설정
python3 MN-CSE/scripts/build.py
python3 MN-CSE/scripts/run.py
```

`--init-local-env`는 root `.env`의 통합 개발 기본값을 준비합니다. 필수 AE Originator,
Seed Resource ID 및 SP ID는 환경의 올바른 값으로 준비해야 합니다. 빌드는 해당 값이 Seed DB와
일치하는지 검사합니다. 기존 `MN-CSE/runtime/data.db`는 재실행 시 Seed DB로 덮어쓰지 않습니다.

## IN-CSE 개발/실행

root `.env`에 IN-CSE 설정을 준비합니다. 다음 명령은 IN-CSE 설정을 검증하고 `config.h`를
생성한 뒤 빌드합니다.

```bash
python3 IN-CSE/scripts/build.py
python3 IN-CSE/scripts/run.py
```

IN-CSE는 standalone 실행이 가능하며 MEC가 아직 접속할 수 없어도 listener 자체는 기동할 수
있습니다. 외부 요청의 end-to-end forwarding은 등록된 Remote CSE와 도달 가능한 POA가 있어야
검증됩니다. 생성된 `IN-CSE/config.h`, `server` 및 runtime 파일은 소스 변경으로 취급하지
않습니다.

## Dashboard 개발/테스트

```bash
cd Dashboard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-camera.txt -r requirements-test.txt
python -m pytest -q
```

Dashboard 설정은 환경변수로 전달됩니다. 로컬 실행을 할 때는 `Dashboard/.env.example`을
참고해 필요한 값을 shell 환경에 설정합니다. Dashboard의 live CSE 조회는 IN-CSE 설정과
원격 MN-CSE 등록이 유효할 때만 통합 검증할 수 있습니다.

## 패키지 개발/테스트

빌드 요구사항과 독립된 venv를 사용합니다.

```bash
python3 -m venv packaging/mec/.venv
source packaging/mec/.venv/bin/activate
python -m pip install -r packaging/mec/requirements-build.txt
python packaging/mec/build_package.py --help
```

```bash
python3 -m venv packaging/monitoring/.venv
source packaging/monitoring/.venv/bin/activate
python -m pip install -r packaging/monitoring/requirements-build.txt
python packaging/monitoring/build_package.py --help
```

실제 패키지 생성은 각각 루트 `.env`의 구성과 Seed DB를 사용하고, 새 출력 경로가 필요합니다.
`packaging/mec/tests/`와 `packaging/monitoring/tests/`의 controller 테스트는 AI-AE venv 등
pytest 및 필요한 모듈이 설치된 WSL 환경에서 실행합니다. 패키지 생성 성공만으로 깨끗한 장비
설치나 두 노드 네트워크 통신이 검증되는 것은 아닙니다.

## 통합 검증

개발 통합 테스트는 프로젝트 루트에서 실행합니다.

```bash
bash scripts/verify-mec.sh
```

MN-CSE, AI-AE 및 필요한 Mock PLC가 이미 실행 중이어야 합니다. 스크립트는 서비스를 종료하거나
DB를 초기화하지 않지만 Mock Sensor 송신은 runtime DB를 변경합니다. 실제 모델이 CRITICAL을
예측하지 않으면 PLC STOP 결과는 미검증으로 둡니다.

## Git 작업 방식과 민감 정보

- 변경 전 `git status --short`를 확인하고 이미 존재하는 작업을 보존합니다.
- `.env`, runtime DB, Dashboard SQLite, 생성된 `config.h`, 바이너리, 로그 및 `.venv`를 커밋하지
  않습니다.
- 실제 주소, Originator, Resource ID, ingest key 및 인증정보를 문서/로그/issue에 출력하지
  않습니다.
- 변경 범위에 맞는 단위 테스트와 빌드를 수행하며 실행하지 않은 결과를 성공으로 보고하지
  않습니다.
