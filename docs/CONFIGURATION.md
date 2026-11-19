# 환경변수 및 설정 관리

저장소 빌드용 루트 `.env`와 실제 배포 패키지별 `config/.env`는 목적과 배치가 다릅니다.
Computer A와 Computer B는 각자 설정 파일을 보유하며 공유하지 않습니다. `.env` 파일의
실제 주소, Originator, Resource ID 및 인증정보는 저장소/문서/로그에 복사하지 않습니다.

## 설정 파일

| 파일 | 사용처 | Git 관리 |
|---|---|---|
| 프로젝트 루트 `.env.example` | 개발 및 패키지 빌드 키 목록/placeholder | 추적 |
| 프로젝트 루트 `.env` | 개발 빌드 설정, MN-CSE/IN-CSE 구성 | ignore |
| `packaging/mec/templates/.env.example` | MEC 배포 패키지용 독립 설정 | 추적 |
| `packaging/monitoring/templates/.env.example` | Monitoring 배포 패키지용 독립 설정 | 추적 |
| `Dashboard/.env.example` | Dashboard 로컬 개발용 | 추적 |

`.env.example`의 `YOUR_*`, `AUTO_FROM_*`, `CHANGE_*` 값은 placeholder입니다. 운영 주소나
실제 ID가 아닙니다. 패키지의 `configure-*` 명령은 새 `config/.env`만 생성하며 기존 파일을
덮어쓰지 않습니다.

## AI-AE 및 MEC MN-CSE 설정

프로젝트 루트 `.env`가 사용하는 주요 AI-AE 키:

| 변수 | 의미 |
|---|---|
| `CSE_BASE_URL` | AI-AE가 요청하는 MN-CSE HTTP 주소. 동일 MEC 호스트의 loopback 사용 |
| `CSE_BASE_NAME` | AI-AE가 사용하는 CSE Base 이름 |
| `CSE_RVI` | oneM2M release version indicator |
| `AE_NAME` | AI-AE Application Entity 이름 |
| `AE_ID` | AI-AE 요청의 `X-M2M-Origin` |
| `FCNT_DEVICE1_RI`~`FCNT_DEVICE5_RI` | Seed DB의 센서 FlexContainer Resource ID |
| `FCNT_RISK_RI` | Seed DB의 Device6 Risk Resource ID |

AI-AE는 리소스 ID를 자동 발견하지 않습니다. 위 Base/RI 값과 resource schema는
`MN-CSE/data.db` Seed DB와 일치해야 하며 build 단계에서 검증됩니다.

TinyIoT MN-CSE 빌드/실행 키:

| 변수 | 의미 |
|---|---|
| `TINYIOT_SERVER_TYPE` | CSE mode. MEC Package는 `mn` |
| `TINYIOT_SERVER_IP` | MN-CSE Base `poa`에 광고하는 MEC Node 주소 |
| `TINYIOT_SERVER_PORT` | HTTP listener/POA 포트 |
| `TINYIOT_CSE_BASE_NAME` | MN-CSE CSE Base 이름 |
| `TINYIOT_CSE_BASE_RI` | CSE Base의 고정 RI |
| `TINYIOT_CSE_BASE_SP_ID` | CSE Base의 service-provider ID |

MN-CSE listener는 `0.0.0.0`에 bind합니다. `TINYIOT_SERVER_IP`는 bind 주소가 아니라 POA
광고값입니다. Computer B에서 도달 가능한 MEC 주소를 지정해야 하며 loopback으로 설정하면
원격 forwarding이 실패합니다.

MEC MN-CSE의 runtime Remote CSE 등록 키:

| 변수 | 의미 |
|---|---|
| `REMOTE_CSE_ID` | IN-CSE의 CSE ID. IN-CSE의 Base RI와 일치해야 함 |
| `REMOTE_CSE_NAME` | IN-CSE CSE Base 이름 |
| `REMOTE_CSE_HOST` | MEC Node에서 도달 가능한 Monitoring Node host |
| `REMOTE_CSE_PORT` | IN-CSE HTTP 포트 |

이 네 값은 MN-CSE process 환경에서 읽힙니다. 값이 비어 있으면 MN-CSE는 로컬 서비스만
시작하고 Remote CSE 등록은 시도하지 않습니다. 유효한 설정이 있으면 등록/CSR 생성은
비동기 재시도합니다. `.env.example`의 placeholder를 유효한 값으로 교체해야 통합됩니다.

## Monitoring Node IN-CSE 설정

| 변수 | 의미 |
|---|---|
| `IN_CSE_SERVER_IP` | IN-CSE가 CSR의 POA로 광고할 Monitoring Node host |
| `IN_CSE_SERVER_PORT` | IN-CSE HTTP listener 포트 |
| `IN_CSE_CSE_BASE_NAME` | IN-CSE CSE Base 이름 |
| `IN_CSE_CSE_BASE_RI` | IN-CSE CSE Base의 고정 RI |
| `IN_CSE_CSE_BASE_SP_ID` | IN-CSE와 MN-CSE 간에 일치시킬 SP ID |
| `IN_CSE_RVI` | IN-CSE oneM2M RVI. MEC `CSE_RVI`와 일치해야 함 |
| `IN_CSE_ADMIN_AE_ID` | 선택적 개발 전용 privileged Originator. Monitoring Package 빌드에서는 설정하지 않음 |
| `IN_CSE_ALLOWED_REMOTE_CSE_ID` | 허용할 CSE ID의 comma-separated 목록 |

