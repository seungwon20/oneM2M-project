# 개발 가이드

## 개발 환경 준비

현재 저장소에는 AI-AE와 TinyIoT MN-CSE 소스가 포함됩니다. Dashboard는 별도 개발 중이며
소스는 저장소에 없습니다. 통합은 단일 MEC, 고정 CSE Base/Resource ID 구성입니다.

권장 환경:

- Windows PowerShell 또는 현재 프로젝트에서 사용하는 터미널
- WSL/Linux에서 GCC, GNU Make, pkg-config, OpenSSL 및 libwebsockets 개발 파일
- Python 3 (AI-AE와 MN-CSE build/run 스크립트)

프로젝트 루트에서 가상환경을 사용하는 예:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r AI-AE\requirements.txt
```

MN-CSE의 embedded SQLite 구현은 SQLite 개발 package 설치를 요구하지 않지만,
컴파일 시 OpenSSL과 libwebsockets 링크가 필요합니다.

## AI-AE 구조

| 파일 또는 모듈 | 역할 |
|---|---|
| `mec_safety/app.py` | FastAPI application, HTTP endpoint, 요청 흐름 |
| `mec_safety/device_schemas.py` | device별 sensor payload 검증 |
| `mec_safety/storage.py` | 최신 device 값을 프로세스 메모리에 보관 |
| `mec_safety/sensorTriggerEngine.py` | trigger 조건과 ML 위험도 추론 |
| `mec_safety/layer2.py` | oneM2M HTTP PUT |
| `mec_safety/config.py` | 환경변수와 FlexContainer 설정 |
| `mec_safety/demo_plc_client.py` | PLC TCP 클라이언트 |
| `mec_safety/demo_plc_server.py` | PLC 모의 서버 |
| `mec_safety/send_mock_data.py` | mock sensor 송신기 |
| `mec_safety/train_risk_model.py` | mock 데이터로 모델 생성 |
| `mec_safety/risk_model.joblib` | 패키지된 데모 모델 |

## 개발 원칙

- 실제 소스와 확인된 동작을 우선합니다.
- Dashboard 내부 구현은 소스 통합 전 추측하지 않습니다.
- 센서 payload는 `device_schemas.py`의 exact field 규칙을 따릅니다.
- 최신 상태에는 추가 필드나 CSE 메타데이터를 넣지 않습니다.
- 모델 추론은 명시된 trigger 조건을 통과한 경우에만 수행합니다.
- CSE update 성공과 AI-AE 응답 성공 기준을 분리해서 처리합니다.
- 민감한 `.env` 값은 테스트와 문서에 직접 포함하지 않습니다.
- 데모 모델은 산업 안전 검증 모델로 표현하지 않습니다.

## 로컬 실행

루트 `.env`를 설정한 뒤 AI-AE를 실행합니다.

```powershell
cd AI-AE
python -m uvicorn mec_safety.app:app --host 127.0.0.1 --port 8001 --reload
```

모의 PLC와 센서 송신기는 별도 터미널에서 선택적으로 실행합니다.

```powershell
python -m mec_safety.demo_plc_server
python -m mec_safety.send_mock_data --interval-seconds 1
```

모의 sender는 실제 MN-CSE Resource를 업데이트하므로 주의해서 사용합니다.

## API 수동 확인

```powershell
curl.exe http://127.0.0.1:8001/health

curl.exe -X POST http://127.0.0.1:8001/api/devices/device3/data ^
  -H "Content-Type: application/json" ^
  -d "{\"beam_blocked\":true}"

curl.exe http://127.0.0.1:8001/api/snapshot
```

## 테스트 실행

전체 테스트:

```powershell
cd AI-AE
python -m pytest -q
```

현재 코드 기준 전체 테스트는 14개입니다. 마지막 확인 결과 14개가 통과했습니다.

모델 흐름의 작은 범위 테스트:

```powershell
python -m pytest -q tests\test_sensor_trigger_engine.py
```

HTTPX `MockTransport`를 사용하는 테스트는 실제 MN-CSE에 쓰기를 보내지 않습니다.
실제 CSE 연결을 확인할 때만 read-only 스크립트를 사용합니다.

```powershell
python tests\check_cse_connection.py
```

이 스크립트는 CSE Base와 six FlexContainer에 대해 GET을 수행합니다.

## 모델 재학습

데이터 생성과 모델 학습은 데모 목적입니다.

```powershell
python -m mec_safety.generate_mock_data
python -m mec_safety.train_risk_model
```

학습은 `mock_sensor_dataset.csv`의 규칙 레이블을 사용해 `risk_model.joblib`을 갱신합니다.
산업 안전 결과를 대체하지 않으며, 배포 전 별도 검증이 필요합니다.

## 모의 데모

```powershell
# Terminal 1
python -m mec_safety.demo_plc_server

