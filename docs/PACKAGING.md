# 독립 배포 패키지

## 목표와 현재 범위

저장소는 소스 관리용이며 실제 배포는 역할별 패키지로 분리합니다.

| 패키지 | 포함 구성요소 | 상태 |
|---|---|---|
| MEC Package | AI-AE, TinyIoT MN-CSE, 모델, seed DB, 설정/실행 도구 | Linux x86_64 패키징 자동화 구현 |
| Dashboard Package | PinchGuard Dashboard Backend/Frontend | Dashboard 소스가 저장소에 통합된 뒤 구현 |

Dashboard는 별도로 개발 완료되었지만 소스가 현재 저장소에 없습니다. 따라서 이 저장소에서는
Dashboard 패키지를 만들거나 실행 명령을 가정하지 않습니다. Computer A/B 간 실네트워크
연동 검증도 아직 완료된 것으로 간주하지 않습니다.

## MEC Package 구조

`python packaging/mec/build_package.py`는 다음과 같은 Linux x86_64 패키지를 생성합니다.

```text
MEC-Package-Linux-x86_64/
├── bin/
│   ├── tinyiot-mn-cse
│   ├── ai-ae/
│   └── mec-control/
├── config/
│   ├── .env.example
│   └── build-info.json
├── data/seed.db
├── models/risk_model.joblib
├── runtime/
│   ├── data.db                 # 최초 실행 때 생성
│   ├── logs/
│   └── pid/
├── scripts/
│   ├── configure-mec
│   ├── start-mec
│   ├── stop-mec
│   ├── status-mec
│   └── healthcheck
├── share/sdt_definitions/
├── licenses/
└── README.md
```

AI-AE와 패키지 제어 도구는 PyInstaller onedir로 Python Runtime 및 Python 의존성을 포함합니다.
TinyIoT는 Linux x86_64용 네이티브 실행 파일입니다. 대상 장비에는 빌드 도구나 Python 개발
의존성이 필요하지 않지만, TinyIoT 바이너리가 링크한 OpenSSL/libwebsockets 런타임 라이브러리는
필요합니다. 이 패키지는 현재 Linux x86_64 외 플랫폼을 지원한다고 주장하지 않습니다.

## 패키지 빌드

WSL/Linux x86_64에서 루트 `.env`를 준비한 뒤 실행합니다. 해당 `.env`는 빌드 시 설정 검증과
TinyIoT 컴파일에만 사용되고 MEC 패키지에 복사되지 않습니다.

```bash
python3 -m venv packaging/mec/.venv
source packaging/mec/.venv/bin/activate
python -m pip install -r packaging/mec/requirements-build.txt
python packaging/mec/build_package.py
```

빌드는 MN-CSE `build.py`의 seed/설정 검증을 거친 뒤 AI-AE와 제어 도구를 동결하고,
패키지 디렉터리, `.tar.gz`, SHA-256 체크섬을 `packaging/mec/dist/`에 생성합니다.
기존 출력 디렉터리/아카이브는 덮어쓰지 않으며, 새 `--output-dir`을 지정해야 합니다.
프로젝트 루트 `.env` 자체는 복사하지 않습니다. 단, TinyIoT 컴파일에 필요한 서비스
Provider ID는 seed DB에 저장되어 있지 않아 패키지 빌드 메타데이터에 포함됩니다.

## 설치 및 실행

압축을 푼 뒤 패키지 디렉터리에서:

```bash
./scripts/configure-mec
```

`config/.env`가 생성되면 `AE_ID`와 MEC 장비의 접근 가능한 IPv4 주소인
`TINYIOT_SERVER_IP`를 입력합니다. 자동 생성된 Base/Device1~Device6 설정은 함께 배포된
seed DB에서 추출되며, 서로 불일치하면 시작을 거부합니다. 다른 포트를 사용하면
`TINYIOT_SERVER_PORT`와 `CSE_BASE_URL=http://127.0.0.1:<같은 포트>`를 함께 변경합니다.
AI-AE의 로컬 CSE URL은 MEC 내부 loopback 연결입니다. Dashboard는 다른 컴퓨터에서 접속할 때
loopback이 아니라 `TINYIOT_SERVER_IP`와 포트를 사용해야 합니다.

```bash
./scripts/start-mec
./scripts/status-mec
./scripts/healthcheck
./scripts/stop-mec
```

시작 순서는 설정/seed 검증 → runtime DB 최초 복사 → MN-CSE 시작 → CSE Base 준비 확인 →
AI-AE 시작 → AI-AE `/health` 확인입니다. 실패하면 시작된 프로세스를 정리하고 오류를
반환합니다. 실행 로그와 PID 파일은 `runtime/logs/`, `runtime/pid/`에 기록됩니다.

MN-CSE는 HTTP listener를 `0.0.0.0`에 bind하고, `TINYIOT_SERVER_IP`/`TINYIOT_SERVER_PORT`를
POA에 광고합니다. 이 환경변수는 패키지 실행 시 읽히므로 장비마다 바이너리를 다시 컴파일할
필요가 없습니다. 기존 `runtime/data.db`는 재실행이나 패키지 업데이트로 덮어쓰지 않습니다.

## Dashboard Package 후속 작업

Dashboard 소스가 통합되면 실제 backend/frontend, 설정 키, SQLite 사용 방식, 실행 환경과
라이선스를 먼저 확인한 뒤 별도 `packaging/dashboard/`를 설계합니다. MEC 접속 URL은
Dashboard 설정 파일에 두고, Computer A의 MN-CSE LAN 주소를 사용해야 합니다. 두 패키지 간
연결, 방화벽, 인증, 재부팅 후 자동 기동은 별도 실환경 테스트를 통과한 뒤 지원 범위에
표시합니다.
