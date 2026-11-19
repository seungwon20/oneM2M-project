# AI-AE + MN-CSE WSL 실행 가이드

## 실행 구성

개발과 실동작 검증은 하나의 WSL Ubuntu 환경에서 수행합니다. TinyIoT MN-CSE, AI-AE,
Mock PLC, Mock Sensor Sender와 pytest 모두 같은 WSL 배포판을 사용합니다.

| 구성요소 | 실행 주소/포트 | 설명 |
|---|---|---|
| TinyIoT MN-CSE | `0.0.0.0:3000` | HTTP listener |
| AI-AE | `127.0.0.1:8001` | FastAPI 센서 수신 및 ML 위험도 판정 |
| Mock PLC | `127.0.0.1:9001` | 선택적 CRITICAL STOP 시뮬레이션 |

Dashboard, IN-CSE, 다중 MEC Discovery와 Docker Compose는 이 검증 범위에 포함되지 않습니다.
현재 checkout이 `/mnt/c/` 아래라면 빌드와 Python 설치가 느릴 수 있습니다. 새 checkout은
`~/projects/oneM2M-project` 같은 WSL Linux 파일시스템 경로를 권장하지만, 기존 작업 디렉터리를
임의로 이동하거나 덮어쓰지 마세요.

## 1. WSL 의존성 및 AI-AE 가상환경

필요한 시스템 도구는 Python 3, venv, GCC, GNU Make, pkg-config, OpenSSL 개발 파일과
libwebsockets 개발 파일입니다. 누락된 경우 WSL 터미널에서 설치합니다.

```bash
sudo apt-get update
sudo apt-get install -y build-essential pkg-config libssl-dev libwebsockets-dev python3-venv
```

프로젝트 루트에서 AI-AE 가상환경을 만들고 모든 Python 요구사항을 설치합니다.

```bash
cd AI-AE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

scikit-learn 버전은 WSL에서 생성한 모델과 맞추어 `requirements.txt`에서 고정합니다.

## 2. 프로젝트 루트 `.env`

`.env.example`을 참고해 루트 `.env`를 준비합니다. `.env` 실제 값은 문서, 화면 출력 또는
로그에 복사하지 않습니다. 최초 설정은 기존 Originator/Resource ID를 보존하는 옵션을 사용할
수 있습니다.

```bash
cd "$(git rev-parse --show-toplevel)"
python3 MN-CSE/scripts/build.py --init-local-env
```

seed DB에 없는 `TINYIOT_CSE_BASE_SP_ID`는 별도로 설정해야 합니다. Registrar CSE는 확정되지
않았으므로 REMOTE_CSE 설정은 채우지 않습니다.

## 3. MN-CSE 빌드 및 실행

프로젝트 루트에서 빌드합니다.

```bash
cd "$(git rev-parse --show-toplevel)"
python3 MN-CSE/scripts/build.py
```

빌드 스크립트는 필수 설정과 MN 모드를 검증하고, `.env`의 CSE Base Name/RI 및 Device1~6
Resource ID가 seed DB와 일치하는지 검사합니다. FlexContainer custom field도 AI-AE schema와
비교한 뒤 `config.h` 및 `Makefile`을 생성하고 GCC로 `MN-CSE/server`를 빌드합니다. 생성된
`config.h`와 `Makefile`은 직접 편집하지 않습니다.

다른 WSL 터미널에서 서버를 실행합니다.

```bash
cd "$(git rev-parse --show-toplevel)"
python3 MN-CSE/scripts/run.py
```

첫 시작에 runtime DB가 없을 때만 `MN-CSE/data.db`를 `MN-CSE/runtime/data.db`로 복사합니다.
기존 runtime DB는 덮어쓰지 않습니다. SDT definition도 runtime 디렉터리에 복사합니다.
Seed DB는 읽기 전용 기준 데이터로 유지합니다.

`httpd.c` listener는 `0.0.0.0`에 bind합니다. `TINYIOT_SERVER_IP`와 `TINYIOT_SERVER_PORT`는
`util.c`가 CSE POA에 광고하는 값이며, AI-AE의 로컬 접속 URL은 별도
`http://127.0.0.1:3000`입니다.

## 4. CSE Base 및 Device1~6 확인

MN-CSE 실행 중 AI-AE 가상환경에서 read-only 검증기를 실행합니다.

```bash
cd AI-AE
source .venv/bin/activate
python tests/check_cse_connection.py
```

검증기는 TCP 연결, CSE Base GET, HTTP `200`, `X-M2M-RSC: 2000`, Device1~6의 실제 RI 일치,
FlexContainer type/wrapper와 custom field schema를 확인합니다. 출력에는 `.env` 값이나
Resource ID를 표시하지 않고 판정 결과만 표시합니다.

## 5. Mock PLC 실행

CRITICAL STOP 테스트를 한다면 **AI-AE보다 먼저** 별도 WSL 터미널에서 실행합니다.

```bash
cd AI-AE
source .venv/bin/activate
python -m mec_safety.demo_plc_server
```

Mock PLC는 `127.0.0.1:9001`에서 연결을 기다립니다.

