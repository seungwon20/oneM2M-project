# TinyIoT IN-CSE

IN-CSE는 Computer B의 Monitoring Node에서 실행합니다. MEC Node의 TinyIoT MN-CSE가 Remote
CSE로 등록하면 Dashboard Backend는 local IN-CSE에 oneM2M 요청을 보내고, IN-CSE가 해당
MN-CSE로 요청을 전달합니다.

## 설정 및 빌드

WSL Ubuntu/Linux에서 GCC, GNU Make, pkg-config, OpenSSL 및 libwebsockets 개발 파일이
필요합니다. 프로젝트 루트 `.env`에 다음 설정이 필요합니다.

- listener POA 주소 및 port
- IN-CSE Base name, RI, SP ID
- MN-CSE와 일치하는 RVI 및 SP ID
- 선택적 개발 전용 administrator Originator (`IN_CSE_ADMIN_AE_ID`). Monitoring 패키지에는
  privileged administrator를 빌드하지 않습니다.
- `IN_CSE_ALLOWED_REMOTE_CSE_ID`에 포함되는 MEC MN-CSE ID

환경변수 이름과 의미는 [설정 문서](../docs/CONFIGURATION.md)를 참고합니다. 실제 ID/address를
문서나 로그에 복사하지 않습니다.

```bash
python3 IN-CSE/scripts/build.py
python3 IN-CSE/scripts/run.py
```

`build.py`는 root `.env`를 검증해 `config.h`를 생성한 뒤 native server를 빌드합니다.
`run.py`는 `.env` 설정을 프로세스 환경에 전달하고 runtime 디렉터리에서 server를 실행합니다.
`config.h`, `server` 및 runtime 데이터는 빌드/실행 생성물입니다.

Monitoring Package의 빌드 스크립트는 고정된 IN-CSE identity 및 MEC Seed DB의 Remote CSE
ID로 임시 build config를 생성합니다. 다운로드 사용자는 `PG_IN_CSE_ORIGIN`을 설정하고
IN-CSE의 최초 기동 전에 확정해야 합니다. 해당 Originator는 기본 AccessControl에서 조회
권한을 받으며, `IN_CSE_ADMIN_AE_ID`의 privileged 권한을 재사용하지 않습니다.

## Network 및 요청 경로

- IN-CSE HTTP listener는 설정된 `IN_CSE_SERVER_PORT`에서 실행됩니다. 통합 개발 예시는
  `3001`입니다.
- `IN_CSE_SERVER_IP`는 CSR의 POA에 포함되는 Monitoring Node 주소입니다. MEC Node에서
  접근 가능한 주소여야 하며 `127.0.0.1`을 원격 POA로 사용하면 안 됩니다.
- Dashboard Backend는 같은 Monitoring Node의 IN-CSE에 요청하므로 기본 패키지 설정은
  `http://127.0.0.1:3001`입니다.
- Dashboard의 Device 조회는 oneM2M SP-relative path
  `/~/<MN-CSE-ID>/DeviceN`를 사용합니다. MN-CSE ID, RVI, Originator와 IN-CSE access-control이
  일치해야 합니다.

IN-CSE는 MEC MN-CSE 없이도 자체 listener를 시작할 수 있습니다. 다만 원격 데이터 응답은
MN-CSE 등록과 POA 네트워크 연결이 성공하기 전까지 제공되지 않습니다.

## 패키지와 검증

IN-CSE는 [Monitoring Package](../docs/PACKAGING.md)에 Dashboard와 함께 포함됩니다. 실제 두
장비 간 연결, 방화벽, Remote CSE 등록, forwarding 및 운영 access-control 검증은 별도로
수행해야 하며, WSL 단일 노드 실행만으로 완료된 것으로 보지 않습니다.
