"""PinchGuard educational operations dashboard.

Never use this software for certified machinery safety control.
Data marked as DEMO is synthetic; EDGE denotes a locally hosted receiver,
not evidence of a deployed ETSI MEC app.
"""
from __future__ import annotations

import hmac
import io
import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv('PG_DB_PATH', str(ROOT / 'pinchguard.sqlite3')))
INGEST_KEY = os.getenv('PG_INGEST_KEY', 'local-dev-change-me')
DEMO_ALLOWED = os.getenv('PG_ENABLE_DEMO', '1') == '1'
FRESH_SECONDS = int(os.getenv('PG_FRESH_SECONDS', '15'))
FRAME_LIMIT = 2_000_000
MAX_EVENT_BODY = 1_000_000

# Dashboard reads the remote MN-CSE through the local IN-CSE registrar.
IN_CSE_URL = os.getenv('PG_IN_CSE_URL', '').rstrip('/')
MN_CSE_ID = os.getenv('PG_MN_CSE_ID', '').strip('/')
IN_CSE_ORIGIN = os.getenv('PG_IN_CSE_ORIGIN', '')
IN_CSE_RVI = os.getenv('PG_IN_CSE_RVI', '3')
IN_CSE_TIMEOUT = float(os.getenv('PG_IN_CSE_TIMEOUT', '3'))
MN_CSE_FRESH_SECONDS = int(os.getenv('PG_MN_CSE_FRESH_SECONDS', '30'))
MN_CSE_POLL_SECONDS = max(1.0, float(os.getenv('PG_MN_CSE_POLL_SECONDS', '10')))
MN_DEVICE_IDS = tuple(f'Device{i}' for i in range(1, 7))

app = FastAPI(title='PinchGuard Control Center', version='0.1.0')
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
lock = threading.RLock()
view_mode = 'demo' if DEMO_ALLOWED else 'live'
latest_sensor: dict[str, dict[str, Any]] = {}
latest_risk: dict[str, dict[str, Any]] = {}
latest_frame: dict[str, dict[str, Any]] = {}
frame_bytes: dict[str, bytes] = {}
frame_times: dict[str, list[float]] = {}
one_m2m_last: float | None = None
one_m2m_verify_count = 0


def utc_iso(seconds: float | None = None) -> str:
    return datetime.fromtimestamp(seconds or time.time(), tz=timezone.utc).isoformat(timespec='seconds')


def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            received_at REAL NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            device_id TEXT NOT NULL,
            description TEXT NOT NULL,
            source TEXT NOT NULL,
            data_json TEXT NOT NULL,
            is_demo INTEGER NOT NULL DEFAULT 0,
            ack_at TEXT,
            event_key TEXT
        )''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_events_mode ON events(is_demo,received_at DESC)')
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_events_key ON events(event_key) WHERE event_key IS NOT NULL')


init_db()


def store_event(category: str, severity: str, device_id: str, description: str,
                source: str, payload: dict[str, Any], demo=False, event_key=None, received_at=None) -> int | None:
    try:
        with conn() as c:
            cur = c.execute('''INSERT INTO events
            (received_at,category,severity,device_id,description,source,data_json,is_demo,event_key)
            VALUES (?,?,?,?,?,?,?,?,?)''', (
                received_at or time.time(), category, severity, str(device_id)[:100],
                str(description)[:400], str(source)[:80], json.dumps(payload, ensure_ascii=False),
                int(demo), event_key,
            ))
            return cur.lastrowid
    except sqlite3.IntegrityError:
        return None


def require_key(x_api_key: str | None):
    if not INGEST_KEY or not x_api_key or not hmac.compare_digest(x_api_key, INGEST_KEY):
        raise HTTPException(401, 'Invalid or missing X-API-Key')


def severity_value(value: Any) -> str:
    s = str(value).upper()
    return s if s in ('SAFE', 'WARNING', 'HIGH', 'CRITICAL', 'UNKNOWN') else 'UNKNOWN'


