# 독립 배포 패키지

## 목표와 현재 상태

저장소는 소스 코드 및 빌드 정의를 관리하며, 최종 사용자는 장비 역할에 맞는 독립 패키지를
받는 것이 목표입니다.

| 패키지 | 포함 구성요소 | 구현 상태 |
|---|---|---|
| MEC Package | AI-AE + TinyIoT MN-CSE | Linux x86_64 빌더와 런타임 제어 스크립트 존재 |
| Monitoring Package | TinyIoT IN-CSE + PinchGuard Dashboard | Linux x86_64 빌더와 런타임 제어 스크립트 존재 |

Dashboard는 별도 개발 완료였으며 현재 저장소에 소스가 통합되어 있습니다. 패키지 빌드 경로가
구현된 것과 GitHub Release 배포 또는 별도 장비에서 설치/운영 검증이 완료된 것은 구분합니다.
두 컴퓨터 간 LAN 연결과 깨끗한 환경 설치는 완료된 것으로 간주하지 않습니다.

## MEC Package

빌드 진입점은 `packaging/mec/build_package.py`입니다. Linux x86_64 환경에서 root `.env`와
MN-CSE Seed DB를 검증하고 TinyIoT를 빌드한 뒤 AI-AE 및 제어 도구를 PyInstaller onedir로
패키징합니다. 출력 기본 위치는 `packaging/mec/dist/MEC-Package-Linux-x86_64/`이며 옆에
`.tar.gz`와 `.sha256` 파일을 생성합니다.

주요 패키지 구성:

```text
MEC-Package-Linux-x86_64/
├── bin/
│   ├── ai-ae/
│   ├── mec-control/
│   └── tinyiot-mn-cse
├── config/
│   ├── .env.example
│   └── build-info.json
├── data/seed.db
├── models/risk_model.joblib
├── runtime/{logs,pid}/
├── scripts/{configure-mec,start-mec,stop-mec,status-mec,healthcheck}
├── share/sdt_definitions/
├── licenses/
└── README.md
```

실제 디렉터리 및 파일 배치는 빌더 구현을 따릅니다. 런타임에 첫 실행만 Seed DB를
`runtime/data.db`로 복사하며, 기존 runtime DB는 덮어쓰지 않습니다. AI-AE/제어기는 번들된
Python runtime을 사용하나 TinyIoT 네이티브 실행 파일의 시스템 동적 라이브러리 필요 여부는
배포 OS에서 확인해야 합니다.

## Monitoring Package

빌드 진입점은 `packaging/monitoring/build_package.py`입니다. Linux x86_64에서 root `.env`의
MEC RVI 및 SP ID와 MEC Seed DB의 CSE Base RI를 읽습니다. 패키지 빌더가 고정 IN-CSE
identity와 해당 Seed DB만 허용하는 Remote CSE build 설정을 생성합니다. IN-CSE를 빌드하고
IN-CSE, Dashboard Backend, 패키지 제어기를 패키징합니다. 기본 출력은
`packaging/monitoring/dist/Monitoring-Package-Linux-x86_64/`이며 `.tar.gz` 및 `.sha256`도
생성합니다.

주요 구성:

```text
Monitoring-Package-Linux-x86_64/
├── bin/
│   ├── dashboard/
│   ├── monitor-control/
│   └── tinyiot-in-cse
├── config/{.env.example,build-info.json}
├── runtime/{logs,pid}/
├── scripts/{configure-monitoring,start-monitoring,stop-monitoring,status-monitoring,healthcheck}
└── README.md
```

Dashboard static 파일은 Backend 실행 패키지에 포함됩니다. Monitoring Node의 IN-CSE와
Dashboard는 같은 노드에서 실행하고, 각자의 oneM2M CSE HTTP listener와 Dashboard listener를
구분합니다.

## 빌드 절차

WSL/Linux x86_64에 C compiler, make, pkg-config, OpenSSL/libwebsockets 개발 파일 및 Python
venv를 준비합니다. MEC 빌드:

