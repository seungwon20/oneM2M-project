'use strict';

const $ = id => document.getElementById(id);
const LEVEL_NAMES = {SAFE:'SAFE',WARNING:'WARNING',HIGH:'HIGH',CRITICAL:'CRITICAL',UNKNOWN:'UNKNOWN'};
const LEVEL_KO = {SAFE:'SAFE',WARNING:'WARNING',HIGH:'HIGH',CRITICAL:'CRITICAL',UNKNOWN:'UNKNOWN'};
const fmtTime = ts => {
  if(!ts) return '—';
  const d = new Date(typeof ts === 'number' ? ts*1000 : ts);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleTimeString('en-GB',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit',timeZone:'Asia/Seoul'});
};
const cap = (s,n=26) => String(s??'—').slice(0,n);
// PINCHGUARD_UI_LABELS_V1: presentation-only aliases (original source stays in API/SQLite).
function pgDisplaySource(value){
  const source = String(value ?? '');
  if(source === 'MN-CSE Device6') return 'MEC 위험도 분석';
  if(source === 'MN-CSE Device5') return '현장 거리 센서';
  return source;
}
function pgDisplayDescription(value){
  const description = String(value ?? '');
  if(description.includes('MEC에서 수신해 MN-CSE에 저장한 위험도'))
    return 'MEC에서 전달된 최신 위험도 평가 결과';
  if(description.startsWith('MEC 위험도 평가 수신:'))
    return description.replace('MEC 위험도 평가 수신:', '위험도 평가 결과 수신 ·');
  if(description.startsWith('MN-CSE Device5 거리 측정값 수신'))
    return '접근 거리 측정값 수신';
  return description;
}



// PINCHGUARD_ENGLISH_UI_V1
function pgEnglishText(value, kind='description', severity='') {
  const input=String(value ?? '');
  if (!/[가-힣]/.test(input)) {
    if(input==='MN-CSE Device6') return 'MEC Risk Analysis';
    if(input==='MN-CSE Device5') return 'Field Distance Sensor';
    return input;
  }
  const dictionary={
    'MEC 위험도 분석':'MEC Risk Analysis',
    '현장 거리 센서':'Field Distance Sensor',
    'MEC에서 전달된 최신 위험도 평가 결과':'Latest risk assessment received from MEC',
    'MEC에서 수신해 MN-CSE에 저장한 위험도':'Risk assessment received from MEC and stored in oneM2M',
    '접근 거리 측정값 수신':'Proximity distance reading received',
    'MN-CSE Device5 거리 측정값 수신':'Proximity distance reading received',
    '센서 값 수신':'Sensor reading received',
    '데모 센서값':'Demo sensor reading',
    '위험구역 접근 감지':'Approach to hazard zone detected',
    '위험 신호 없음':'No risk detected',
    '끼임 위험 이벤트':'Pinch-point hazard detected',
    '매우 높은 끼임 위험 경고':'Critical pinch-point hazard warning',
    '분석 결과 불명확':'Assessment inconclusive',
    '지원되지 않는 oneM2M 알림 유형':'Unsupported oneM2M notification type',
    'oneM2M 이벤트 수신':'oneM2M event received',
    '데모: 위험구역 접근 없음':'Demo: No approach to hazard zone',
    '데모: 작업자 위험구역 접근':'Demo: Worker approaching hazard zone',
    '데모: 광전 센서 차단 및 설비 가동':'Demo: Photoelectric barrier blocked while machine is running',
    '데모: 설비 가동 + 경계 차단 + 20cm 이내 접근 (모의)':'Demo: Machine running, barrier blocked, and distance under 20 cm (simulated)',
    '데모: 센서 또는 영상 입력 신뢰 불가':'Demo: Unreliable sensor or video input',
    '데모: 위험구역 접근 감지':'Demo: Approach to hazard zone detected',
  };
  if(Object.prototype.hasOwnProperty.call(dictionary,input))return dictionary[input];
  let m=input.match(/^(?:MEC 위험도 평가 수신:|위험도 평가 결과 수신 ·)\s*(SAFE|WARNING|HIGH|CRITICAL|UNKNOWN)$/i);
  if(m)return 'Risk assessment received: '+m[1].toUpperCase();
  m=input.match(/^데모 위험 알림:\s*(SAFE|WARNING|HIGH|CRITICAL|UNKNOWN)$/i);
  if(m)return 'Demo risk alert: '+m[1].toUpperCase();
  m=input.match(/^CSE 위험도\s*(\S+)$/);
  if(m)return 'Risk level received: '+m[1];
  if(kind==='source')return 'External Data Source';
  if(kind==='error')return 'Request failed. Check the server log.';
  if(kind==='risk'||kind==='event')return 'Risk assessment update received'+(severity?' · '+severity:'');
  return 'Event received (original details available in API)';
}

let lastState = null;
let pending = false;
let lastCameraFrame = null;
let loadErrorShown = false;

async function api(path, method='GET', body){
  const res = await fetch(path, {method, headers: body ? {'Content-Type':'application/json'} : {}, body:body ? JSON.stringify(body) : undefined,cache:'no-store'});
  let data;
  try{data=await res.json()}catch(_){throw new Error(`HTTP ${res.status}`)}
  if(!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}
function showToast(text,failed=false){
  const toast=document.createElement('div');toast.className='toast';toast.textContent=text;
  if(failed)toast.style.borderColor='#b55965';
  document.body.appendChild(toast);setTimeout(()=>toast.remove(),3400);
}

function renderState(data){
  lastState=data;
  const demo=data.mode==='demo';
  const simulated=!demo && Boolean(data.camera.latest?.simulation || data.sensor.latest?.simulation || data.risk.last_result?.simulation);
  $('demo-banner').hidden=!(demo || simulated);
  const bannerNote=$('demo-banner').querySelector('span');
  if(bannerNote)bannerNote.textContent=simulated?'Incoming video, sensor and risk events are simulated. They do not demonstrate validated AI inference or actual equipment safety.':'Displayed values are simulated. They do not represent real equipment protection.';
  $('mode-indicator').innerHTML='';
  const dot=document.createElement('span');dot.className='status-dot';$('mode-indicator').append(dot,document.createTextNode(demo?' Demo Data':simulated?' Simulated API input':' Live Data'));
  $('mode-indicator').style.borderColor=(demo||simulated)?'#594735':'#275b59';
  $('mode-indicator').style.color=(demo||simulated)?'#ffd396':'#79dfd1';
  $('btn-mode').lastChild.textContent=demo?' Switch to Live Data':' View Demo';
  const level=data.risk.level;
  const el=$('risk-main');el.textContent=LEVEL_NAMES[level]||'UNKNOWN';el.className='metric-big '+level.toLowerCase();
  $('risk-sub').textContent=data.risk.fresh?`Latest assessment received ${data.risk.age_sec} sec ago · ${(demo||simulated)?'SIMULATION':'LIVE'}`:'No assessment / Data expired';
  const s=data.sensor;
  $('sensor-main').replaceChildren();
  if(s.age_sec!==null){$('sensor-main').append(document.createTextNode(s.age_sec.toFixed(1)+' '));const u=document.createElement('small');u.textContent='sec';$('sensor-main').append(u)}
  else{$('sensor-main').textContent='No data'}
  $('sensor-sub').textContent=s.fresh?'Latest reading · Valid':'No data or stale readings';
  const c=data.camera;
  $('camera-main').textContent=c.online?'Connected':(!demo&&data.sensor.fresh)?'Virtual Scene':'Standby';
  $('camera-main').className='metric-big '+((c.online||(!demo&&data.sensor.fresh))?'safe':'unknown');
  $('camera-sub').textContent=c.online?`HTTP JPEG · ${c.fps} FPS (last 3 sec)`:( !demo&&data.sensor.fresh ? 'Sensor-driven schematic scene · Not actual camera footage' : 'Waiting for sensor data');
  $('events-main').replaceChildren(document.createTextNode(String(data.stats.risk_events)+' '));const cnt=document.createElement('small');cnt.textContent=' events';$('events-main').append(cnt);
  $('events-sub').textContent=`CRITICAL ${data.stats.critical_events||0} events · HIGH ${data.stats.high_events} events included · ${(demo||simulated)?'SIMULATED':'LIVE'} records`;
  renderSensors(data);
  renderCamera(data);
  renderDecision(data);
  renderConnections(data);
  renderEvents(data);
  drawChart(data.history);
  $('footer-sync').textContent='Last sync '+fmtTime(data.server_time)+' KST';
}
function renderSensors(data){
  const s=data.sensor.latest || {};
  const valid=data.sensor.fresh;
  const val=(v,unit='')=>valid&&v!==null&&v!==undefined?String(v)+unit:'—';
  $('distance').textContent=val(s.distance_cm);
  $('rpm').textContent=val(s.rpm);
  $('distance-desc').textContent=valid && typeof s.distance_cm==='number'?'Latest distance reading (cm)':'Waiting for sensor data';
  $('beam').textContent=valid && typeof s.beam_blocked==='boolean'?(s.beam_blocked?'BLOCKED':'CLEAR'):'—';
  $('beam').style.color=valid&&s.beam_blocked?'#fb8e96':'';
  $('machine').textContent=valid && typeof s.machine_running==='boolean'?(s.machine_running?'RUNNING':'STOPPED'):'—';
  $('machine').style.color=valid&&s.machine_running?'#69d7c1':'';
  $('device-name').textContent=cap(s.device_id || 'Disconnected',30);
  $('sensor-link').textContent=valid?'Data current':'No data / STALE';
  $('sensor-link').classList.toggle('online',valid);
}
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
  $('pg-zone-count').textContent='ZONE '+(zone===null?'—':zone+' people');
  $('pg-total-count').textContent='TOTAL '+(total===null?'—':total+' people');
  $('pg-motor-state').textContent='MOTOR '+(spinning===null?'—':spinning?'RUNNING':'STOPPED');
  $('pg-scene-distance').textContent='DIST '+(known(s.distance_cm)?Number(s.distance_cm).toFixed(1)+'cm':'—');
  $('pg-scene-belt').classList.toggle('moving',spinning===true);
  const label=overlay.parentElement.querySelector('.demo-camera-label');
  if(label)label.textContent='SENSOR SCENE  ·  Not actual camera footage';

  // 아이콘의 위치는 보기 위한 임의의 도식 배치이며, LIVE 좌표를 뜻하지 않음.
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
    person.title=hazard?'Worker in hazard zone (schematic position)':'Worker on site (schematic position)';
    people.append(person);
  }
  if(total!==null && total>displayTotal){
    const more=document.createElement('span');more.className='pg-more-persons';
    more.textContent='+'+(total-displayTotal)+' people';people.append(more);
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
  $('video-status').textContent=online?(frame?.simulation?'● Simulated video':'● Live video received'):
    virtual?'● Virtual scene · Sensor-based':demo?'● Demo Visualization':'● Waiting for data';
  $('camera-meta').textContent=online?`FRAME ${cap(frame.frame_id,12)} / ${data.camera.fps} FPS`:
    virtual?'SENSOR-DRIVEN SCENE · NOT VIDEO':demo?'DEMO SCENE':'SCENE OFFLINE';
  $('camera-utc').textContent=online?`FRAME ${cap(frame.frame_id,15)} · ${fmtTime(frame.received_at)} KST`:
    virtual?'LIVE SENSOR DATA · SYNTHETIC DISPLAY':demo?'SYNTHETIC SCENE · NOT A REAL CAMERA':'SENSOR DATA UNAVAILABLE';
  if(online && frame.received_at!==lastCameraFrame){
    lastCameraFrame=frame.received_at;
    $('camera-image').src='/api/frame/latest?ts='+encodeURIComponent(frame.received_at);
  }
}

function renderDecision(data){
  const level=data.risk.level;
  const color={CRITICAL:'#ff3e79',HIGH:'#fa6b77',WARNING:'#f4b56b',SAFE:'#49d9bd',UNKNOWN:'#849aac'}[level];
  const angle={CRITICAL:360,HIGH:300,WARNING:195,SAFE:70,UNKNOWN:0}[level];
  document.querySelector('.risk-ring').style.background=`conic-gradient(${color} 0 ${angle}deg,#304756 ${angle}deg)`;
  const label=$('decision-label');label.textContent=LEVEL_NAMES[level]||'UNKNOWN';label.style.color=color;
  $('decision-description').textContent=data.risk.fresh?cap(pgEnglishText(pgDisplayDescription(data.risk.last_result.description),'risk',data.risk.level),80):'No current valid risk assessment';
  $('decision-source').textContent=data.risk.fresh?cap(pgEnglishText(pgDisplaySource(data.risk.last_result.source),'source'),24):'—';
  $('decision-age').textContent=data.risk.fresh?data.risk.age_sec.toFixed(1)+' sec ago':'No data / expired';
}
function renderMnDevices(payload){
  const status=$('mn-cse-status');
  const grid=$('mn-device-grid');
  if(!payload || !payload.configured){
    status.textContent='설정 필요';status.classList.remove('online');
    grid.textContent='IN-CSE 경유 설정이 필요합니다. PG_IN_CSE_URL, PG_MN_CSE_ID, PG_IN_CSE_ORIGIN을 설정하세요.';
    $('mn-cse-footnote').textContent='현재 대시보드의 기존 센서·Risk level 데이터에는 영향을 주지 않습니다.';
    return;
  }
  status.textContent=`${payload.success_count}/${payload.device_count} 연결`;
  status.classList.toggle('online',payload.connected);
  grid.replaceChildren();
  for(const item of (payload.devices||[])){
    const card=document.createElement('article');card.className='mn-device-card';
    const head=document.createElement('div');head.className='mn-device-card-head';
    const name=document.createElement('b');name.textContent=item.device_id;head.append(name);
    const badge=document.createElement('span');badge.className='mn-device-badge '+(item.ok?(item.fresh?'fresh':'stale'):'error');badge.textContent=!item.ok?'조회 실패':item.fresh?'최신':'오래된 데이터';head.append(badge);card.append(head);
    if(item.ok){
      const data=item.data||{};const fields=document.createElement('dl');fields.className='mn-device-fields';
      const ignored=new Set(['rn','ri','pi','ct','et','lt','ty','st','cs','cnd','acpi','lbl','at','aa','cr','loc','daci','ol','lnk','ch','fopt','mni','mbs','mia','or','rq']);
      const entries=Object.entries(data).filter(([key,value])=>!ignored.has(key)&&value!==null&&typeof value!=='object');
      if(!entries.length){const empty=document.createElement('div');empty.className='mn-device-empty';empty.textContent='표시할 센서 속성 없음';fields.append(empty)}
      for(const [key,value] of entries){const row=document.createElement('div');row.className='mn-device-field';const dt=document.createElement('dt');dt.textContent=key;const dd=document.createElement('dd');dd.textContent=typeof value==='boolean'?(value?'true':'false'):String(value);row.append(dt,dd);fields.append(row)}
      card.append(fields);
      const time=document.createElement('div');time.className='mn-device-time';time.textContent=item.source_timestamp?`원본 수신 ${fmtTime(item.source_timestamp)} · ${item.data_age_sec===null?'나이 계산 불가':Math.floor(item.data_age_sec)+' sec ago'}`:'원본 수신 시각 없음';card.append(time);
    }else{
      const error=document.createElement('div');error.className='mn-device-error';error.textContent=item.error||'조회 실패';card.append(error);
    }
    grid.append(card);
  }
  $('mn-cse-footnote').textContent=`MN-CSE ${payload.cse_url}/${payload.cse_base}/${payload.container} · 조회 ${fmtTime(payload.fetched_at)} · 최신 기준 ${payload.fresh_threshold_sec}sec`;
}
async function refreshMnDevices(){
  try{const payload=await api('/api/onem2m/devices');renderMnDevices(payload)}
  catch(err){const status=$('mn-cse-status');if(status)status.textContent='조회 오류';const grid=$('mn-device-grid');if(grid)grid.textContent='MN-CSE 조회 오류: '+err.message}
}

function renderConnections(data){
  const video=data.camera.online;
  const sensor=data.sensor.fresh;
  $('conn-camera').textContent=video?'Video connected':(data.mode==='live'&&sensor)?'Sensor visualization (no video)':'Disconnected';$('conn-camera').className='conn-state '+(video?'ok':'');
  $('conn-sensor').textContent=sensor?'Data current':'No data';$('conn-sensor').className='conn-state '+(sensor?'ok':'');
  const age=data.one_m2m.notification_age_sec;
  $('conn-cse').textContent=age!==null?`Last notification ${age.toFixed(0)} sec ago`:'Not verified';
  $('conn-cse').className='conn-state '+(age!==null?'ok':'');
}
function renderEvents(data){
  const rows=data.events.filter(e=>e.category!=='SENSOR').slice(0,8);
  const tbody=$('event-table');tbody.replaceChildren();
  $('event-count').textContent=`${data.stats.risk_events} RISK EVENTS`;
  if(!rows.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=5;td.className='empty-table';td.textContent='No risk or alert events recorded';tr.append(td);tbody.append(tr);return}
  for(const e of rows){
    const tr=document.createElement('tr');
    const cols=[fmtTime(e.received_at),e.category,pgEnglishText(pgDisplayDescription(e.description),'event',e.severity),pgEnglishText(pgDisplaySource(e.source),'source')];
    for(let i=0;i<cols.length;i++){
      const td=document.createElement('td');
      if(i===1){const pill=document.createElement('span');pill.className='level-pill level-'+e.severity;pill.textContent=e.category==='RISK'?e.severity:e.category;td.append(pill)}
      else{td.textContent=cap(cols[i],i===2?60:25);td.title=String(cols[i])}
      tr.append(td);
    }
    const final=document.createElement('td');
    if(e.ack_at){const done=document.createElement('span');done.className='ack-done';done.textContent='✓ Acknowledged';final.append(done)}
    else if(e.category==='RISK'){
      const b=document.createElement('button');b.className='ack-btn';b.textContent='Acknowledge';b.addEventListener('click',async()=>{
        b.disabled=true;try{await api(`/api/events/${e.id}/ack`,'POST');showToast('Event acknowledged. The actual hazard state has not changed.');await refresh()}catch(err){showToast(err.message,true)}finally{b.disabled=false}
      });final.append(b);
    }else{final.textContent='—'}
    tr.append(final);tbody.append(tr);
  }
}
function drawChart(points){
  const canvas=$('distance-chart');if(!canvas)return;
  const r=canvas.getBoundingClientRect();if(r.width<10)return;
  const dpr=window.devicePixelRatio||1;canvas.width=Math.round(r.width*dpr);canvas.height=Math.round(r.height*dpr);
  const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);
  const w=r.width,h=r.height,pad={left:39,right:15,top:18,bottom:30};const iw=w-pad.left-pad.right,ih=h-pad.top-pad.bottom;
  ctx.clearRect(0,0,w,h);
  $('chart-empty').hidden=!!points?.length;
  if(!points?.length)return;
  const vals=points.map(p=>p.v);
  const max=Math.max(200,Math.ceil(Math.max(...vals,100)/50)*50);
  const x=i=>pad.left+(points.length===1 ? .5 : i/(points.length-1))*iw;
  const y=v=>pad.top+(max-v)/max*ih;
  ctx.font='10px system-ui';ctx.fillStyle='#668398';ctx.textAlign='right';
  for(let t=0;t<=4;t++){const v=max*t/4;const yp=y(v);ctx.beginPath();ctx.strokeStyle='#273b4a';ctx.setLineDash([3,5]);ctx.moveTo(pad.left,yp);ctx.lineTo(w-pad.right,yp);ctx.stroke();ctx.setLineDash([]);ctx.fillText(String(Math.round(v)),pad.left-9,yp+3)}
  for(const threshold of [50,100]){if(threshold>max)continue;ctx.beginPath();ctx.strokeStyle='#b888534f';ctx.setLineDash([7,5]);ctx.moveTo(pad.left,y(threshold));ctx.lineTo(w-pad.right,y(threshold));ctx.stroke();ctx.setLineDash([])}
  const grad=ctx.createLinearGradient(0,pad.top,0,h-pad.bottom);grad.addColorStop(0,'rgba(44,213,195,.30)');grad.addColorStop(1,'rgba(44,213,195,.01)');
  ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(x(i),y(p.v)):ctx.moveTo(x(i),y(p.v)));ctx.lineTo(x(points.length-1),y(0));ctx.lineTo(x(0),y(0));ctx.closePath();ctx.fillStyle=grad;ctx.fill();
  ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(x(i),y(p.v)):ctx.moveTo(x(i),y(p.v)));ctx.strokeStyle='#31e1ca';ctx.lineWidth=2.4;ctx.lineJoin='round';ctx.stroke();
  ctx.beginPath();ctx.fillStyle='#43e8d1';ctx.arc(x(points.length-1),y(points.at(-1).v),4,0,Math.PI*2);ctx.fill();
  ctx.fillStyle='#7691a3';ctx.textAlign='left';ctx.fillText(fmtTime(points[0].t).slice(0,5),pad.left,h-7);ctx.textAlign='right';ctx.fillText(fmtTime(points.at(-1).t).slice(0,5),w-pad.right,h-7);
}
async function refresh(){
  if(pending)return;pending=true;
  try{const data=await api('/api/state');renderState(data);loadErrorShown=false}
  catch(err){if(!loadErrorShown){showToast('API connection failed: '+err.message,true);loadErrorShown=true};$('footer-sync').textContent='Server connection error'}
  finally{pending=false}
}
$('btn-mode').addEventListener('click',async()=>{
  try{await api('/api/mode','POST',{mode:lastState?.mode==='demo'?'live':'demo'});await refresh()}
  catch(err){showToast(err.message,true)}
});
document.querySelectorAll('[data-scenario]').forEach(btn=>btn.addEventListener('click',async()=>{
  btn.disabled=true;try{await api('/api/demo','POST',{scenario:btn.dataset.scenario});showToast('Demo '+LEVEL_KO[btn.dataset.scenario]+' event created');await refresh()}
  catch(err){showToast(err.message,true)}finally{btn.disabled=false}
}));
document.querySelectorAll('.nav-item').forEach(a=>a.addEventListener('click',()=>{
  document.querySelectorAll('.nav-item').forEach(el=>el.classList.remove('active'));a.classList.add('active')
}));
function tickClock(){$('clock').textContent=new Date().toLocaleTimeString('en-GB',{hour12:false,timeZone:'Asia/Seoul'}).replace(/^24:/,'00:')}
setInterval(tickClock,1000);tickClock();refresh();refreshMnDevices();setInterval(refresh,1500);setInterval(refreshMnDevices,10000);
window.addEventListener('resize',()=>{if(lastState)drawChart(lastState.history)});