def new_sensor(data: dict[str, Any], *, demo=False, source='DIRECT_API'):
    now = time.time()
    d = {
        'device_id': str(data.get('device_id', 'sensor-01'))[:80],
        'distance_cm': data.get('distance_cm'),
        'presence': data.get('presence', data.get('person_present')),
        'machine_running': data.get('machine_running'),
        'beam_blocked': data.get('beam_blocked'),
        'rpm': data.get('rpm'),
        'sequence': data.get('sequence'),
        'timestamp_utc': data.get('timestamp_utc'),
        'source': source,
        'received_at': now,
        'demo': demo,
        'simulation': data.get('simulation') is True,
    }
    if d['distance_cm'] is None and isinstance(data.get('distance_m'), (int,float)):
        d['distance_cm'] = round(float(data['distance_m']) * 100, 2)
    for k in ('distance_cm', 'rpm'):
        v = d[k]
        if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or not (0 <= v <= 100000)):
            raise HTTPException(422, f'Invalid {k}')
    for k in ('presence', 'machine_running', 'beam_blocked'):
        if d[k] is not None and not isinstance(d[k], bool):
            raise HTTPException(422, f'Invalid boolean {k}')
    with lock:
        latest_sensor['demo' if demo else 'live'] = d
    store_event('SENSOR', 'INFO', d['device_id'], '센서 값 수신', source, d, demo=demo)
    return d


def new_risk(data: dict[str, Any], *, demo=False, source='DIRECT_API', event_key=None):
    now = time.time()
    level = severity_value(data.get('risk_level'))
    d = {
        'event_id': str(data.get('event_id', f'evt-{int(now * 1000)}'))[:120],
        'risk_level': level,
        'description': str(data.get('description') or {
            'HIGH':'끼임 위험 이벤트', 'CRITICAL':'매우 높은 끼임 위험 경고', 'WARNING':'위험구역 접근 감지',
            'SAFE':'위험 신호 없음', 'UNKNOWN':'분석 결과 불명확'
        }[level])[:400],
        'source': source,
        'camera_id': data.get('camera_id'),
        'distance_cm': data.get('distance_cm',
                      round(float(data['distance_m'])*100,2) if isinstance(data.get('distance_m'), (int,float)) else None),
        'timestamp_utc': data.get('timestamp_utc'),
        'received_at': now,
        'demo': demo,
        'simulation': data.get('simulation') is True,
    }
    with lock:
        latest_risk['demo' if demo else 'live'] = d
    event_id = store_event('RISK', level, str(data.get('camera_id') or data.get('device_id') or 'Fusion Engine'),
                            d['description'], source, {**data, **d}, demo=demo, event_key=event_key)
    return d, event_id


class SensorIn(BaseModel):
    model_config = ConfigDict(extra='allow')
    device_id: str = Field(min_length=1, max_length=80)
    distance_cm: float | None = Field(default=None, ge=0, le=100000)
    presence: bool | None = None
    machine_running: bool | None = None
    beam_blocked: bool | None = None
    rpm: float | None = Field(default=None, ge=0, le=100000)
    sequence: int | None = None
    timestamp_utc: str | None = None


class RiskIn(BaseModel):
    model_config = ConfigDict(extra='allow')
    event_id: str | None = None
    risk_level: Literal['SAFE','WARNING','HIGH','CRITICAL','UNKNOWN']
    description: str | None = None
    camera_id: str | None = None
    distance_cm: float | None = None
    timestamp_utc: str | None = None


class DemoIn(BaseModel):
    scenario: Literal['SAFE','WARNING','HIGH','CRITICAL','UNKNOWN']


class ModeIn(BaseModel):
    mode: Literal['demo','live']


@app.get('/')
def index():
    return FileResponse(ROOT / 'static' / 'index.html')


@app.get('/health')
def health():
    return {'status':'ok', 'service':'pinchguard-dashboard','note':'not an industrial safety controller'}


# PINCHGUARD_MN_HISTORY_v1: per-resource revision last recorded in the LIVE log
_pg_mn_last_revision = {}

