# TinyIoT MN-CSE

이 디렉터리의 루트가 TinyIoT 소스 루트입니다. 별도 `MN-CSE/tinyIoT/` 하위 디렉터리는
없습니다. 이번 통합 구성은 단일 MEC의 MN-CSE 모드이며, Registrar/Remote CSE 연결은
설정하지 않습니다.

## 빌드 설정

프로젝트 루트 `.env`를 단일 설정 원천으로 사용합니다. 최초 로컬 통합 설정:

```bash
python3 MN-CSE/scripts/build.py --init-local-env
```

이후 빌드:

```bash
python3 MN-CSE/scripts/build.py
```

빌드 환경은 WSL/Linux이며 GCC, GNU Make, pkg-config, OpenSSL 및 libwebsockets 개발 파일이
필요합니다. 스크립트는 `.env`의 TinyIoT 필수값, AI-AE Base Name/RVI, seed DB의 고정
Resource ID와 field schema를 검증합니다. Base RI는 seed DB에서 읽을 수 있으며 Base SP ID는
DB에 저장되지 않아 `.env`에 별도로 설정되어 있어야 합니다.

`config.h.in` 및 `Makefile.in`은 추적 템플릿입니다. build script가 `config.h`, `Makefile`을
생성하고 `make`를 실행하므로 자동 생성 파일을 직접 수정하지 않습니다. 기존
`autogen.sh`는 interactive이며 일반 통합 빌드 경로로 사용하지 않습니다.

## 데이터베이스와 실행

`data.db`는 빈 DB가 아닌 CSE Base 및 Device1~Device6 FlexContainer가 포함된 초기 seed입니다.
TinyIoT DB 초기화 코드는 현재 디렉터리의 `data.db`를 열고 테이블만 준비합니다. 빈 파일에서
Device1~6 리소스를 자동 생성하지 않습니다.

실행:

```bash
python3 MN-CSE/scripts/run.py
```

처음 실행할 때 seed DB를 `MN-CSE/runtime/data.db`로 복사하고 이후에는 해당 runtime DB를
재사용합니다. SDT definitions도 runtime working directory에 복사합니다. 따라서 실시간
업데이트를 `data.db` seed가 아닌 `runtime/data.db`에서 확인합니다.

## 네트워크 및 oneM2M 통신

- HTTP port: `.env`의 `TINYIOT_SERVER_PORT` (통합 기본 3000)
- HTTP listener bind: `0.0.0.0`
- CSE POA 광고 IP: `.env`의 `TINYIOT_SERVER_IP`
- AI-AE target: `CSE_BASE_URL=http://127.0.0.1:3000`
- CSE Base Name 및 RVI: `.env`의 `CSE_BASE_NAME`, `CSE_RVI`와 일치
- AI-AE write: 기존 Device1~Device6 Resource ID에 oneM2M HTTP PUT

`SERVER_IP`는 listener bind IP가 아니라 POA 광고값입니다.

## Dashboard 및 기타 범위

Dashboard는 별도 개발 중이고 이 저장소에 포함되지 않습니다. IN-CSE, Remote CSE 등록,
다중 MEC discovery, 자동 Resource ID 관리, Docker Compose 또한 현재 구현 범위가 아닙니다.
