# 배포 가이드

## 기본 토폴로지

| 장비 | 설치 컴포넌트 | 목적 |
|---|---|---|
| Computer A — MEC Node | AI-AE + TinyIoT MN-CSE | 센서 처리, 위험 추론, oneM2M resource 저장 |
| Computer B — Monitoring Node | TinyIoT IN-CSE + PinchGuard Dashboard | Remote CSE 등록/라우팅과 UI 제공 |

MEC Package와 Monitoring Package는 서로 다른 장비에 독립적으로 설치할 수 있습니다. 각
패키지는 별도 `config/.env`를 사용하며 하나의 설정 파일을 공유하지 않습니다. 동일 장비에
두 패키지를 배치하는 것은 개발/demo용 구성으로 가능하지만 포트 충돌, 방화벽 및 POA 주소를
별도로 조정해야 합니다.

## 사전 준비

현재 C/C++ 빌드와 패키지 자동화의 공식 작업 환경은 WSL Ubuntu/Linux x86_64입니다.
지원 OS/아키텍처는 패키징 및 실환경 검증을 통과한 범위만 공식화해야 합니다.

개발/패키지 빌드 도구:

```bash
sudo apt-get update
sudo apt-get install -y build-essential pkg-config libssl-dev libwebsockets-dev python3-venv
```

MN-CSE Seed DB를 기준으로 Base/Device1~Device6 Resource ID와 FlexContainer schema가 맞아야
합니다. Seed DB는 초기 데이터이므로 직접 갱신하지 않고, 실행 데이터는 runtime DB에
저장합니다.

## Computer A — MEC Package

### 포함 요소와 외부 의존성

- AI-AE Python/FastAPI 실행 파일, ML 모델 및 패키지 내부 Python runtime
- TinyIoT MN-CSE 네이티브 실행 파일
- 기존 Seed DB와 SDT definition
- 설정 템플릿, start/stop/status/healthcheck 도구
- 실행 시 libc 및 TinyIoT가 링크한 OpenSSL/libwebsockets 런타임 라이브러리
- IN-CSE endpoint는 Computer B에서 실행되어야 함. 단, 연결이 일시적으로 실패해도 MEC
  MN-CSE는 기동하며 등록을 재시도하도록 구현됨

### 설정 항목

`./scripts/configure-mec` 실행 후 `config/.env`에서 다음을 입력합니다.

- `AE_ID`: AI-AE의 oneM2M Originator
- `TINYIOT_SERVER_IP`: Computer B에서 접근 가능한 MEC Node 주소. CSE POA에 광고됩니다.
- `REMOTE_CSE_ID`, `REMOTE_CSE_NAME`: Computer B IN-CSE의 CSE ID와 Base 이름. IN-CSE 설정과
  일치해야 합니다.
- `REMOTE_CSE_HOST`, `REMOTE_CSE_PORT`: Computer B IN-CSE가 실제로 수신하는 주소와 포트
- `CSE_BASE_URL`: AI-AE가 같은 MEC Node의 MN-CSE로 요청하는 로컬 URL. 포트가 변경되면 함께
  변경합니다.
- Seed에서 채워지는 Base 및 Device1~Device6 ID는 임의 변경하지 않습니다.

`TINYIOT_SERVER_IP`는 bind 주소가 아니라 POA 광고 주소입니다. MN-CSE HTTP listener는
`0.0.0.0`에 bind합니다. 내부망에서 안정적으로 라우팅되는 MEC 주소를 사용하고, loopback을
Computer B용 POA 주소로 사용하지 않습니다.

### 설치/기동/확인

```bash
./scripts/configure-mec
# config/.env 편집
./scripts/start-mec
./scripts/status-mec
./scripts/healthcheck
./scripts/stop-mec
```

기동 순서는 설정과 Seed DB 검증 → runtime DB 최초 복사 → MN-CSE 기동 및 CSE Base 확인 →
AI-AE 기동 및 `/health` 확인입니다. IN-CSE 등록은 MN-CSE의 백그라운드 재시도이므로
Monitoring Node가 아직 시작되지 않았더라도 로컬 MEC 서비스는 시작할 수 있습니다.
`status-mec`에는 IN-CSE 등록이 ready 또는 pending/unavailable로 표시됩니다.

### 네트워크

- MEC MN-CSE inbound TCP `TINYIOT_SERVER_PORT` (기본 예시 `3000`): Computer B의 IN-CSE에서
  접근 가능하도록 제한적으로 허용
- AI-AE HTTP `AI_AE_PORT` (기본 예시 `8001`): 외부에 열 필요가 없는 센서 내부 API라면
  loopback/내부 네트워크로 제한
- Mock PLC TCP `9001`: 개발/demo 선택 기능, 별도 프로세스

## Computer B — Monitoring Package

### 포함 요소와 외부 의존성

- TinyIoT IN-CSE 네이티브 실행 파일
- Dashboard Backend와 static Frontend를 포함한 실행 파일
- 설정 템플릿, 실행/종료/상태/healthcheck 도구
- Dashboard SQLite, 로그 및 PID 저장용 runtime 디렉터리
- IN-CSE 네이티브 바이너리의 libc/OpenSSL/libwebsockets 런타임 라이브러리
- MEC Node의 MN-CSE는 외부 서비스이며, Monitoring Package는 MEC 없이도 기동 가능

### 설정 항목

`./scripts/configure-monitoring` 실행 후 `config/.env`에서 다음을 입력합니다.

