# AI-AE + MN-CSE 실제 실행 가이드

## 현재 검증된 배치

단일 컴퓨터에서 AI-AE와 TinyIoT MN-CSE를 실행합니다.

| 컴포넌트 | 실행 위치 | 포트 | 목적 |
|---|---|---:|---|
| TinyIoT MN-CSE | WSL/Linux | TCP HTTP `3000` | oneM2M 리소스 저장 및 update 처리 |
| AI-AE | Windows Python 또는 같은 Linux 환경 | HTTP `8001` | 센서 입력, 위험도 판단, CSE update |
| Mock PLC | 선택적 데모 프로세스 | TCP `9001` | CRITICAL STOP 동작 모의 |

Dashboard, IN-CSE, 다중 MEC 등록/Discovery, Docker Compose는 이번 구성에 포함되지 않습니다.

## 전제 조건

MN-CSE는 WSL/Linux에서 빌드합니다. 필요한 도구/라이브러리:

- Python 3
- GCC와 GNU Make
- pkg-config
- OpenSSL 개발 파일
- libwebsockets 개발 파일

Ubuntu 계열에서는 시스템 관리자 권한으로 필요한 패키지를 설치합니다.

```bash
sudo apt-get update
sudo apt-get install -y build-essential pkg-config libssl-dev libwebsockets-dev python3
```

## 1. 프로젝트 루트 `.env` 준비

`.env.example`을 참고해 루트 `.env`에 AI-AE Originator와 6개 Resource ID를 준비합니다.
실제 값은 로그나 문서에 복사하지 않습니다.

최초 통합 환경에서는 WSL 프로젝트 루트에서 다음 명령으로 확인된 로컬 TinyIoT 값과
AI-AE 연결 주소를 설정할 수 있습니다.

```bash
python3 MN-CSE/scripts/build.py --init-local-env
```

옵션은 `CSE_BASE_URL`, `CSE_BASE_NAME`, `CSE_RVI`와 seed DB에서 읽을 수 있는 CSE Base RI,
그리고 TinyIoT의 로컬 네트워크 값을 설정합니다. 기존 `AE_ID`, six Resource ID 및
`TINYIOT_CSE_BASE_SP_ID`는 보존합니다. seed DB에는 SP ID가 없으므로 해당 변수는 별도
설정이 필요합니다. 일반 빌드는 `.env` 누락이나 placeholder를 오류로 처리합니다.

필수 TinyIoT 환경변수:

- `TINYIOT_SERVER_TYPE=mn`
- `TINYIOT_SERVER_IP`
- `TINYIOT_SERVER_PORT`
- `TINYIOT_CSE_BASE_NAME`
- `TINYIOT_CSE_BASE_RI`
- `TINYIOT_CSE_BASE_SP_ID`

추가로 `CSE_BASE_URL`, `CSE_BASE_NAME`, `CSE_RVI`, `AE_ID`, AI-AE의 six Resource ID도
필요합니다. Registrar CSE는 확정되지 않아 REMOTE_CSE 설정은 비워 둡니다.

## 2. MN-CSE 빌드

프로젝트 루트가 현재 디렉터리인 WSL/Linux shell에서 실행합니다.

```bash
python3 MN-CSE/scripts/build.py
```

스크립트는 다음을 수행합니다.

1. `.env`의 필수 설정과 single-MN 모드를 검사합니다.
2. seed DB의 CSE Base, Device1~6 Resource ID와 custom field를 AI-AE 설정과 대조합니다.
3. `.env` 및 추적 템플릿에서 `MN-CSE/config.h`, `MN-CSE/Makefile`을 생성합니다.
4. `make clean`, `make -j2`로 `MN-CSE/server`를 빌드합니다.

`config.h`와 `Makefile`은 생성 파일이며 직접 수정하지 않습니다. `config.h.in`과
`Makefile.in`이 템플릿입니다. 빌드 결과의 설정 값은 출력하지 않습니다.

## 3. MN-CSE 실행

프로젝트 루트에서 실행합니다.

```bash
python3 MN-CSE/scripts/run.py
```

첫 시작에 `MN-CSE/data.db`를 `MN-CSE/runtime/data.db`로 복사합니다. 다음 시작에서는 runtime
DB가 이미 있으면 seed로 덮어쓰지 않습니다. SDT definition도 runtime 디렉터리에 복사한 뒤
서버를 실행합니다. 정지하려면 `Ctrl+C`를 누릅니다.

### 주소 해석