@app.get('/api/state')
def state():
    global one_m2m_last
    now = time.time()
    with lock:
        m = view_mode
        s = dict(latest_sensor.get(m, {}))
        r = dict(latest_risk.get(m, {}))
        f = dict(latest_frame.get(m, {}))
        link = one_m2m_last
        verified = one_m2m_verify_count
        live_times = frame_times.get(m, [])[:]
    # PINCHGUARD_MN_LIVE_BRIDGE_v1
    # LIVE 화면에 별도로 폴링한 MN-CSE 장치별 데이터를 반영한다.
    # 원본 수신 시각을 사용하며, 오래된 데이터를 새 데이터처럼 표시하지 않는다.
    if m == 'live' and _in_cse_configured():
        from datetime import datetime as _mn_datetime, timezone as _mn_timezone
        with _mn_cache_lock:
            _mn_snapshot = dict(_mn_cache) if _mn_cache is not None else {}
        _mn_devices = {
            item.get('device_id'): item
            for item in _mn_snapshot.get('devices', [])
            if isinstance(item, dict) and item.get('ok')
        }

        def _mn_fresh_device(number):
            item = _mn_devices.get(f'Device{number}', {})
            raw_timestamp = item.get('source_timestamp')
            if not isinstance(raw_timestamp, str):
                return None
            try:
                stamp = _mn_datetime.fromisoformat(raw_timestamp.replace('Z', '+00:00'))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=_mn_timezone.utc)
                source_epoch = stamp.timestamp()
            except (ValueError, TypeError, OverflowError):
                return None
            age = now - source_epoch
            if not (-2 <= age <= MN_CSE_FRESH_SECONDS):
                return None
            payload = item.get('data')
            return (payload, source_epoch) if isinstance(payload, dict) else None

        # CSE가 설정됐으면 LIVE 화면에서 오래된 다른 경로의 값을 섞지 않는다.
        s, r = {}, {}
        _d5 = _mn_fresh_device(5)
        if _d5 is not None:
            _v5, _t5 = _d5
            s = {
                'received_at': _t5,
                'device_id': 'EdgeGuardMEC',
                'source': 'MN-CSE',
                'distance_cm': _v5.get('distance_cm'),
            }
            for _idx, _fields in (
                (1, ('zone_person_count', 'total_person_count')),
                (2, ('weight_kg',)),
                (3, ('beam_blocked',)),
                (4, ('is_rotating', 'speed_rpm')),
            ):
                _extra = _mn_fresh_device(_idx)
                if _extra is not None:
                    _values, _ = _extra
                    for _field in _fields:
                        if _field in _values:
                            s[_field] = _values[_field]
            if 'is_rotating' in s:
                s['machine_running'] = s['is_rotating']
            if 'speed_rpm' in s:
                s['rpm'] = s['speed_rpm']
            if isinstance(s.get('zone_person_count'), int):
                s['presence'] = s['zone_person_count'] > 0

        _d6 = _mn_fresh_device(6)
        if _d6 is not None:
            _v6, _t6 = _d6
            _risk_levels = {
                'low': 'SAFE', 'medium': 'WARNING',
                'high': 'HIGH', 'critical': 'CRITICAL',
            }
            _level = _risk_levels.get(str(_v6.get('risk_level', '')).strip().lower())
            if _level is not None:
                r = {
                    'received_at': _t6,
                    'risk_level': _level,
                    'source': 'MN-CSE Device6',
                    'description': 'MEC에서 수신해 MN-CSE에 저장한 위험도',
                    'distance_cm': _v6.get('distance_cm'),
                    'rpm': _v6.get('speed_rpm'),
                }
    # PINCHGUARD_MN_HISTORY_v1: persist the *source* revisions, not every GET.
    # Do not generate synthetic/derived risk decisions here; only record Device6.
    if m == 'live' and _in_cse_configured():
        with lock:
            if _d5 is not None and s:
                _rev5 = f"Device5:{_v5.get('st')}:{_t5:.3f}"
                if _pg_mn_last_revision.get('Device5') != _rev5:
                    _e5 = store_event(
                        'SENSOR', 'INFO', 'Device5',
                        'MN-CSE Device5 거리 측정값 수신', 'MN-CSE Device5',
                        {**s, 'cse_st': _v5.get('st'), 'source_timestamp': _v5.get('received_at')},
                        demo=False, event_key='PG-MN:' + _rev5, received_at=_t5,
                    )
                    _pg_mn_last_revision['Device5'] = _rev5
            if _d6 is not None and r:
                _rev6 = f"Device6:{_v6.get('st')}:{_t6:.3f}"
                if _pg_mn_last_revision.get('Device6') != _rev6:
                    _e6 = store_event(
                        'RISK', r['risk_level'], 'Device6',
                        f"MEC 위험도 평가 수신: {r['risk_level']}", 'MN-CSE Device6',
                        {**r, 'cse_st': _v6.get('st'), 'source_timestamp': _v6.get('evaluated_at'),
                         'mec_risk_level': _v6.get('risk_level')},
                        demo=False, event_key='PG-MN:' + _rev6, received_at=_t6,
                    )
                    _pg_mn_last_revision['Device6'] = _rev6
    s_age = round(now - s['received_at'],1) if s else None
    r_age = round(now - r['received_at'],1) if r else None
    f_age = round(now - f['received_at'],1) if f else None
    risk_is_fresh = bool(r and r_age is not None and r_age <= FRESH_SECONDS)
    risk_level = r['risk_level'] if risk_is_fresh else 'UNKNOWN'
    video_ok = f_age is not None and f_age <= 5
    live_times = [x for x in live_times if now - x <= 10]
    fps = round(sum(x >= now-3 for x in live_times)/3,1) if video_ok else 0
    with conn() as c:
        events = [dict(x) for x in c.execute('''SELECT id,received_at,category,severity,device_id,description,
                 source,is_demo,ack_at,data_json FROM events WHERE is_demo=? ORDER BY id DESC LIMIT 35''', (int(m=='demo'),))]
        counts = c.execute('SELECT COUNT(*) total, SUM(CASE WHEN severity="HIGH" THEN 1 ELSE 0 END) highs, SUM(CASE WHEN severity="CRITICAL" THEN 1 ELSE 0 END) criticals FROM events WHERE is_demo=? AND category=\"RISK\"',(int(m=='demo'),)).fetchone()
        history = [dict(x) for x in c.execute('''SELECT received_at,data_json FROM events WHERE is_demo=? AND category='SENSOR' ORDER BY id DESC LIMIT 60''',(int(m=='demo'),))]
    for e in events:
        e['received_at_iso'] = utc_iso(e['received_at'])
        e['payload'] = json.loads(e.pop('data_json'))
    chart = []
    for h in reversed(history):
        data = json.loads(h['data_json'])
        if isinstance(data.get('distance_cm'), (int,float)):
            chart.append({'t':h['received_at'],'v':round(float(data['distance_cm']),2)})
    return {
      'mode':m, 'demo_allowed':DEMO_ALLOWED,'server_time':utc_iso(now),
      'risk': {'level':risk_level,'last_result':r or None,'age_sec':r_age,'fresh':risk_is_fresh},
      'sensor': {'latest':s or None,'age_sec':s_age,'fresh':s_age is not None and s_age <= FRESH_SECONDS},
      'camera':{'latest':f or None,'age_sec':f_age,'online':video_ok,'fps':fps},
      'one_m2m':{'last_notification':utc_iso(link) if link else None,
                 'notification_age_sec':round(now-link,1) if link else None,
                 'verification_count':verified},
      'stats':{'risk_events':counts['total'] or 0,'high_events':counts['highs'] or 0,'critical_events':counts['criticals'] or 0,'recent_events':len(events)},
      'events':events,'history':chart, 'fresh_threshold_sec':FRESH_SECONDS,
      'deployment':'LOCAL EDGE SERVER (MEC sandbox deployment not verified)',
    }