```bash
python3 -m venv packaging/mec/.venv
source packaging/mec/.venv/bin/activate
python -m pip install -r packaging/mec/requirements-build.txt
python packaging/mec/build_package.py
```

Monitoring 빌드:

```bash
python3 -m venv packaging/monitoring/.venv
source packaging/monitoring/.venv/bin/activate
python -m pip install -r packaging/monitoring/requirements-build.txt
python packaging/monitoring/build_package.py
```

MEC 빌드는 프로젝트 root `.env`와 Seed DB 설정을 검증합니다. Monitoring 빌드는 root `.env`의
`CSE_RVI`, `TINYIOT_CSE_BASE_SP_ID`와 MEC Seed DB의 Base RI를 사용하며 Monitoring Node의
실제 주소/Originator/ingest key는 요구하지 않습니다. Root `.env`는 패키지에 복사되지 않습니다.
출력 디렉터리/아카이브가 이미 존재하면 덮어쓰지 않고 실패하므로 새 `--output-dir`을
지정합니다. 컴파일 시 생성되는 CSE 설정 header는 패키지용 build configuration 산출물입니다.
빌드 로그나 metadata에 실제 Originator, Resource ID 또는 인증정보를 추가하지 않습니다.

## 설치와 설정 분리

각 아카이브의 `README.md`와 [배포 가이드](DEPLOYMENT.md)를 따릅니다.

- MEC는 `./scripts/configure-mec`로 자체 `config/.env`를 만들고 MEC 장비의 POA 주소,
  Remote IN-CSE endpoint와 Originator를 설정합니다.
- Monitoring은 `./scripts/configure-monitoring`로 별도 설정을 만들고 Monitoring Node의 POA,
  Dashboard listener, MEC Package의 `AE_ID`와 ingest key를 설정합니다. `PG_IN_CSE_ORIGIN`은
  MN-CSE Seed DB의 읽기 권한과 일치해야 하며, IN-CSE 최초 기동 전에 정해야 합니다.
- 두 패키지는 서로 다른 컴퓨터에 배치될 수 있으므로 `.env`를 공유하지 않습니다.
- 설정 파일에는 운영상 민감한 값이 들어갈 수 있으므로 접근을 제한하고 Git에 커밋하지 않습니다.

## 데이터 및 업그레이드

- MEC `runtime/data.db`와 Monitoring `runtime/`의 SQLite, 로그, PID는 패키지 코드와 분리합니다.
- 업그레이드 전에 사용자 데이터를 백업합니다. 기존 runtime DB를 새 Seed DB로 대체하지
  않습니다.
- 패키지 변경/업데이트 때 DB schema 호환성, 기존 Resource ID 및 설정 migration을 확인합니다.
- `stop-*`/`status-*`는 패키지의 PID/runtime 경로를 기준으로 관리하며, 별도 OS service manager
  등록이나 재부팅 후 자동 시작은 현재 패키지 기능으로 보장하지 않습니다.

## 배포 및 검증 한계

현재 빌더는 Linux x86_64만 허용합니다. WSL에서 패키지가 생성되더라도 깨끗한 Linux 장비에서
실행되는 것을 대체 검증하지 않습니다. Windows package, ARM64, 자동 업데이트, GitHub Release
게시, 서명 및 공급망 검증은 아직 확정/구현되지 않았습니다.

Release 전에 적어도 다음을 별도로 확인해야 합니다.

- 대상 OS/아키텍처와 동적 라이브러리 호환성
- 설정 파일 없이 시작 시 명확한 실패 및 placeholder 차단
- runtime 데이터 보존/업데이트 및 정상 종료
- Computer A ↔ Computer B의 등록/POA/IN-CSE forwarding/Dashboard 조회
- 방화벽, Originator/ACP 정책, 인증 및 TLS 배치
- 실제 배포 아카이브의 SHA-256 재계산 및 Release metadata

수행하지 않은 항목은 통과 또는 지원 완료로 표시하지 않습니다.
