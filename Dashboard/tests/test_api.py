"""Actual HTTP-level route tests with simulated CSE / camera inputs.
Tests do not operate industrial safety equipment or connect to a real CSE.
"""
import os
import sys
import tempfile
from pathlib import Path
from io import BytesIO

DB_FILE = tempfile.NamedTemporaryFile(suffix='.sqlite3',delete=False)
DB_FILE.close()
os.environ['PG_DB_PATH']=DB_FILE.name
os.environ['PG_ENABLE_DEMO']='1'
os.environ['PG_DEMO_SEED']='1'
os.environ['PG_INGEST_KEY']='local-dev-change-me'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from PIL import Image
from app import app
client=TestClient(app)
KEY={'X-API-Key':'local-dev-change-me'}


def test_root():
    r=client.get('/')
    assert r.status_code==200 and 'PINCH' in r.text
    assert client.get('/static/app.js').status_code==200


def test_demo_and_live_modes():
    r=client.get('/api/state'); assert r.status_code==200
    assert r.json()['mode']=='demo'
    assert r.json()['stats']['risk_events']>0
    r=client.post('/api/demo',json={'scenario':'HIGH'})
    assert r.status_code==200
    assert client.get('/api/state').json()['risk']['level']=='HIGH'
    r=client.post('/api/mode',json={'mode':'live'})
    assert r.status_code==200
    state=client.get('/api/state').json()
    assert state['mode']=='live' and state['risk']['level']=='UNKNOWN'


def test_api_sensor_risk_and_ack():
    assert client.post('/api/sensor',json={'device_id':'S1','presence':True}).status_code==401
    r=client.post('/api/sensor',headers=KEY,json={'device_id':'S1','presence':True,'distance_cm':32.5,'rpm':300,'machine_running':True,'beam_blocked':True})
    assert r.status_code==200
    r=client.post('/api/risk',headers=KEY,json={'event_id':'risk-5','risk_level':'WARNING','description':'사람 접근'})
    assert r.status_code==200
    state=client.get('/api/state').json()
    assert state['risk']['level']=='WARNING'
    assert state['sensor']['latest']['distance_cm']==32.5
    id_=next(e['id'] for e in state['events'] if e['category']=='RISK')
    res=client.post(f'/api/events/{id_}/ack')
    assert res.status_code==200
    assert client.get('/api/state').json()['risk']['level']=='WARNING'
    assert any(e['ack_at'] for e in client.get('/api/state').json()['events'] if e['id']==id_)
    assert client.post('/api/sensor',headers=KEY,json={'device_id':'S1','distance_cm':-4}).status_code==422


def test_notification_verification_and_cin():
    r=client.post('/notify',headers={'X-M2M-RI':'abc-123'},json={'m2m:sgn':{'vrq':True}})
    assert r.status_code==200 and r.headers['x-m2m-rsc']=='2000' and r.headers['x-m2m-ri']=='abc-123'
    assert client.get('/api/state').json()['one_m2m']['verification_count']>=1
    payload={'event_id':'m2m-risk','risk_level':'HIGH','description':'알림 위험'}
    body={'m2m:sgn':{'sur':'/TinyIoT/PinchGuardAE/risk-events/risk-sub',
              'nev':{'rep':{'m2m:cin':{'ri':'cin-test-xyz','con':__import__('json').dumps(payload)}}}}}
    r=client.post('/notify',json=body)
    assert r.status_code==200 and r.headers['x-m2m-rsc']=='2000'
    assert client.get('/api/state').json()['risk']['level']=='HIGH'
    assert client.get('/api/state').json()['one_m2m']['last_notification']
    # Repeat should not create a duplicate persisted risk entry.
    before=client.get('/api/state').json()['stats']['risk_events']
    assert client.post('/notify',json=body).status_code==200
    after=client.get('/api/state').json()['stats']['risk_events']
    assert after==before
    sen={'m2m:sgn':{'nev':{'rep':{'m2m:cin':{'con':'{"device_id":"ESP-1","distance_m":0.4,"machine_running":true}'}}}}}
    assert client.post('/notify',json=sen).status_code==200
    assert client.get('/api/state').json()['sensor']['latest']['distance_cm']==40


def test_frame_receiver():
    image=Image.new('RGB',(320,240),(20,40,60))
    buf=BytesIO();image.save(buf,format='JPEG');raw=buf.getvalue()
    assert client.post('/api/frame',content=raw,headers={'content-type':'image/jpeg'}).status_code==401
    r=client.post('/api/frame',content=raw,headers={**KEY,'Content-Type':'image/jpeg','X-Camera-ID':'cam-01','X-Frame-ID':'33'})
    assert r.status_code==200 and r.json()['accepted']
    x=client.get('/api/state').json()
    assert x['camera']['online'] and x['camera']['latest']['width']==320
    assert client.get('/api/frame/latest').content==raw
    assert client.post('/api/frame',content=b'\xff\xd8foo\xff\xd9',headers={**KEY,'Content-Type':'image/jpeg'}).status_code==400