@app.post('/api/sensor')
def sensor(data: SensorIn, x_api_key: str | None=Header(None)):
    require_key(x_api_key)
    payload = data.model_dump(exclude_none=True)
    item = new_sensor(payload, source='SIMULATED_RULES' if payload.get('simulation') is True else 'DIRECT_API')
    return {'accepted':True,'received_at':utc_iso(item['received_at'])}


@app.post('/api/risk')
def risk(data: RiskIn, x_api_key: str | None=Header(None)):
    require_key(x_api_key)
    payload = data.model_dump(exclude_none=True)
    item, event_id = new_risk(payload, source='SIMULATED_RULES' if payload.get('simulation') is True else 'DIRECT_API')
    return {'accepted':True,'event_id':event_id,'level':item['risk_level']}


@app.post('/api/frame')
async def frame(request: Request, x_api_key: str | None=Header(None)):
    require_key(x_api_key)
    if request.headers.get('content-type','').split(';')[0].strip().lower() != 'image/jpeg':
        raise HTTPException(415,'Expected image/jpeg')
    payload = bytearray()
    async for part in request.stream():
        payload.extend(part)
        if len(payload)>FRAME_LIMIT:
            raise HTTPException(413,'Frame is too large')
    if len(payload)<4 or not payload.startswith(b'\xff\xd8') or not payload.endswith(b'\xff\xd9'):
        raise HTTPException(400,'Invalid JPEG framing')
    try:
        with Image.open(io.BytesIO(payload)) as jpeg:
            if jpeg.format != 'JPEG':
                raise ValueError('Not JPEG')
            width, height = jpeg.size
            if width * height > 16_000_000:
                raise ValueError('Frame dimensions exceed limit')
            jpeg.verify()
    except (ValueError, OSError, UnidentifiedImageError):
        raise HTTPException(400,'Corrupted or oversized JPEG')
    device_id = request.headers.get('x-camera-id','cam-01')[:64]
    frame_id = request.headers.get('x-frame-id','-')[:64]
    now = time.time()
    item = {'camera_id':device_id,'frame_id':frame_id,'jpeg_bytes':len(payload),'received_at':now,'width':width,'height':height,'source':'HTTP_JPEG','simulation': request.headers.get('x-pg-simulation','0') == '1'}
    with lock:
        latest_frame['live']=item
        frame_bytes['live']=bytes(payload)
        frame_times.setdefault('live',[]).append(now)
        frame_times['live'] = frame_times['live'][-120:]
    return {'accepted':True,'camera_id':device_id,'frame_id':frame_id,'received_at_ms':int(now*1000),'inference_status':'NOT_CONNECTED'}


