#!/usr/bin/env python3
"""Simulated sender -> dashboard API. Never transmits to a real machine."""
import argparse
import json
from urllib.request import Request,urlopen

p=argparse.ArgumentParser()
p.add_argument('--base',default='http://127.0.0.1:8000')
p.add_argument('--key',default='local-dev-change-me')
a=p.parse_args()

def post(path,obj):
    req=Request(a.base+path, data=json.dumps(obj).encode(),method='POST',headers={
        'Content-Type':'application/json','X-API-Key':a.key})
    with urlopen(req,timeout=5) as r:
        print(path,r.status,r.read().decode('utf-8'))

post('/api/sensor',{'device_id':'ESP32-01','sequence':15,'distance_cm':32.5,'presence':True,'beam_blocked':True,'rpm':560,'machine_running':True})
post('/api/risk',{'event_id':'test-risk-15','risk_level':'HIGH','camera_id':'CAM-01',
                  'description':'시뮬레이션 입력: 끼임 위험구역 침입'})
print('완료: 브라우저에서 LIVE 모드로 전환하세요.')