## 6. AI-AE 실행 및 상태 확인

다른 WSL 터미널에서 AI-AE를 실행합니다.

```bash
cd AI-AE
source .venv/bin/activate
python -m uvicorn mec_safety.app:app --host 127.0.0.1 --port 8001
```

앱 시작 시 Mock PLC 연결을 시도합니다. health 응답은 별도 WSL 터미널에서 확인합니다.

```bash
curl -fsS http://127.0.0.1:8001/health
```

## 7. Mock Sensor 및 실제 update

AI-AE 디렉터리의 별도 WSL 터미널에서 한 샘플을 보냅니다.

```bash
cd AI-AE
source .venv/bin/activate
python -m mec_safety.send_mock_data --once
```

sender는 Device1, Device2, Device4, Device5, Device3 순서로 측정 feature만 전송합니다.
CSV의 `risk_level` 라벨은 요청에 넣지 않습니다. 각 센서 update는 HTTP `200`,
`Layer2 success=True`, `RSC=2004`이어야 합니다. 마지막 Device3 요청 뒤 ML 예측과 Device6
Risk update(`success=True`, `RSC=2004`)를 확인합니다. 연속 전송은 `--once`를 빼고
`--interval-seconds 1`을 지정합니다.

Mock Sensor는 실제 runtime DB를 변경합니다. 데이터 확인은 `MN-CSE/runtime/data.db`를 기준으로
하고 `MN-CSE/data.db` seed는 수정하지 않습니다.

## 8. 재현 가능한 통합 확인 및 단위 테스트

세 서비스가 모두 실행 중일 때 프로젝트 루트에서 통합 검증기를 실행합니다.

```bash
cd "$(git rev-parse --show-toplevel)"
bash scripts/verify-mec.sh
```

이 검증기는 AI-AE health, CSE 연결과 리소스 schema, Mock Sensor 1회 전송, Device6 update,
runtime DB 변경 및 seed DB 불변을 확인합니다. 이미 실행 중인 서비스를 종료하지 않고 DB도
초기화하지 않습니다. 모델이 예측한 CRITICAL 입력이 있을 때만 PLC `STOP_ACCEPTED`와
`STOPPED` 응답을 검증하며, 해당 입력이 없으면 미실행으로 표시합니다.

단위 테스트는 통합 검증과 별도로 실행합니다.

```bash
cd AI-AE
source .venv/bin/activate
python -m pytest -q
```

pytest mock transport 테스트는 실제 MN-CSE에 쓰지 않습니다. 통합 검증의 Mock Sensor 단계는
실제 runtime DB를 변경합니다.

## 이번 WSL 실동작 검증 결과

- MN-CSE seed 설정/리소스 검증과 GCC 빌드가 성공했고, `run.py`가 runtime DB를 최초 생성한 뒤
  HTTP server를 시작했습니다. SDT definition 807개(21개 파일)가 로드됐습니다.
- CSE Base 및 Device1~Device6 GET은 HTTP `200`, RSC `2000`과 RI/schema 검증을 통과했습니다.
- AI-AE health가 응답했고, 다섯 센서 update와 Device6 Risk update는 HTTP `200`, RSC `2004`로
  성공했습니다.
- 일반 mock 샘플의 모델 결과는 `Medium`이었습니다. CSV의 위험도 라벨을 전달하지 않고 feature로
  예측된 CRITICAL 샘플도 별도로 검증했으며, Device6 update와 Mock PLC의
  `STOP_ACCEPTED` / `STOPPED` 응답을 확인했습니다.
- 검증 중 runtime DB는 업데이트됐고 seed DB는 변경되지 않았습니다.
- pytest 결과: **22 passed**, deprecation warning 1건(Starlette에서 AnyIO alias 사용 관련).

위 결과는 이번 WSL 환경에서 실행한 범위에 한정됩니다. 두 컴퓨터 간 LAN 연결, Dashboard,
재부팅 후 자동 기동은 검증하지 않았습니다.

## 9. 종료 및 데이터 보존

MN-CSE, AI-AE, Mock PLC는 각자 실행 중인 WSL 터미널에서 `Ctrl+C`로 종료합니다. 주요 포트는
MN-CSE TCP `3000`, AI-AE HTTP `8001`, Mock PLC TCP `9001`입니다.

- `MN-CSE/data.db`: 고정 Resource ID가 있는 seed DB이며 실행 중 직접 수정하지 않습니다.
- `MN-CSE/runtime/data.db`: 실제 실행 및 센서 update가 기록되는 런타임 DB입니다.
- `run.py`는 runtime DB가 이미 있으면 seed로 덮어쓰지 않습니다.
- DB 초기화 또는 교체는 사용자 데이터 손실을 일으킬 수 있으므로 백업 후 별도로 결정합니다.

독립 Linux x86_64 MEC Package의 빌드·구성 절차는 [패키징 가이드](PACKAGING.md)를 참고하세요.
Dashboard는 별도 개발 완료 상태이나 소스가 저장소에 통합되지 않아 Dashboard Package 및
Computer A/B 간 네트워크 통신은 검증 대상이 아닙니다.
