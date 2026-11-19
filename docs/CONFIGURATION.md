# 환경변수 및 설정 관리

프로젝트 루트 `.env`가 AI-AE와 MN-CSE 통합 설정의 단일 원천입니다. 실제 Originator,
Resource ID 등 사용자별 값은 이 문서에 복사하지 않습니다.

## 설정 초기화와 보안

- 예시: [`.env.example`](../.env.example)
- 로컬 설정: 프로젝트 루트 `.env` (Git ignore 대상)
- AI-AE: `python-dotenv`가 루트 `.env`를 로드하며, OS 환경변수가 있으면 우선합니다.
- MN-CSE: `MN-CSE/scripts/build.py`가 같은 파일을 읽어 생성 설정에 적용합니다.

```bash
python3 MN-CSE/scripts/build.py --init-local-env
```

위 초기화 옵션은 현재 단일 컴퓨터에 맞는 연결 설정을 적용하며 기존 `AE_ID`와 six Resource
ID는 건드리지 않습니다. 일반 빌드에는 `--init-local-env`를 붙이지 않습니다.
`.env` 전체를 저장소나 로그에 복사하지 마세요.

## AI-AE 연결 변수

| 변수 | 의미 |
|---|---|
| `CSE_BASE_URL` | AI-AE가 PUT/GET 요청할 MN-CSE 주소. 통합 목표는 `http://127.0.0.1:3000` |
| `CSE_BASE_NAME` | CSE Base 이름, TinyIoT 설정과 일치해야 함 |
| `CSE_RVI` | oneM2M RVI. 현재 CSE 빌드 값과 일치해야 함 |
| `AE_NAME` | AI-AE의 설정 이름 |
| `AE_ID` | 요청 `X-M2M-Origin`에 쓰는 Originator |
| `FCNT_DEVICE1_RI`~`FCNT_DEVICE5_RI` | Camera, Weight, Infrared, Encoder, Distance FlexContainer RI |
| `FCNT_RISK_RI` | Device6 Risk FlexContainer RI |

AI-AE는 `Layer2Handoff`에서 각 고정 RI에 HTTP PUT을 보내고 HTTP 200, RSC 2004,
응답 RI 일치를 성공 조건으로 확인합니다. CSE 리소스 생성이나 ID discovery는 하지 않습니다.

## TinyIoT 빌드 변수

| 변수 | 의미 |
|---|---|
| `TINYIOT_SERVER_TYPE` | 실행 모드. 현재 `mn`만 지원 |
| `TINYIOT_SERVER_IP` | MN-CSE CSE Base의 POA에 광고할 IPv4 주소 |
| `TINYIOT_SERVER_PORT` | HTTP listener port 및 POA port |
| `TINYIOT_CSE_BASE_NAME` | CSE Base resource name |
| `TINYIOT_CSE_BASE_RI` | CSE Base 고정 Resource ID |
| `TINYIOT_CSE_BASE_SP_ID` | CSE Base의 service-provider ID |

`CSE_RVI`도 TinyIoT `config.h`의 `CSE_RVI` 매크로로 컴파일됩니다. 별도의 `TINYIOT_*_RVI`
값을 두지 않고 두 컴포넌트가 같은 루트 변수에 의존합니다.

빌드 스크립트는 `TINYIOT_SERVER_TYPE=mn`, 로컬 목표 URL, Base Name/RVI 일치, 필수값 및
seed DB의 Base/Device1~Device6 ID와 schema를 검사합니다. 누락, placeholder, DB mismatch는
값을 노출하지 않고 오류 처리합니다.

## SERVER_IP와 주소의 차이

`MN-CSE/httpd.c`의 HTTP listener는 현재 `0.0.0.0`에 bind합니다. `SERVER_IP`는 `util.c`가
oneM2M CSE Base의 `poa`에 기록하는 주소이며, bind 제한 주소가 아닙니다.

- 단일 컴퓨터 구성: POA IP를 loopback으로 설정하고 AI-AE 요청 주소를 별도로
  `http://127.0.0.1:3000`으로 설정
- 다른 호스트/네트워크 구성: `TINYIOT_SERVER_IP`는 peer가 도달할 수 있는 광고 주소,
  `CSE_BASE_URL`은 AI-AE가 실제 요청할 주소
- 두 값은 같은 의미가 아니며 반드시 같을 필요 없음

## Resource ID와 DB

Device1~Device6 ID는 현재 seed DB와 기존 `.env` 사이에서 모두 일치함을 확인했습니다.
기존 DB ID를 수정하거나 자동 생성하지 않습니다.

- `MN-CSE/data.db`: 초기 seed. CSE Base와 six FlexContainer, custom field 포함
- `MN-CSE/runtime/data.db`: `run.py`가 seed에서 첫 실행에 복사하는 writable DB
- `sqlite_implement.c`는 현재 working directory의 `data.db`를 엽니다.
- DB 초기화는 누락 테이블을 생성할 뿐 여섯 사용자 리소스를 bootstrap하지 않습니다.

새 배포에서 고정 ID를 재현하려면 seed DB를 버전/백업 관리하고 런타임 DB와 분리합니다.
런타임 DB가 이미 있으면 `run.py`는 seed로 덮어쓰지 않습니다.
`.env.example`의 Base RI 및 SP ID는 placeholder입니다. 최초 로컬 초기화 옵션은 seed DB에서
Base RI를 읽지만, DB에 저장되지 않는 SP ID는 운영자가 확인해 `.env`에 설정해야 합니다.

## Registrar / Remote CSE

Registrar CSE와 Remote CSE 연결은 확정되지 않았습니다. `.env`에 해당 연결값을 추가하지 않으며
MN-CSE build 설정의 Remote CSE 값은 빈 값/비활성 값으로 유지합니다.

현재 구성은 단일 MN-CSE이며 IN-CSE, discovery, MEC registry는 포함하지 않습니다.

## 포트와 런타임 설정

| 컴포넌트/기능 | 현재 설정 |
|---|---|
| TinyIoT HTTP | `TINYIOT_SERVER_PORT`, 통합값 3000 |
| AI-AE HTTP | Uvicorn 인자, 통합 예시 8001 |
| Mock PLC TCP | 코드 고정 기본값 `127.0.0.1:9001` |
| Runtime DB | `MN-CSE/runtime/data.db` |

AI-AE listen port와 PLC endpoint는 현재 루트 `.env` 설정이 아닙니다.

## 민감 정보 원칙

- `.env`, Originator, Resource ID를 커밋/문서화하지 않습니다.
- 전체 환경변수 덤프를 빌드 로그에 추가하지 않습니다.
- build 검증 결과는 일치 여부만 출력합니다.
- runtime DB에는 실제 센서/위험도 값이 기록되므로 접근 권한과 백업을 관리합니다.
