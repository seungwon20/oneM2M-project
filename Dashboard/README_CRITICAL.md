# PinchGuard 자동 위험 시나리오 — CRITICAL 포함

## 변경점

- 기존 3단계(SAFE / WARNING / HIGH) → **4단계(SAFE / WARNING / HIGH / CRITICAL)**
- UNKNOWN은 센서·판정값 유효성 부족에 사용하는 독립 상태로 유지
- 자동 시나리오: **SAFE → WARNING → HIGH → CRITICAL → HIGH → WARNING → SAFE**
- 자동 송신기, FastAPI `/api/risk`, `/api/demo`, `/notify`, 웹 UI, SQLite 통계 모두 수정
- HIGH와 CRITICAL을 이벤트 기록에서 별도 집계 (`stats.high_events`, `stats.critical_events`)
- 데모 버튼에 **매우 위험** 추가, 최고 위험 색상을 자홍/진홍 계열로 구분

## 실행 (WSL Ubuntu)

첫 번째 터미널:

```bash
cd /mnt/c/Users/minea/desktop/PinchGuard_Dashboard_CRITICAL
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-camera.txt
export PG_INGEST_KEY='local-dev-change-me'
uvicorn app:app --host 127.0.0.1 --port 8000
```

두 번째 터미널:

```bash
cd /mnt/c/Users/minea/desktop/PinchGuard_Dashboard_CRITICAL
source .venv/bin/activate
export PG_API_KEY='local-dev-change-me'
python camera_sender.py --source synthetic --url http://localhost:8000/api/frame --fps 10 --cycle-seconds 24
```

Windows에서 `http://localhost:8000` 접속. 기존에 8000 포트에서 실행 중인 서버가 있다면 종료 후 새 버전으로 실행하세요.

더 빠른 촬영은 `--cycle-seconds 12`로 단축할 수 있습니다.

## 시연용 위험 등급 기준 (실제 산업 안전 기준 아님)

| 등급 | 예제 조건 |
|---|---|
| CRITICAL | 설비 가동 + 작업자 존재 + 광전식 차단 + 거리 ≤ 20cm |
| HIGH | 설비 가동 + 작업자 존재 + (광전식 차단 또는 거리 ≤ 45cm), CRITICAL 제외 |
| WARNING | 설비 가동 + 작업자 존재 + 거리 ≤ 105cm, 상위 등급 제외 |
| SAFE | 위 조건을 만족하지 않는 정상 데모 상태 |
| UNKNOWN | 필수 센서 입력 없음 또는 결과 유효 기간 초과 |

영상과 센서·위험 값은 **규칙 기반의 가상 시뮬레이션**입니다. CRITICAL은 실제 끼임 사고의 감지나 설비 정지 기능을 의미하지 않습니다.