# Terminal 2
python -m uvicorn mec_safety.app:app --host 127.0.0.1 --port 8001

# Terminal 3
python -m mec_safety.send_mock_data --interval-seconds 1
```

sender는 기본적으로 모든 데이터에 대해 device1, device2, device4, device5, device3 순서로
요청을 보내고 마지막 요청에서 위험도 추론을 트리거할 수 있습니다.

## Git 저장소 개발 방식

권장 워크플로우:

1. 작업 전 현재 변경사항과 기존 문서 충돌을 확인합니다.
2. 기능별로 작고 검토 가능한 변경을 나눕니다.
3. `.env` 및 산출물은 커밋하지 않습니다.
4. 실행 명령은 최소 범위의 테스트로 검증합니다.
5. 문서의 현재 구현과 계획을 명확히 분리합니다.

기존 프로젝트에는 루트 `.env`가 로컬에서 존재할 수 있지만 Git 추적 대상이 아닙니다.
민감한 값은 `git diff`, 문제 보고 및 문서에 그대로 붙이지 않습니다.

## MN-CSE 빌드 및 실행

WSL/Linux에서 프로젝트 루트 기준:

```bash
python3 MN-CSE/scripts/build.py --init-local-env
python3 MN-CSE/scripts/build.py
python3 MN-CSE/scripts/run.py
```

첫 build 설정은 루트 `.env` 값을 검사하고, seed DB의 고정 Base/Resource ID와 AI-AE
설정을 대조합니다. `.env`에 값이 없거나 placeholder인 경우 build가 중단됩니다.

`configure.ac`는 Autoconf 설정 헤더 및 Makefile 생성을 선언하지만 기존 `autogen.sh`는
대화형이고 기존 `Makefile.in`은 현재 source list와 불일치했습니다. 통합 build script는
추적 템플릿 `config.h.in`, `Makefile.in`에서 빌드 파일을 생성하고 `make`를 실행합니다.
생성된 `config.h`, `Makefile`은 직접 수정하거나 커밋하지 않습니다.

## 테스트와 실제 CSE 확인

AI-AE 단위/통합 테스트:

```powershell
cd AI-AE
python -m pytest -q
```

MockTransport 기반 테스트는 CSE write를 보내지 않습니다. 실제 서버를 실행한 상태에서:

```powershell
python tests\check_cse_connection.py
python -m mec_safety.send_mock_data --once
```

두 번째 명령은 실제 runtime DB에 sensor와 Risk update를 기록합니다. 테스트용 입력인지
확인하고 운영 데이터와 섞이지 않도록 주의합니다.

## 모듈별 개발 원칙

- AI-AE 입력 schema와 TinyIoT Device1~Device6 FlexContainer schema를 함께 검증합니다.
- Resource ID는 기존 seed DB의 값을 유지하고, build 검증으로 mismatch를 막습니다.
- `MN-CSE/data.db`는 seed로 보존하고 서버는 `runtime/data.db`에서 실행합니다.
- `SERVER_IP`는 POA 광고 주소이고 listener bind 주소는 현재 `0.0.0.0`임을 구분합니다.
- Registrar/Remote CSE가 확정되기 전 관련 환경변수를 설정하지 않습니다.
- Dashboard 구현, 다중 MEC discovery, Registry, Docker Compose는 현 task 범위에 넣지 않습니다.

## Dashboard 통합 시 주의사항

Dashboard 소스가 전달되면 다음 항목을 실제 코드에서 확인해야 합니다.

- 프레임워크와 런타임 요구사항
- build와 실행 명령
- 환경변수 템플릿
- listen port 및 조회 API 관계
- 인증 방식
- Dashboard가 CSE를 직접 조회하는 경우 필요한 접근 제어