- `IN_CSE_SERVER_IP`: MEC Node가 접근할 수 있는 Computer B 주소(광고되는 POA)
- `IN_CSE_SERVER_PORT`: IN-CSE listener 포트
- `PG_IN_CSE_URL`: Dashboard Backend가 같은 장비의 IN-CSE를 조회하는 주소. 기본은 loopback
  이며, IN-CSE와 Dashboard가 다른 장비에 놓일 때는 routable 주소로 변경합니다.
- `PG_MN_CSE_ID`: 등록 대상 MEC MN-CSE의 CSE ID. 패키지 빌드 설정과 일치해야 합니다.
- `PG_IN_CSE_ORIGIN`: IN-CSE 접근 정책에 허용된 Dashboard Originator
- `PG_INGEST_KEY`: Dashboard ingest API 용도에 맞는 강한 임의 key. 실제 값을 문서/로그에
  출력하지 않습니다.
- `PG_DASHBOARD_HOST`/`PG_DASHBOARD_PORT`: 브라우저에 제공할 Backend listener 주소/포트
- `PG_DB_PATH`: Dashboard SQLite runtime 파일 경로

### 설치/기동/확인

```bash
./scripts/configure-monitoring
# config/.env 편집
./scripts/start-monitoring
./scripts/status-monitoring
./scripts/healthcheck
./scripts/stop-monitoring
```

기동 순서는 IN-CSE 시작 및 CSE Base 확인 → Dashboard 시작 및 `/health` 확인입니다. MEC가
아직 실행되지 않았거나 등록되지 않았더라도 Dashboard 자체는 시작할 수 있습니다.
`status-monitoring`에서 MEC 데이터 연결 상태를 별도 표시합니다. 연결되지 않으면
`PG_IN_CSE_URL`, Originator/ACL, MN-CSE 등록, POA 주소, 방화벽 및 RVI를 확인합니다.

### 네트워크

- IN-CSE inbound TCP `IN_CSE_SERVER_PORT` (기본 예시 `3001`): Computer A의 MN-CSE 등록 및
  Dashboard Backend 요청 허용
- Dashboard inbound TCP `PG_DASHBOARD_PORT` (기본 예시 `8000`): 실제 사용자 브라우저가
  접근할 범위만 허용
- IN-CSE CSE API를 인터넷 전체에 공개하지 않습니다. 가능한 한 두 노드 내부망/VPN으로
  제한하고 access-control/RVI 설정을 확인합니다.

## 시작 순서와 연결 확인

권장 순서는 Computer B에서 Monitoring Package를 기동한 뒤 Computer A의 MEC Package를
기동하는 것입니다. MEC 쪽에는 재시도 로직이 있으므로 순서가 바뀌어도 로컬 CSE를 계속
운영할 수 있어야 합니다.

1. Computer B에서 IN-CSE와 Dashboard의 로컬 health를 확인합니다.
2. Computer A에서 MN-CSE/AI-AE health를 확인하고 Remote CSE registration 상태를 봅니다.
3. Computer A의 방화벽에서 Computer B IN-CSE가 MEC POA에 도달할 수 있는지 확인합니다.
4. Computer B에서 Dashboard API의 `/api/onem2m/devices`가 여섯 원격 resource를 조회하는지
   확인합니다.
5. 한 장비의 `127.0.0.1`을 다른 장비의 접속 주소로 사용하지 않았는지 확인합니다.

API/health 응답이 정상이어도 실제 센서가 최신이라는 뜻은 아닙니다. Dashboard는 source
timestamp와 polling 상태를 분리해 표시합니다. Sensor Sender 사용 시 runtime DB가 변경됩니다.

## WSL 단일 환경 개발/demo

모든 프로세스를 하나의 WSL Ubuntu에서 시험할 때도 동일한 CSE 등록 및 원격 경로를 사용할 수
있지만, 이 설정은 서로 다른 컴퓨터의 방화벽/라우팅/POA 검증을 대신하지 않습니다.

- MN-CSE: 기본 예시 TCP `3000`
- IN-CSE: 기본 예시 TCP `3001`
- Dashboard: 기본 예시 TCP `8000`
- AI-AE: 기본 예시 TCP `8001`
- Mock PLC: 기본 예시 TCP `9001`

## 데이터 보존과 업그레이드

- MEC runtime DB와 Dashboard SQLite는 프로그램/바이너리 업데이트와 분리되어 있습니다.
- 설치나 업그레이드 시 기존 runtime 디렉터리를 덮어쓰거나 삭제하지 않습니다.
- 배포 전 DB와 로그를 백업하고, 새 패키지에서 기존 DB 스키마 호환성을 별도로 검증합니다.
- 패키지 start/stop/status 스크립트는 기록된 PID와 해당 패키지 실행 파일을 확인한 뒤
  프로세스를 관리합니다.

## 아직 검증이 필요한 항목

- Computer A ↔ Computer B 실제 LAN 등록/forwarding/GET end-to-end
- 신규 장비에서 MEC와 Monitoring 각 패키지의 설치/기동/종료/재부팅
- 네트워크 단절 뒤 Remote CSE 재등록 및 Dashboard 회복 시간
- 대상 OS별 동적 라이브러리, 방화벽, CPU 아키텍처 호환성
- 운영 Originator/ACP 정책과 TLS

아직 실행하지 않은 검증은 성공으로 간주하지 않습니다.
