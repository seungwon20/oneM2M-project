# TinyIoT MN-CSE

이 디렉터리는 MEC Node에서 실행하는 TinyIoT Middle Node CSE 소스와 Seed DB입니다. 기본
배포에서 AI-AE는 같은 Computer A의 MN-CSE에 로컬 HTTP로 연결하고, Monitoring Node의
IN-CSE는 등록된 Remote CSE로 접근합니다.

## 빌드 환경과 설정

WSL Ubuntu/Linux에서 GCC, GNU Make, pkg-config, OpenSSL 및 libwebsockets 개발 파일이
필요합니다. 프로젝트 루트 `.env`를 사용합니다.

```bash
python3 MN-CSE/scripts/build.py --init-local-env
# root .env에서 환경별 Originator, Resource ID 및 SP ID 확인/설정
python3 MN-CSE/scripts/build.py
```

빌드 스크립트는 필수 설정, MN mode, CSE Base Name/RVI 및 Seed DB의 Resource ID/schema를
검증하고 `config.h`, `Makefile`을 생성해 컴파일합니다. `TINYIOT_CSE_BASE_SP_ID`는 Seed DB에서
읽히지 않으므로 직접 설정해야 합니다. 생성된 파일을 직접 편집하지 않습니다.

## Seed DB, Runtime DB 및 실행

`data.db`는 CSE Base 및 Device1~Device6 FlexContainer가 포함된 Seed DB입니다. 최초 실행 시
`MN-CSE/runtime/data.db`에 복사되며, 이후 실행에서 기존 runtime DB를 유지합니다. 실제 센서
업데이트는 runtime DB에서 확인합니다.

```bash
python3 MN-CSE/scripts/run.py
```

SDT definitions도 runtime working directory에 복사됩니다. Runtime DB를 초기화하거나 Seed DB로
덮어쓰는 작업 전에는 사용자 데이터를 백업해야 합니다.

## 주소와 oneM2M 연결

- HTTP listener는 `0.0.0.0`에 bind합니다.
- `TINYIOT_SERVER_PORT`는 listener 포트이며 통합 기본값은 `3000`입니다.
- `TINYIOT_SERVER_IP`는 CSE Base POA에 광고하는 MEC Node 주소입니다. 다른 장비에서 접근
  가능해야 하며 listener bind address와 다릅니다.
- AI-AE의 `CSE_BASE_URL`은 same-node loopback 연결입니다. 현재 root build validation은
  `http://127.0.0.1:3000`을 요구합니다.
- MEC Package의 Remote CSE endpoint는 `REMOTE_CSE_ID`, `REMOTE_CSE_NAME`,
  `REMOTE_CSE_HOST`, `REMOTE_CSE_PORT` runtime 환경 설정으로 전달됩니다. 대상은 Monitoring
  Node의 IN-CSE입니다.
- Remote CSE가 설정된 경우 등록/CSR 생성은 백그라운드 재시도합니다. IN-CSE가 아직
  도달되지 않아도 로컬 MN-CSE는 시작할 수 있으며, 등록 상태가 ready라는 의미는 아닙니다.

## 패키지와 범위

[MEC Package](../docs/PACKAGING.md)는 MN-CSE 및 AI-AE를 포함하고,
[배포 가이드](../docs/DEPLOYMENT.md)는 POA 및 원격 연결 설정을 설명합니다. 다중 MEC
discovery, 별도 registry, 자동 failover는 현재 범위가 아닙니다.