@app.get('/api/frame/latest')
def frame_latest():
    with lock:
        frame_image=frame_bytes.get('live')
    if not frame_image:
        raise HTTPException(404,'No live frame received')
    return Response(content=frame_image, media_type='image/jpeg', headers={'Cache-Control':'no-store, max-age=0'})


def _parse_onem2m_device(device_id: str, body: Any) -> dict[str, Any]:
    """Unwrap a TinyIoT FlexContainer response without inventing sensor fields."""
    if not isinstance(body, dict):
        raise ValueError('CSE response must be a JSON object')
    resource = body.get(f'eg:{device_id}')
    if not isinstance(resource, dict):
        # Some CSE implementations may return a generic wrapper; accept only an
        # unambiguous resource object with the expected rn.
        resource = next((v for v in body.values() if isinstance(v, dict) and v.get('rn') == device_id), None)
    if not isinstance(resource, dict):
        raise ValueError(f'{device_id} resource wrapper not found')
    if resource.get('rn') != device_id:
        raise ValueError(f'{device_id} resource name mismatch')
    return resource


def _in_cse_configured() -> bool:
    return bool(IN_CSE_URL and MN_CSE_ID and IN_CSE_ORIGIN and IN_CSE_RVI)


def _fetch_onem2m_device(device_id: str) -> dict[str, Any]:
    if not _in_cse_configured():
        return {
            'device_id': device_id,
            'ok': False,
            'error': 'PG_IN_CSE_URL, PG_MN_CSE_ID, PG_IN_CSE_ORIGIN and PG_IN_CSE_RVI are required',
        }
    path = '/'.join(quote(part, safe='') for part in (MN_CSE_ID.strip('/'), device_id))
    url = f'{IN_CSE_URL}/~/{path}'
    headers = {
        'X-M2M-Origin': IN_CSE_ORIGIN,
        'X-M2M-RI': f'pinchguard-{device_id.lower()}-{int(time.time() * 1000)}',
        'X-M2M-RVI': IN_CSE_RVI,
        'Accept': 'application/json',
    }
    request = urllib.request.Request(url, headers=headers, method='GET')
    fetched_at = time.time()
    try:
        with urllib.request.urlopen(request, timeout=IN_CSE_TIMEOUT) as response:
            status = response.status
            raw = response.read(256_000)
        if status != 200:
            return {'device_id': device_id, 'ok': False, 'http_status': status, 'error': f'HTTP {status}'}
        try:
            body = json.loads(raw.decode('utf-8'))
            resource = _parse_onem2m_device(device_id, body)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            return {'device_id': device_id, 'ok': False, 'http_status': status, 'error': f'Invalid oneM2M response: {exc}'}
        source_time = resource.get('received_at') or resource.get('evaluated_at')
        age_sec = None
        fresh = False
        if isinstance(source_time, str):
            try:
                parsed = datetime.fromisoformat(source_time.replace('Z', '+00:00'))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                age_sec = max(0.0, fetched_at - parsed.timestamp())
                fresh = age_sec <= MN_CSE_FRESH_SECONDS
            except ValueError:
                pass
        return {
            'device_id': device_id,
            'ok': True,
            'http_status': status,
            'resource_type': resource.get('ty'),
            'content_definition': resource.get('cnd'),
            'data': resource,
            'source_timestamp': source_time,
            'data_age_sec': round(age_sec, 1) if age_sec is not None else None,
            'fresh': fresh,
            'fetched_at': utc_iso(fetched_at),
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, 'reason', exc)
        return {'device_id': device_id, 'ok': False, 'error': str(reason)[:240], 'fetched_at': utc_iso(fetched_at)}