- `httpd.c`는 listener를 `0.0.0.0`에 bind합니다.
- `TINYIOT_SERVER_IP`는 `util.c`가 CSE Base의 POA에 기록하는 광고 IP입니다.
- `TINYIOT_SERVER_PORT`는 listener와 POA port입니다.
- AI-AE는 별도 `CSE_BASE_URL=http://127.0.0.1:3000`로 연결합니다.

동일 Windows/WSL 컴퓨터에서 확인된 구성에서는 Windows 측 `127.0.0.1:3000`으로 WSL 서버에
접속할 수 있었습니다. 다른 네트워크 배치에서는 loopback 대신 AI-AE에서 접근 가능한 주소를
설정하고 POA 광고 주소와 용도를 구분합니다.

## 4. CSE 상태 및 리소스 확인

MN-CSE 실행 로그에 DB 초기화, SDT definition 로드 및 HTTP server 시작이 표시되어야 합니다.
Originator 값을 문서나 셸 이력에 복사하지 않도록, 실제 Base 및 Resource GET 검증은
AI-AE의 설정 파일을 읽는 스크립트로 수행합니다.

```powershell
cd AI-AE
python tests\check_cse_connection.py
```

CSE Base 응답은 HTTP `200`, `X-M2M-RSC: 2000`이어야 합니다. 이는 HTTP listener 및
Base 조회 확인이며 AI-AE update 성공 확인과는 별도입니다.

## 5. AI-AE 실행

PowerShell에서 프로젝트의 `AI-AE` 디렉터리로 이동합니다.

```powershell
cd AI-AE
python -m pip install -r requirements.txt
python -m uvicorn mec_safety.app:app --host 127.0.0.1 --port 8001
```

AI-AE는 프로젝트 루트 `.env`를 `python-dotenv`로 읽습니다. 상태 endpoint:

```powershell
curl.exe http://127.0.0.1:8001/health
```

연결 검증 스크립트는 `.env` 값을 읽고 CSE Base와 여섯 FlexContainer에 GET을 보내며,
Resource ID/schema를 검증합니다.

성공 결과는 TCP 연결, CSE Base GET 및 여섯 리소스 조회/schema 검사 성공입니다.

## 6. Mock Sensor 데이터로 update 확인

AI-AE 디렉터리의 별도 PowerShell에서 실행합니다.

```powershell
python -m mec_safety.send_mock_data --once
```

sender는 Device1, Device2, Device4, Device5, Device3 순서로 샘플을 전송합니다. 각 센서 update의
응답에서 `Layer2 success=True`, `RSC=2004`를 확인합니다. 마지막 Device3 요청에서 추론이
실행되며 `Device6 success=True`, `RSC=2004`이면 위험도도 CSE에 update된 것입니다.

실제 동작은 runtime DB를 변경합니다. 테스트 전후 DB 상태가 필요하면 seed DB가 아니라
`MN-CSE/runtime/data.db`를 확인합니다.

연속 전송:

```powershell
python -m mec_safety.send_mock_data --interval-seconds 1
```

종료는 `Ctrl+C`입니다. 실제 MN-CSE에 데이터를 쓰므로 mock 데이터 실행에 주의합니다.

## 7. 선택적 Mock PLC

AI-AE 프로세스 시작 시 PLC 연결이 필요하므로 테스트 전에 별도 터미널에서 시작합니다.

```powershell
cd AI-AE
python -m mec_safety.demo_plc_server
```

모의 서버는 `127.0.0.1:9001`에서 동작합니다. Demo PLC 주소/포트는 현재 환경변수로 바뀌지
않으며, 실제 PLC에 연결하기 전에 안전 제어 경로를 별도로 검증해야 합니다.

## DB 복구와 보존

- `MN-CSE/data.db`: 고정 Resource ID를 포함한 seed. 실행 프로세스에 직접 사용하지 않습니다.
- `MN-CSE/runtime/data.db`: 실제 실행 시 update되는 런타임 DB.
- `run.py`는 runtime DB를 자동 초기화하거나 덮어쓰지 않습니다.
- 새 배포에는 seed DB를 별도로 보존/배포해야 기존 ID를 재현할 수 있습니다.
- 빈 DB는 테이블은 만들지만 Device1~Device6를 재생성하지 않으므로 seed 없이 운영하지 않습니다.

런타임 DB 교체 또는 초기화는 데이터를 지우는 작업이므로 필요한 백업 후 운영자가 별도로
결정해야 합니다. 자동 초기화 명령은 제공하지 않습니다.