def test_critical_demo_and_live():
    r=client.post('/api/demo',json={'scenario':'CRITICAL'})
    assert r.status_code==200 and r.json()['risk_level']=='CRITICAL'
    assert client.get('/api/state').json()['risk']['level']=='CRITICAL'
    assert client.get('/api/state').json()['stats']['critical_events']>=1
    assert client.post('/api/mode',json={'mode':'live'}).status_code==200
    r=client.post('/api/risk',headers=KEY,json={'event_id':'critical-test','risk_level':'CRITICAL','simulation':True})
    assert r.status_code==200 and r.json()['level']=='CRITICAL'
    state=client.get('/api/state').json()
    assert state['risk']['level']=='CRITICAL'
    assert state['stats']['critical_events']>=1

def test_critical_onem2m_notification():
    body={'m2m:sgn':{'sur':'/TinyIoT/PinchGuardAE/risk-events/risk-sub',
          'nev':{'rep':{'m2m:cin':{'ri':'cin-critical-unique','con':'{"risk_level":"CRITICAL","event_id":"critical-m2m"}'}}}}}
    assert client.post('/notify',json=body).status_code==200
    assert client.get('/api/state').json()['risk']['level']=='CRITICAL'


def test_mn_cse_devices_endpoint(monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, 'IN_CSE_URL', 'http://in-cse.test:3001')
    monkeypatch.setattr(app_module, 'MN_CSE_ID', 'tinyiot')
    monkeypatch.setattr(
        app_module,
        'MN_DEVICE_RIS',
        {f'Device{i}': f'device-{i}-ri' for i in range(1, 7)},
    )
    monkeypatch.setattr(app_module, 'IN_CSE_ORIGIN', 'dashboard-test')
    monkeypatch.setattr(app_module, 'IN_CSE_RVI', '3')
    def fake_fetch(device_id):
        return {
            'device_id': device_id,
            'ok': True,
            'http_status': 200,
            'data': {'rn': device_id, 'ty': 28, 'distance_cm': 88.8},
            'source_timestamp': '2026-11-17T05:00:00+00:00',
            'data_age_sec': 1.0,
            'fresh': True,
        }
    monkeypatch.setattr(app_module, '_fetch_onem2m_device', fake_fetch)
    monkeypatch.setattr(app_module, '_mn_cache', app_module._poll_mn_cse_once())
    response = client.get('/api/onem2m/devices')
    assert response.status_code == 200
    body = response.json()
    assert body['connected'] is True
    assert body['success_count'] == 6
    assert [item['device_id'] for item in body['devices']] == [f'Device{i}' for i in range(1, 7)]
    assert body['devices'][4]['data']['distance_cm'] == 88.8


def test_mn_cse_device_uses_in_cse_sp_relative_route(monkeypatch):
    import json
    import app as app_module

    monkeypatch.setattr(app_module, 'IN_CSE_URL', 'http://in-cse.test:3001')
    monkeypatch.setattr(app_module, 'MN_CSE_ID', '/tinyiot/')
    monkeypatch.setattr(
        app_module,
        'MN_DEVICE_RIS',
        {f'Device{i}': f'device-{i}-ri' for i in range(1, 7)},
    )
    monkeypatch.setattr(app_module, 'IN_CSE_ORIGIN', 'dashboard-test')
    monkeypatch.setattr(app_module, 'IN_CSE_RVI', '3')
    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit):
            return json.dumps({'eg:Device1': {'rn': 'Device1', 'ty': 28}}).encode()

    def fake_urlopen(request, timeout):
        captured['url'] = request.full_url
        captured['headers'] = request.headers
        captured['timeout'] = timeout
        return FakeResponse()

    monkeypatch.setattr(app_module.urllib.request, 'urlopen', fake_urlopen)
    result = app_module._fetch_onem2m_device('Device1')

    assert result['ok'] is True
    assert captured['url'] == 'http://in-cse.test:3001/~/tinyiot/device-1-ri'
    assert captured['headers']['X-m2m-origin'] == 'dashboard-test'


def test_mn_cse_device_unwrap():
    import app as app_module
    resource = app_module._parse_onem2m_device('Device5', {
        'eg:Device5': {'rn': 'Device5', 'ty': 28, 'distance_cm': 88.8}
    })
    assert resource['distance_cm'] == 88.8
    try:
        app_module._parse_onem2m_device('Device5', {'eg:Device4': {'rn': 'Device4'}})
    except ValueError:
        pass
    else:
        raise AssertionError('mismatched resource must be rejected')