def _poll_mn_cse_once():
    """Poll all remote devices once; failures are isolated per device."""
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=len(MN_DEVICE_IDS)) as pool:
        futures = {pool.submit(_fetch_onem2m_device, device_id): device_id for device_id in MN_DEVICE_IDS}
        for future in as_completed(futures):
            device_id = futures[future]
            try:
                results[device_id] = future.result()
            except Exception as exc:  # Keep one device failure from hiding the others.
                results[device_id] = {'device_id': device_id, 'ok': False, 'error': str(exc)[:240]}
    ordered = [results[d] for d in MN_DEVICE_IDS]
    success_count = sum(1 for item in ordered if item.get('ok'))
    return {
        'source': 'MN-CSE via IN-CSE',
        'configured': _in_cse_configured(),
        'cse_url': IN_CSE_URL or None,
        'remote_cse_id': MN_CSE_ID or None,
        'fetched_at': utc_iso(),
        'poll_interval_sec': MN_CSE_POLL_SECONDS,
        'success_count': success_count,
        'device_count': len(MN_DEVICE_IDS),
        'connected': success_count > 0,
        'devices': ordered,
        'fresh_threshold_sec': MN_CSE_FRESH_SECONDS,
        'note': 'fresh is based on the source received_at/evaluated_at timestamp, not the HTTP fetch time',
    }


_mn_cache_lock = threading.Lock()
_mn_cache: dict[str, Any] | None = None
_mn_stop = threading.Event()
_mn_worker: threading.Thread | None = None


def _mn_poll_loop():
    # Poll immediately, then every configured interval. No browser required.
    while not _mn_stop.is_set():
        try:
            result = _poll_mn_cse_once()
            with _mn_cache_lock:
                global _mn_cache
                _mn_cache = result
        except Exception as exc:
            with _mn_cache_lock:
                _mn_cache = {'source': 'MN-CSE via IN-CSE', 'configured': _in_cse_configured(),
                             'connected': False, 'error': str(exc)[:240],
                             'devices': [], 'success_count': 0, 'device_count': len(MN_DEVICE_IDS),
                             'poll_interval_sec': MN_CSE_POLL_SECONDS, 'fetched_at': utc_iso()}
        if _mn_stop.wait(MN_CSE_POLL_SECONDS):
            break


@app.on_event('startup')
def start_mn_polling():
    global _mn_worker
    if not _in_cse_configured():
        return
    if _mn_worker is not None and _mn_worker.is_alive():
        return
    _mn_stop.clear()
    _mn_worker = threading.Thread(target=_mn_poll_loop, name='mn-cse-poller', daemon=True)
    _mn_worker.start()


@app.on_event('shutdown')
def stop_mn_polling():
    _mn_stop.set()
    if _mn_worker is not None:
        _mn_worker.join(timeout=IN_CSE_TIMEOUT + 2)


