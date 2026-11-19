# PinchGuard Dashboard - direct MN-CSE integration

This update adds a **server-side direct HTTP GET client** from the existing FastAPI dashboard to the team's MN-CSE. It does not perform oneM2M Remote CSE Registration and does not route through the local IN-CSE.

## What changed

- `GET /api/onem2m/devices` retrieves `Device1` through `Device6` from the configured MN-CSE in parallel.
- The dashboard has a separate **Remote oneM2M / MN-CSE** panel, refreshed every 5 seconds.
- The panel displays the original scalar FlexContainer attributes, source timestamp, data age, and freshness status.
- Device-specific attributes are not forced into the dashboard's existing generic `distance_cm` / `rpm` sensor model.
- A failed device request is displayed independently; one unavailable device does not hide the other five.
- Existing `/api/state`, `/notify`, camera, sensor, risk, demo/live mode, and SQLite event handling remain in place.

## Configure on the computer running FastAPI

The MN-CSE URL must be configured in the **FastAPI server process environment**, not in the browser and not on the teammate's machine. In PowerShell, before starting Uvicorn:

```powershell
$env:PG_MN_CSE_URL = "http://172.19.17.34:3000"
$env:PG_MN_CSE_BASE = "TinyIoT"
$env:PG_MN_CSE_CONTAINER = "EdgeGuardMEC"
$env:PG_MN_CSE_ORIGIN = "CAdmin"
$env:PG_MN_CSE_RVI = "3"
$env:PG_MN_CSE_TIMEOUT = "3"
$env:PG_MN_CSE_FRESH_SECONDS = "30"
```

Then start the existing application from this project directory:

```powershell
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

If the dashboard is run in WSL/Linux, use `export PG_MN_CSE_URL=...` etc. in the same shell that launches Uvicorn.

`172.19.17.34` is the endpoint that was tested in the supplied session. It may change when the teammate restarts WSL, changes networks, or changes VPN routing. If it changes, update `PG_MN_CSE_URL` and verify reachability from the FastAPI host.

## Verify

From the computer running the dashboard:

```powershell
curl.exe http://127.0.0.1:8000/api/onem2m/devices
```

Expected response shape:

```json
{
  "source": "MN-CSE",
  "configured": true,
  "success_count": 6,
  "device_count": 6,
  "connected": true,
  "devices": [
    {
      "device_id": "Device5",
      "ok": true,
      "http_status": 200,
      "resource_type": 28,
      "data": {
        "rn": "Device5",
        "ty": 28,
        "distance_cm": 88.8
      },
      "fresh": false
    }
  ]
}
```

The example above is abbreviated. `fresh` is calculated from the source `received_at` or `evaluated_at` timestamp against `PG_MN_CSE_FRESH_SECONDS`; it is **not** based on the time the dashboard fetched the record. A successful HTTP 200 response can therefore still contain stale sensor data.

## Important interpretation and limitations

1. A successful `/api/onem2m/devices` response proves that FastAPI can directly retrieve the configured MN-CSE resources. It does **not** prove IN-CSE ↔ MN-CSE Remote CSE Registration.
2. The current six records contain heterogeneous telemetry. For example, Device1 has people counts, Device2 has weight, Device3 has a beam state, Device4 has rotation state/speed, Device5 has distance, and Device6 has risk/speed/distance. The dashboard presents those values as source attributes without inventing a unified safety decision.
3. The existing top-level risk assessment remains driven by its existing `/api/risk` or `/notify` ingestion path. Device6's `risk_level` is shown in the MN-CSE device panel only; it is not silently promoted into the existing fusion-risk card.
4. The observed sample timestamps were from 2026-11-11. Until new source timestamps arrive, those values should appear as stale under the default 30-second threshold.
5. `CAdmin` is the originator used in the successful manual tests. For a shared or production environment, use a least-privilege originator/ACP policy and do not expose the CSE publicly.
6. This is an educational PoC dashboard, not a certified industrial safety controller. It does not command machinery or validate safety thresholds.

## Tests

Run:

```powershell
python -m pytest -q
```

The automated tests use mocked MN-CSE responses. They validate parsing and API behavior, not the live teammate network connection.


## 10초 자동 동기화
FastAPI 서버가 시작되면 별도 백그라운드 스레드가 즉시 MN-CSE Device1~6을 조회하고 이후 10초 간격으로 다시 조회합니다. 브라우저가 닫혀 있어도 서버가 실행 중이면 동작합니다. `/api/onem2m/devices`는 마지막 수집 결과를 반환하며, 브라우저도 10초마다 화면을 갱신합니다. 환경변수 `PG_MN_CSE_POLL_SECONDS=10`으로 설정합니다. 실시간 push가 아닌 10초 주기 polling이며, 원본 센서값의 최신성은 별도로 판정합니다. Uvicorn은 `--workers 1`로 실행해 중복 폴링을 방지하세요.