IN-CSE는 `IN-CSE/scripts/build.py`로 생성되는 config header를 사용합니다. 생성된
`config.h`는 추적되지 않으며 직접 편집하지 않습니다. IN-CSE Dashboard 조회 경로는
SP-relative addressing인 `/~/<MN-CSE-ID>/DeviceN`입니다.

Monitoring Package는 IN-CSE Base identity와 고정 MEC Seed DB의 Remote CSE allow-list를
빌드 과정에서 구성합니다. 패키지 사용자가 입력하는 `PG_IN_CSE_ORIGIN`은 기동 시
`IN_CSE_DASHBOARD_ORIGINATOR`로 전달되며, IN-CSE의 최초 AccessControl 생성 시 retrieve와
discovery 권한만 부여됩니다. 이 값은 **첫 기동 전에** 정하고, 이후 바꾸지 않는 것을
권장합니다. Optional한 `IN_CSE_ADMIN_AE_ID`는 기존 관리자 AccessControl을 활성화하므로
공유/운영 패키지 빌드에 사용하지 마세요.

## Dashboard 설정

Dashboard 로컬 개발은 `Dashboard/.env.example`, 배포는 Monitoring Package의 별도
`config/.env`를 사용합니다.

| 변수 | 의미 |
|---|---|
| `PG_IN_CSE_URL` | Dashboard Backend의 IN-CSE HTTP origin. path 없이 지정 |
| `PG_MN_CSE_ID` | 등록된 원격 MN-CSE ID |
| `PG_MN_DEVICE1_RI`~`PG_MN_DEVICE6_RI` | Seed DB에서 생성되는 Device1~Device6 Resource ID |
| `PG_IN_CSE_ORIGIN` | MEC Package의 `AE_ID`와 동일하게 설정. MN-CSE Seed DB가 허용한 Originator |
| `PG_IN_CSE_RVI` | IN-CSE와 일치하는 RVI |
| `PG_IN_CSE_TIMEOUT` | oneM2M 요청 timeout 초 |
| `PG_MN_CSE_POLL_SECONDS` | Device1~Device6 polling 간격 |
| `PG_MN_CSE_FRESH_SECONDS` | 원본 source timestamp freshness 임계 초 |
| `PG_DB_PATH` | Dashboard SQLite 파일 경로 |
| `PG_INGEST_KEY` | Dashboard ingest API의 API key |
| `PG_NOTIFY_TOKEN` | 설정된 경우 oneM2M notification 별도 검증 토큰 |
| `PG_ENABLE_DEMO`, `PG_DEMO_SEED` | Demo mode/초기 샘플 이벤트 사용 여부 |
| `PG_DASHBOARD_HOST`, `PG_DASHBOARD_PORT` | Monitoring Package Dashboard listener 주소/포트 |

기본 토폴로지에서 Dashboard와 IN-CSE는 같은 Monitoring Node이므로 Backend→IN-CSE URL에
loopback을 사용할 수 있습니다. MN-CSE는 다른 MEC Node이므로 MN-CSE로 직접 연결할 때
loopback을 사용하지 않습니다. 원격 조회는 IN-CSE가 CSR의 POA를 사용합니다.

## 포트와 주소 의미

| 키/프로세스 | 기본 예시 | 의미 |
|---|---:|---|
| `CSE_BASE_URL` | `127.0.0.1:3000` | AI-AE에서 같은 MEC 장비의 MN-CSE로 연결 |
| MN-CSE `TINYIOT_SERVER_PORT` | `3000` | MEC Node CSE listener |
| IN-CSE `IN_CSE_SERVER_PORT` | `3001` | Monitoring Node CSE listener |
| Dashboard `PG_DASHBOARD_PORT` | `8000` | Browser용 UI/API |
| AI-AE | `8001` | 센서 HTTP API 실행 인자 |
| Mock PLC | `9001` | 개발/demo TCP endpoint |

실제 포트는 각 배포 설정과 실행 시 적용값을 기준으로 합니다. 방화벽을 구성할 때 MEC
listener는 Monitoring Node에서, IN-CSE는 MEC Node에서 접근 가능해야 합니다.

## 민감 정보 및 Git 확인

- 실제 `.env`, runtime DB, Dashboard SQLite, 로그는 Git에 올리지 않습니다.
- `.env.example`은 placeholder만 보유합니다.
- 실행 전 `.env`가 Git ignore 대상인지 `git check-ignore .env` 등으로 확인합니다.
- 환경 덤프(`env`, `printenv`)를 로그/이슈/문서에 붙이지 않습니다.
- Resource ID, Originator 및 주소가 포함된 `config.h`는 생성물로 관리하며 저장소에 커밋하지
  않습니다.