@app.get('/api/onem2m/devices')
def onem2m_devices():
    """Return latest automatically polled snapshot; does not contact CSE on each request."""
    with _mn_cache_lock:
        snapshot = dict(_mn_cache) if _mn_cache is not None else None
    if snapshot is None:
        return {'source': 'MN-CSE via IN-CSE', 'configured': _in_cse_configured(), 'connected': False,
                'polling': bool(_in_cse_configured()),
                'status': 'waiting_for_first_poll' if _in_cse_configured() else 'not_configured',
                'devices': [], 'success_count': 0, 'device_count': len(MN_DEVICE_IDS),
                'poll_interval_sec': MN_CSE_POLL_SECONDS, 'fetched_at': None}
    # Age cached source readings against now; HTTP poll success != fresh sensor data.
    now = time.time()
    snapshot['devices'] = [dict(item) for item in snapshot.get('devices', [])]
    for device in snapshot['devices']:
        source_time = device.get('source_timestamp')
        if device.get('ok') and isinstance(source_time, str):
            try:
                stamp = datetime.fromisoformat(source_time.replace('Z', '+00:00'))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                age = max(0.0, now - stamp.timestamp())
                device['data_age_sec'] = round(age, 1)
                device['fresh'] = age <= MN_CSE_FRESH_SECONDS
            except ValueError:
                pass
    snapshot['polling'] = bool(_mn_worker and _mn_worker.is_alive())
    return snapshot


@app.post('/notify')
async def notify(request:Request):
    global one_m2m_last,one_m2m_verify_count
    # Set PG_NOTIFY_TOKEN to require a private, unguessable path token in X-PG-Notify-Token.
    token = os.getenv('PG_NOTIFY_TOKEN','')
    if token and not hmac.compare_digest(request.headers.get('x-pg-notify-token',''),token):
        raise HTTPException(401,'Invalid notification token')
    body=await request.body()
    if len(body)>MAX_EVENT_BODY:
        raise HTTPException(413,'Notification too large')
    try:
        obj=json.loads(body)
    except (ValueError,UnicodeDecodeError):
        raise HTTPException(400,'Invalid JSON')
    if not isinstance(obj,dict) or not isinstance(obj.get('m2m:sgn'),dict):
        raise HTTPException(400,'Expected m2m:sgn')
    sgn=obj['m2m:sgn']
    response_headers={'X-M2M-RSC':'2000'}
    if request.headers.get('X-M2M-RI'):
        response_headers['X-M2M-RI']=request.headers['X-M2M-RI']
    if sgn.get('vrq') is True:
        with lock:
            one_m2m_verify_count+=1
        return Response(status_code=200, content='{}', media_type='application/json', headers=response_headers)
    nev=sgn.get('nev') or {}
    if not isinstance(nev,dict):
        raise HTTPException(400,'Invalid notification event')
    rep=nev.get('rep') or {}
    if not isinstance(rep,dict):
        raise HTTPException(400,'Invalid representation')
    cin = rep.get('m2m:cin')
    if not isinstance(cin,dict):
        # Other resource event types need explicit handling, not a fabricated risk.
        store_event('ONEM2M', 'INFO', 'TinyIoT', '지원되지 않는 oneM2M 알림 유형', 'ONEM2M', obj)
    else:
        content=cin.get('con')
        if isinstance(content,str):
            try: value=json.loads(content)
            except ValueError: value={'raw_content':content}
        else: value=content
        if not isinstance(value,dict):value={'value':value}
        sur=str(sgn.get('sur',''))
        event_key=f'{sur}|{cin.get("ri", "")}' if cin.get('ri') else None
        if 'risk_level' in value:
            new_risk(value,source='ONEM2M',event_key=event_key)
        elif any(x in value for x in ('distance_cm','distance_m','person_present','presence','machine_running','beam_blocked','rpm')):
            # Repeated notifications can occur; resource identity is used for audit.
            new_sensor(value,source='ONEM2M')
        else:
            store_event('ONEM2M','INFO','TinyIoT','oneM2M 이벤트 수신','ONEM2M',value,event_key=event_key)
    with lock:
        one_m2m_last=time.time()
    return Response(status_code=200,content='{}',media_type='application/json',headers=response_headers)


