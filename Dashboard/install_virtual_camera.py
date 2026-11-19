#!/usr/bin/env python3
"""PinchGuard sensor-driven schematic scene installer.

Run in the PinchGuard_Dashboard_CRITICAL project folder with the project's Python.
Edits only static/index.html, static/app.js and static/styles.css.
Originals are backed up, and repeated runs are a no-op.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import sys

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'static'
HTML = STATIC / 'index.html'
JS = STATIC / 'app.js'
CSS = STATIC / 'styles.css'
MARK = 'PINCHGUARD_SENSOR_SCENE_V1'

SCENE_HTML = '''<!-- PINCHGUARD_SENSOR_SCENE_V1: 데이터 기반 모식도, 실제 영상 아님 -->
<div id="pg-scene-overlay" class="pg-scene-overlay" hidden aria-label="센서 데이터 기반 가상 현장 시각화 (실제 카메라 영상 아님)">
  <div id="pg-scene-zone" class="pg-scene-zone"><span>DANGER ZONE · SCHEMATIC</span></div>
  <div id="pg-scene-belt" class="pg-scene-belt"></div>
  <div id="pg-scene-people" class="pg-scene-people" aria-hidden="true"></div>
  <div class="pg-scene-hud" aria-live="off">
    <span id="pg-zone-count">ZONE —</span>
    <span id="pg-total-count">PEOPLE —</span>
    <span id="pg-motor-state">MOTOR —</span>
    <span id="pg-scene-distance">DIST —</span>
  </div>
  <div class="pg-scene-disclaimer">시각화 전용 · 인물 위치는 실제 추적값 아님</div>
</div>
'''

SCENE_JS = r'''
// PINCHGUARD_SENSOR_SCENE_V1
function renderPgScene(data, enabled){
  const overlay=$('pg-scene-overlay');
  if(!overlay)return;
  overlay.hidden=!enabled;
  const stage=$('camera-stage');
  stage.classList.toggle('pg-virtual',enabled);
  if(!enabled)return;

  const s=data.sensor.latest || {};
  const risk=data.risk.fresh ? data.risk.level : 'UNKNOWN';
  overlay.dataset.risk=String(risk);
  const known=n=>typeof n==='number' && Number.isFinite(n) && n>=0;
  const total=known(s.total_person_count)?Math.floor(s.total_person_count):null;
  const rawZone=known(s.zone_person_count)?Math.floor(s.zone_person_count):null;
  const zone=rawZone===null?null:(total===null?rawZone:Math.min(rawZone,total));
  const spinning=typeof s.machine_running==='boolean'?s.machine_running:null;
  $('pg-zone-count').textContent='ZONE '+(zone===null?'—':zone+'명');
  $('pg-total-count').textContent='TOTAL '+(total===null?'—':total+'명');
  $('pg-motor-state').textContent='MOTOR '+(spinning===null?'—':spinning?'RUNNING':'STOPPED');
  $('pg-scene-distance').textContent='DIST '+(known(s.distance_cm)?Number(s.distance_cm).toFixed(1)+'cm':'—');
  $('pg-scene-belt').classList.toggle('moving',spinning===true);
  const label=overlay.parentElement.querySelector('.demo-camera-label');
  if(label)label.textContent='SENSOR SCENE  ·  실제 카메라 영상 아님';

  // 아이콘의 위치는 보기 위한 임의의 도식 배치이며, 실제 좌표를 뜻하지 않음.
  const inZone=[[46,38],[53,52],[60,38],[47,67],[59,63],[54,33],[65,55],[42,56]];
  const outZone=[[13,41],[19,68],[82,67],[84,40],[32,72],[11,73],[76,29],[30,31]];
  const people=$('pg-scene-people');
  people.replaceChildren();
  const displayZone=zone===null?0:Math.min(8,zone);
  const displayTotal=total===null?displayZone:Math.min(8,Math.max(total,displayZone));
  for(let i=0;i<displayTotal;i++){
    const hazard=i<displayZone;
    const p=(hazard?inZone[i % inZone.length]:outZone[(i-displayZone)%outZone.length]);
    const person=document.createElement('div');
    person.className='pg-person'+(hazard?' in-zone':'');
    person.style.left=p[0]+'%';person.style.top=p[1]+'%';
    person.style.animationDelay=(i*.19)+'s';
    person.title=hazard?'위험구역 인원 (위치는 도식)':'현장 인원 (위치는 도식)';
    people.append(person);
  }
  if(total!==null && total>displayTotal){
    const more=document.createElement('span');more.className='pg-more-persons';
    more.textContent='+'+(total-displayTotal)+'명';people.append(more);
  }
}

function renderCamera(data){
  const demo=data.mode==='demo';
  const online=data.camera.online && !demo;
  const virtual=!demo && !online && Boolean(data.sensor.fresh);
  const frame=data.camera.latest;
  $('camera-placeholder').hidden=!(demo||virtual);
  $('camera-image').hidden=!online;
  renderPgScene(data,virtual);
  $('video-status').className='pill '+((online||virtual)?'live':'offline');
  $('video-status').textContent=online?(frame?.simulation?'● 시뮬레이션 영상':'● 실제 영상 수신'):
    virtual?'● 가상 현장 · 센서 기반':demo?'● 데모 시각화':'● 데이터 대기';
  $('camera-meta').textContent=online?`FRAME ${cap(frame.frame_id,12)} / ${data.camera.fps} FPS`:
    virtual?'SENSOR-DRIVEN SCENE · NOT VIDEO':demo?'DEMO SCENE':'SCENE OFFLINE';
  $('camera-utc').textContent=online?`FRAME ${cap(frame.frame_id,15)} · ${fmtTime(frame.received_at)} KST`:
    virtual?'LIVE SENSOR DATA · SYNTHETIC DISPLAY':demo?'SYNTHETIC SCENE · NOT A REAL CAMERA':'SENSOR DATA UNAVAILABLE';
  if(online && frame.received_at!==lastCameraFrame){
    lastCameraFrame=frame.received_at;
    $('camera-image').src='/api/frame/latest?ts='+encodeURIComponent(frame.received_at);
  }
}
'''

STYLE = r'''
/* PINCHGUARD_SENSOR_SCENE_V1 — purely schematic visualization (not camera footage) */
.pg-scene-overlay[hidden]{display:none!important}
.pg-scene-overlay{position:absolute;inset:0;pointer-events:none;z-index:2;overflow:hidden}
#camera-stage.pg-virtual .plant-svg g[transform="translate(425 65)"]{display:none}
#camera-stage.pg-virtual .plant-svg{opacity:.95}
.pg-scene-zone{position:absolute;left:40%;top:26%;width:28%;height:47%;border:2px dashed rgba(249,187,94,.85);border-radius:9px;background:rgba(226,147,37,.055);box-shadow:0 0 35px #e6a34d10;transition:background .3s,border-color .3s}
.pg-scene-zone>span{position:absolute;right:5px;top:5px;font-size:clamp(7px,.73vw,10px);letter-spacing:.055em;color:#ffc77c;font-weight:800;text-shadow:0 1px 4px #0c1629}
.pg-scene-overlay[data-risk="HIGH"] .pg-scene-zone,.pg-scene-overlay[data-risk="CRITICAL"] .pg-scene-zone{border-color:#ff6e88;background:rgba(249,60,94,.12);box-shadow:0 0 30px #fd4b6129;animation:pg-zone-flash 1.2s ease-in-out infinite alternate}
.pg-scene-overlay[data-risk="SAFE"] .pg-scene-zone{border-color:#72c9bc;background:rgba(41,194,174,.045)}
.pg-scene-belt{position:absolute;left:26%;top:55%;width:47%;height:3%;border:2px solid #7aa3b6;border-radius:5px;background:repeating-linear-gradient(90deg,#54bdd0 0 12px,#19384e 12px 27px);box-shadow:0 0 16px #2bacbb4a;opacity:.75}
.pg-scene-belt.moving{animation:pg-conveyor .65s linear infinite}
.pg-scene-people{position:absolute;inset:0}
.pg-person{position:absolute;width:22px;height:37px;transform:translate(-50%,-50%);filter:drop-shadow(0 1px 4px #020a16);animation:pg-worker-bob 2.4s ease-in-out infinite alternate}
.pg-person::before{content:'';position:absolute;top:1px;left:6px;width:11px;height:11px;border-radius:50%;background:#60def2;border:2px solid #112d42}
.pg-person::after{content:'';position:absolute;top:13px;left:4px;width:15px;height:22px;border-radius:6px 6px 4px 4px;background:linear-gradient(135deg,#67dbe8,#267b98);border:2px solid #9af1f0;box-shadow:inset 0 -3px 0 #22445b}
.pg-person.in-zone::before{background:#f8b85a;border-color:#513525}
.pg-person.in-zone::after{background:linear-gradient(135deg,#ffc76d,#c06d39);border-color:#ffdb94}
.pg-more-persons{position:absolute;bottom:23%;right:4%;background:#192f43e0;border:1px solid #426c83;color:#daebf5;font-size:10px;font-weight:800;padding:5px 8px;border-radius:6px}
.pg-scene-hud{position:absolute;right:14px;top:48px;display:grid;grid-template-columns:repeat(2,max-content);justify-content:end;gap:5px;z-index:3}
.pg-scene-hud span{font-size:clamp(8px,.73vw,10px);font-weight:800;letter-spacing:.04em;color:#c6e7e7;border:1px solid #3b7589;background:#0b2236e8;border-radius:5px;padding:5px 7px;white-space:nowrap}
.pg-scene-disclaimer{position:absolute;left:17px;bottom:48px;font-size:clamp(8px,.7vw,10px);font-weight:700;color:#a8c4d0;text-shadow:0 1px 5px #091626;background:#102333a3;border-radius:4px;padding:4px 6px}
#camera-stage.pg-virtual .demo-camera-label{z-index:3;border-color:#379a90;color:#8ef5e0;background:#102c32e8}
@keyframes pg-conveyor{from{background-position:0 0}to{background-position:27px 0}}
@keyframes pg-worker-bob{from{transform:translate(-50%,-50%) translateY(0)}to{transform:translate(-50%,-50%) translateY(-3px)}}
@keyframes pg-zone-flash{from{opacity:.72}to{opacity:1}}
@media(max-width:760px){.pg-scene-hud{top:43px;right:8px}.pg-scene-hud span{font-size:8px;padding:3px 5px}.pg-person{transform:translate(-50%,-50%) scale(.8)}.pg-scene-disclaimer{font-size:8px;bottom:38px;left:8px}}
@media(prefers-reduced-motion:reduce){.pg-scene-belt.moving,.pg-person,.pg-scene-overlay .pg-scene-zone{animation:none!important}}
'''


def apply():
    for p in (HTML, JS, CSS):
        if not p.exists():
            print(f'[ERROR] 파일 없음: {p}')
            sys.exit(1)
    html = HTML.read_text(encoding='utf-8')
    js = JS.read_text(encoding='utf-8')
    css = CSS.read_text(encoding='utf-8')
    if MARK in html and MARK in js and MARK in css:
        print('[OK] 이미 설치되어 있습니다. 아무것도 변경하지 않았습니다.')
        return
    if MARK in html or MARK in js or MARK in css:
        print('[ERROR] 일부만 설치된 상태입니다. 안전을 위해 중단합니다.')
        sys.exit(1)

    needle = '<div class="camera-crosshair top-left">'
    if html.count(needle)!=1:
        print('[ERROR] 카메라 HTML 구조가 예상과 달라 중단합니다.')
        sys.exit(1)
    html = html.replace(needle, SCENE_HTML + needle,1)
    html = html.replace('VIDEO SURVEILLANCE','SENSOR SCENE / CAMERA',1)
    html = html.replace('현장 카메라 <span>CAM-01</span>','현장 시각화 <span>VIRTUAL-01</span>',1)
    html = html.replace('카메라 입력 상태','현장 시각화 상태',1)
    html = html.replace('실제 영상 수신 대기','센서 기반 가상 화면 대기',1)
    html = html.replace('· 영상 AI 박스 표시는 미구현','· 센서값 기반 도식 · 실제 영상 아님',1)

    anchor_start = 'function renderCamera(data){'
    anchor_end = '\nfunction renderDecision(data){'
    start = js.find(anchor_start)
    end = js.find(anchor_end,start)
    if start<0 or end<0 or js.count(anchor_start)!=1:
        print('[ERROR] app.js의 renderCamera 함수 구조가 예상과 달라 중단합니다.')
        sys.exit(1)
    js = js[:start] + SCENE_JS.strip() + '\n' + js[end:]

    old = "$('camera-main').textContent=c.online?'연결됨':'미연결';"
    new = "$('camera-main').textContent=c.online?'연결됨':(!demo&&data.sensor.fresh)?'가상 현장':'대기 중';"
    old2 = "$('camera-main').className='metric-big '+(c.online?'safe':'unknown');"
    new2 = "$('camera-main').className='metric-big '+((c.online||(!demo&&data.sensor.fresh))?'safe':'unknown');"
    old3 = "$('camera-sub').textContent=c.online?`HTTP JPEG · ${c.fps} FPS (최근 3초)`:'영상 수신 없음';"
    new3 = "$('camera-sub').textContent=c.online?`HTTP JPEG · ${c.fps} FPS (최근 3초)`:( !demo&&data.sensor.fresh ? '센서값으로 생성한 가상 현장 · 실제 영상 아님' : '센서 데이터 대기');"
    for before, after in ((old,new),(old2,new2),(old3,new3)):
        if js.count(before)!=1:
            print('[ERROR] app.js의 카메라 상태 표시 코드가 예상과 달라 중단합니다.')
            sys.exit(1)
        js = js.replace(before,after,1)

    old4="$('conn-camera').textContent=video?'수신 중':'미연결';$('conn-camera').className='conn-state '+(video?'ok':'');"
    new4="$('conn-camera').textContent=video?'영상 수신 중':(data.mode==='live'&&sensor)?'센서 시각화 (영상 없음)':'미연결';$('conn-camera').className='conn-state '+(video?'ok':'');"
    if js.count(old4)!=1:
        print('[ERROR] app.js의 연결 표시 코드가 예상과 달라 중단합니다.')
        sys.exit(1)
    js=js.replace(old4,new4,1)
    css += '\n' + STYLE

    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    for path, value in ((HTML,html),(JS,js),(CSS,css)):
        backup=path.with_name(path.name + f'.before_virtual_scene_{stamp}.bak')
        backup.write_bytes(path.read_bytes())
        path.write_text(value,encoding='utf-8')
        print(f'[OK] 수정: {path.relative_to(ROOT)} (백업: {backup.name})')
    print('\n완료! 서버 재시작 없이 브라우저에서 Ctrl+Shift+R 새로고침해 주세요.')
    print('LIVE 모드 + 센서 최신 데이터가 있을 때만 가상 현장 화면이 나타납니다.')
    print('실제 카메라 영상처럼 보이더라도 센서 수치의 모식도이며 실측 위치 영상이 아닙니다.')


if __name__=='__main__':
    apply()