@app.post('/api/demo')
def demo(data: DemoIn):
    if not DEMO_ALLOWED:
        raise HTTPException(403,'Demo disabled')
    samples={
       'SAFE':(165,False,0.0,False,False),
       'WARNING':(78,True,420.0,True,False),
       'HIGH':(31,True,610.0,True,True),
       'CRITICAL':(12,True,610.0,True,True),
       'UNKNOWN':(None,None,None,None,None)
    }
    dist,pres,rpm,running,blocked=samples[data.scenario]
    with lock:
        global view_mode
        view_mode='demo'
    sensor_payload={'device_id':'ESP32-SIM-01','distance_cm':dist,'presence':pres,'rpm':rpm,'machine_running':running,'beam_blocked':blocked,'source':'SYNTHETIC'}
    new_sensor(sensor_payload,demo=True,source='SYNTHETIC')
    risk_payload={'event_id':f'DEMO-{int(time.time()*1000)}','risk_level':data.scenario,'camera_id':'CAM-DEMO-01','description':{
       'SAFE':'데모: 위험구역 접근 없음','WARNING':'데모: 작업자 위험구역 접근',
       'HIGH':'데모: 광전 센서 차단 및 설비 가동',
       'CRITICAL':'데모: 설비 가동 + 경계 차단 + 20cm 이내 접근 (모의)',
       'UNKNOWN':'데모: 센서 또는 영상 입력 신뢰 불가'
    }[data.scenario]}
    new_risk(risk_payload,demo=True,source='SYNTHETIC_RULES')
    return {'accepted':True,'mode':'demo','risk_level':data.scenario}


@app.post('/api/mode')
def mode(data: ModeIn):
    global view_mode
    if data.mode=='demo' and not DEMO_ALLOWED:
        raise HTTPException(403,'Demo disabled')
    with lock:
        view_mode=data.mode
    return {'mode':view_mode}


@app.post('/api/events/{event_id}/ack')
def acknowledge(event_id:int):
    # UI acknowledgement is not physical machine stop or alarm clearing.
    with conn() as c:
        row = c.execute('SELECT id FROM events WHERE id=?',(event_id,)).fetchone()
        if not row:
            raise HTTPException(404,'Event not found')
        c.execute('UPDATE events SET ack_at=COALESCE(ack_at,?) WHERE id=?',(utc_iso(),event_id))
    return {'acknowledged':True,'note':'only event acknowledgement; risk level unchanged'}


if DEMO_ALLOWED and os.getenv('PG_DEMO_SEED','1') == '1':
    with conn() as c:
        n=c.execute('SELECT COUNT(*) FROM events WHERE is_demo=1').fetchone()[0]
    if not n:
        # Explicitly simulated historical observations for visual testing.
        base=time.time()-360
        for i in range(22):
            level='CRITICAL' if i in (10,) else 'HIGH' if i in (9,16) else 'WARNING' if i in (6,7,8,15,17) else 'SAFE'
            cm=round([145,141,130,119,106,93,75,61,48,30,12,78,103,133,148,71,28,56,92,130,150,168][i],2)
            dp={'device_id':'ESP32-SIM-01','distance_cm':cm,'presence':i>3,'machine_running':True,'rpm':520,'beam_blocked':i in (9,10,16),'received_at':base+i*15,'demo':True,'source':'SYNTHETIC'}
            store_event('SENSOR','INFO','ESP32-SIM-01','데모 센서값','SYNTHETIC',dp,demo=True,received_at=base+i*15)
            if level!='SAFE':
                store_event('RISK',level,'CAM-DEMO-01',f'데모 위험 알림: {level}','SYNTHETIC_RULES',
                            {'event_id':f'demo-seed-{i}','risk_level':level,'demo':True},demo=True,received_at=base+i*15)
        new_sensor({'device_id':'ESP32-SIM-01','distance_cm':93,'presence':True,'machine_running':True,'rpm':520,'beam_blocked':False},demo=True,source='SYNTHETIC')
        new_risk({'risk_level':'WARNING','event_id':'demo-bootstrap','description':'데모: 위험구역 접근 감지','camera_id':'CAM-DEMO-01'},demo=True,source='SYNTHETIC_RULES')
