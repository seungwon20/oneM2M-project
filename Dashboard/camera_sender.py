"""PinchGuard Camera Sender - transmit genuine webcam, MP4, or RTSP images.

For a realistic feed, use an actual webcam or a recorded video file.
Synthetic mode is a drawn simulator, NOT real footage or AI detection.

Examples:
    python camera_sender_realistic.py --source ./factory.mp4 --loop --fps 12
    python camera_sender_realistic.py --source 0 --fps 12
    python camera_sender_realistic.py --source synthetic --fps 10
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import sys
import time

import cv2
import numpy as np
import requests
from urllib.parse import urlsplit, urlunsplit


def synthetic_image(i: int, width: int = 960) -> np.ndarray:
    """Animated, intentionally stylized equipment demo; not a real camera feed."""
    h, w = 540, 960
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    # A layered factory-like SCHEMATIC (deliberately not a photograph).
    y_grad = np.linspace(76, 38, h, dtype=np.uint8)
    frame[:] = np.stack((y_grad, y_grad + 8, y_grad + 11), axis=1)[:, None, :]
    cv2.rectangle(frame, (0, 342), (w, h), (66, 69, 73), -1)
    cv2.rectangle(frame, (42, 88), (900, 300), (108, 109, 112), -1)
    for x in range(40, 930, 130):
        cv2.line(frame, (x, 88), (x, 300), (73, 76, 79), 10)
    for x in range(60, 930, 78):
        cv2.line(frame, (x, 346), (x - 60, h), (80, 82, 84), 2)
    # Conveyor belt and moving parcels
    cv2.rectangle(frame, (104, 302), (859, 356), (27, 30, 33), -1)
    cv2.rectangle(frame, (112, 307), (851, 335), (96, 101, 105), -1)
    for x in range(132, 860, 90):
        cv2.circle(frame, (x, 356), 15, (151, 156, 160), -1)
        cv2.circle(frame, (x, 356), 6, (42, 44, 48), -1)
    speed = (i * 17) % 840
    for k in range(-1, 3):
        x = int(104 + ((speed + k * 255) % 870) - 80)
        if 125 < x < 800:
            cv2.rectangle(frame, (x, 257), (x + 75, 309), (105, 162, 203), -1)
            cv2.rectangle(frame, (x + 7, 264), (x + 68, 301), (83, 133, 172), 2)
    # Animated warning lamp
    on = i % 14 < 7
    cv2.rectangle(frame, (735, 195), (768, 224), (26, 28, 31), -1)
    cv2.circle(frame, (751, 184), 16, (40, 180, 250) if on else (23, 57, 84), -1)
    cv2.putText(frame, 'SIMULATED FACTORY SCENE - NOT A CAMERA', (148, 65),
                cv2.FONT_HERSHEY_SIMPLEX, 0.73, (219, 224, 227), 2, cv2.LINE_AA)
    if width != w:
        frame = cv2.resize(frame, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)
    return frame


def cctv_overlay(frame: np.ndarray, camera_id: str, frame_number: int, *, zone: bool = True,
                 source_kind: str = "live") -> np.ndarray:
    """Add presentation-only CCTV metadata; do not imply working AI detections."""
    height, width = frame.shape[:2]
    scale = max(0.48, width / 960)
    thickness = max(1, int(round(width / 950)))
    pad = max(14, int(width * 0.024))
    overlay = frame.copy()
    bar = max(48, int(height * 0.092))
    cv2.rectangle(overlay, (0, 0), (width, bar), (7, 12, 17), -1)
    cv2.rectangle(overlay, (0, height - bar), (width, height), (7, 12, 17), -1)
    cv2.addWeighted(overlay, 0.64, frame, 0.36, 0, dst=frame)
    red = (56, 56, 255)
    green = (155, 238, 153)
    white = (241, 242, 245)
    cv2.circle(frame, (pad + 9, bar // 2), max(4, int(6 * scale)), red, -1)
    cv2.putText(frame, 'REC', (pad + 25, bar // 2 + int(7 * scale)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.76 * scale, white, thickness + 1, cv2.LINE_AA)
    source_label = {'simulated': 'SIMULATION', 'replay': 'VIDEO REPLAY', 'live': 'LIVE CAMERA'}.get(source_kind, 'INPUT')
    cv2.putText(frame, f'{camera_id.upper()}  |  {source_label}',  (pad + int(125 * scale), bar // 2 + int(7 * scale)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.66 * scale, white, thickness + 1, cv2.LINE_AA)
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cv2.putText(frame, stamp, (pad, height - max(16, int(19 * scale))),
                cv2.FONT_HERSHEY_SIMPLEX, 0.64 * scale, white, thickness, cv2.LINE_AA)
    tag = {'simulated': 'SIMULATED / NO AI', 'replay': 'RECORDED VIDEO / NO AI', 'live': 'LIVE VIDEO / NO AI'}.get(source_kind, 'NO AI')
    textsize, _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.55 * scale, thickness)
    cv2.putText(frame, tag, (max(pad, width - textsize[0] - pad), height - max(16, int(19 * scale))),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55 * scale, green, thickness, cv2.LINE_AA)
    if zone:
        # Fixed user-configurable demonstration ROI, NOT an AI detection bounding box.
        x1, y1, x2, y2 = int(width * .59), int(height * .24), int(width * .87), int(height * .75)
        cyan = (94, 225, 242)
        cv2.rectangle(frame, (x1, y1), (x2, y2), cyan, thickness)
        cv2.putText(frame, 'DEMO RISK ZONE', (x1, max(bar + 18, y1 - 9)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.56 * scale, cyan, thickness, cv2.LINE_AA)
    return frame


def open_source(source: str, width: int) -> tuple[cv2.VideoCapture | None, bool, float]:
    if source == 'synthetic':
        return None, False, 0.0
    src = int(source) if source.isdigit() else source
    if isinstance(src, str) and not src.lower().startswith(('rtsp://','http://','https://')) and not Path(src).is_file():
        raise SystemExit(f'Video file not found: {src}')
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise SystemExit(f'Cannot open camera/video source: {source}\n'
                         'On WSL, a Windows USB webcam may not be exposed. Run the sender in Windows Python, '
                         'or use an MP4 file inside WSL.')
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # backend-dependent hint
    is_file = isinstance(src, str) and Path(src).is_file()
    source_fps = cap.get(cv2.CAP_PROP_FPS) if is_file else 0.0
    return cap, is_file, float(source_fps) if source_fps and math.isfinite(source_fps) else 0.0



# ---------------------------------------------------------------------------
# SYNTHETIC SCENARIO: generated sensor values, NOT a computer vision model.
# The risk is computed from simulated distance/beam/machine-running signals.
# ---------------------------------------------------------------------------

def sensor_scenario(elapsed: float, cycle_seconds: float, sequence: int) -> dict:
    """Loop through SAFE -> WARNING -> HIGH -> CRITICAL -> HIGH -> WARNING -> SAFE.

    Synthetic distances are for UI demonstrations, NOT validated safety limits.
    """
    phase = (elapsed % cycle_seconds) / cycle_seconds
    keys = [(0.00, 170.0), (0.14, 155.0), (0.30, 85.0),
            (0.42, 32.0), (0.49, 29.0), (0.58, 12.0),
            (0.67, 12.0), (0.75, 34.0), (0.83, 85.0), (1.00, 170.0)]
    for (p1, v1), (p2, v2) in zip(keys, keys[1:]):
        if phase <= p2:
            f = max(0.0, min(1.0, (phase - p1) / (p2 - p1)))
            distance_cm = round(v1 + (v2-v1)*f, 1)
            break
    else:
        distance_cm = 170.0
    presence = distance_cm < 140.0
    beam_blocked = distance_cm <= 35.0
    return {
        'device_id': 'ESP32-SIM-01', 'sequence': sequence,
        'distance_cm': distance_cm, 'presence': presence,
        'beam_blocked': beam_blocked, 'machine_running': True,
        'rpm': 520.0, 'simulation': True,
        'timestamp_utc': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
    }


def judge_risk(sensor: dict) -> str:
    """Educational rule-based classification, not a validated safety function."""
    if any(sensor.get(k) is None for k in ('distance_cm','presence','beam_blocked','machine_running')):
        return 'UNKNOWN'
    # Demonstration-only priority: CRITICAL must be evaluated before HIGH.
    if sensor['machine_running'] and sensor['presence'] and sensor['beam_blocked'] and sensor['distance_cm'] <= 20:
        return 'CRITICAL'
    if sensor['machine_running'] and sensor['presence'] and (sensor['beam_blocked'] or sensor['distance_cm'] <= 45):
        return 'HIGH'
    if sensor['machine_running'] and sensor['presence'] and sensor['distance_cm'] <= 105:
        return 'WARNING'
    return 'SAFE'


def draw_scenario_overlay(frame: np.ndarray, sensor: dict, level: str) -> np.ndarray:
    """Render a moving schematic worker marker and simulated state."""
    h, w = frame.shape[:2]
    dist = float(sensor['distance_cm'])
    color = {'SAFE': (131, 216, 94), 'WARNING': (60, 195, 255), 'HIGH': (66, 75, 255), 'CRITICAL': (160, 35, 235), 'UNKNOWN': (192, 192, 192)}[level]
    radius = max(7, w // 75)
    # Marker enters the demo ROI as distance decreases. No real-person tracking.
    cx = round(w * (0.28 + 0.41 * (170 - dist) / 150))
    cy = round(h * 0.56)
    cv2.circle(frame, (cx, cy), radius, color, -1)
    cv2.circle(frame, (cx, cy), radius + 6, color, 2)
    cv2.putText(frame, f'SIM: {dist:.0f} cm', (max(10, cx - 55), min(h - 80, cy + 38)),
                cv2.FONT_HERSHEY_SIMPLEX, max(0.4, w/1900), color, 2, cv2.LINE_AA)
    cv2.rectangle(frame, (12, round(h*0.16)), (round(w*0.39), round(h*0.24)), (10, 12, 18), -1)
    cv2.putText(frame, f'RULE-BASED: {level}', (22, round(h*0.215)),
                cv2.FONT_HERSHEY_SIMPLEX, max(0.52, w/1200), color, 2, cv2.LINE_AA)
    return frame


def dashboard_base_from_frame_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.path.endswith('/api/frame'):
        raise ValueError('Auto-scenario requires a PinchGuard Dashboard URL ending in /api/frame')
    return urlunsplit((parts.scheme, parts.netloc, parts.path[:-len('/api/frame')], '', '')).rstrip('/')


def api_post_json(session: requests.Session, base: str, path: str, data: dict, key: str) -> bool:
    try:
        resp = session.post(base+path, json=data, headers={'X-API-Key':key}, timeout=3)
        resp.raise_for_status()
        return bool(resp.json().get('accepted'))
    except (requests.RequestException, ValueError) as exc:
        print(f'API send failed ({path}): {exc}', file=sys.stderr)
        return False

def main() -> None:
    parser = argparse.ArgumentParser(description='Real/live-looking camera sender for the PinchGuard Dashboard')
    parser.add_argument('--url', default='http://127.0.0.1:8000/api/frame',
                        help='Dashboard ingest endpoint')
    parser.add_argument('--source', default='synthetic',
                        help='0 for webcam, a video file, RTSP URL, or synthetic')
    parser.add_argument('--camera-id', default='CAM-01')
    parser.add_argument('--fps', type=float, default=10.0)
    parser.add_argument('--width', type=int, default=960)
    parser.add_argument('--quality', type=int, default=82)
    parser.add_argument('--count', type=int, default=0, help='0 continuously transmits until Ctrl+C')
    parser.add_argument('--loop', action='store_true', help='Loop local MP4/AVI files on EOF')
    parser.add_argument('--no-overlay', action='store_true', help='Disable CCTV text/REC overlays')
    parser.add_argument('--no-zone', action='store_true', help='Do not draw demonstration risk region')
    parser.add_argument('--preview', action='store_true', help='Open optional local OpenCV preview window')
    parser.add_argument('--risk-mode', choices=('auto','simulate','off'), default='auto',
                        help='auto: simulation only with synthetic source; simulate: mock data with any source; off: frames only')
    parser.add_argument('--cycle-seconds', type=float, default=24.0,
                        help='length of repeated SAFE-WARNING-HIGH-CRITICAL-HIGH-WARNING-SAFE simulation')
    parser.add_argument('--sensor-every', type=float, default=1.0, help='seconds between sensor API posts')
    parser.add_argument('--risk-every', type=float, default=4.0, help='risk heartbeat seconds; immediately on level changes')
    parser.add_argument('--no-auto-live', action='store_true',
                        help='do not automatically switch dashboard from demo cards to incoming API data')
    args = parser.parse_args()

    key = os.environ.get('PG_API_KEY') or os.environ.get('PG_INGEST_KEY')
    if not key:
        parser.error("set PG_API_KEY (must match dashboard PG_INGEST_KEY)")
    if args.fps <= 0 or args.width <= 0 or not (1 <= args.quality <= 100) or args.count < 0 or args.cycle_seconds < 2 or args.sensor_every <= 0 or args.risk_every <= 0:
        parser.error('fps / width / quality / count out of range')
    simulate = (args.risk_mode == 'simulate' or (args.risk_mode == 'auto' and args.source == 'synthetic'))
    base = dashboard_base_from_frame_url(args.url) if simulate else None
    cap, is_file, source_fps = open_source(args.source, args.width)
    if args.loop and not is_file:
        print('NOTE: --loop is only relevant for local video files', file=sys.stderr)
    if source_fps > args.fps:
        print(f'Input video {source_fps:.1f} fps -> send {args.fps:.1f} fps (frames skipped to preserve real-time pace)')
    session = requests.Session()
    sent = 0
    sensor_sequence = 0
    last_sensor_at = -1e9
    last_risk_at = -1e9
    last_risk_level = None
    transitions = 0
    start = time.monotonic()
    if simulate and not args.no_auto_live:
        try:
            rr=session.post(base+'/api/mode', json={'mode':'live'}, timeout=3)
            rr.raise_for_status()
            print('Dashboard mode set to incoming API data (SIMULATED source, not AI).')
        except requests.RequestException as exc:
            print(f'Could not auto-select incoming API view: {exc}', file=sys.stderr)
    print(f'Start sending {args.source} -> {args.url} at {args.fps:g} fps; Ctrl+C to stop')
    try:
        while args.count == 0 or sent < args.count:
            began = time.monotonic()
            elapsed = began - start
            sensor_data = sensor_scenario(elapsed, args.cycle_seconds, sensor_sequence + 1) if simulate else None
            level = judge_risk(sensor_data) if simulate else None
            if cap is None:
                frame = synthetic_image(sent + 1, args.width)
            else:
                ok, frame = cap.read()
                if not ok and is_file and args.loop:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, frame = cap.read()
                if not ok:
                    print('No frame available / end of video. Stopping.', file=sys.stderr)
                    break
                # Preserve roughly natural speed when sending a 30fps file at 10fps.
                if is_file and source_fps > args.fps:
                    skips = max(0, round(source_fps / args.fps) - 1)
                    for _ in range(skips):
                        if not cap.grab():
                            break
                if frame.shape[1] != args.width:
                    height = max(1, round(frame.shape[0] * args.width / frame.shape[1]))
                    frame = cv2.resize(frame, (args.width, height), interpolation=cv2.INTER_AREA)
            if not args.no_overlay:
                frame = cctv_overlay(frame, args.camera_id, sent + 1,
                                     zone=not args.no_zone,
                                     source_kind='simulated' if args.source == 'synthetic' else ('replay' if is_file else 'live'))
            if simulate:
                frame = draw_scenario_overlay(frame, sensor_data, level)
            ok, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, args.quality])
            if not ok:
                print('JPEG encoding failed', file=sys.stderr)
                continue
            sent += 1
            headers = {
                'Content-Type': 'image/jpeg',
                'X-API-Key': key,
                'X-Camera-ID': args.camera_id,
                'X-Frame-ID': str(sent),
                'X-Sent-At-Ms': str(int(time.time() * 1000)),
                'X-PG-Simulation': '1' if (simulate or args.source == 'synthetic') else '0',
            }
            try:
                response = session.post(args.url, data=jpeg.tobytes(), headers=headers, timeout=4)
                response.raise_for_status()
                print(f'frame={sent} HTTP={response.status_code} bytes={len(jpeg)}'
                      + (f' accepted={response.json().get("accepted")}' if response.headers.get('content-type','').startswith('application/json') else ''))
            except (requests.RequestException, ValueError) as exc:
                print(f'Frame {sent} send failed: {exc}', file=sys.stderr)
            if simulate:
                if began - last_sensor_at >= args.sensor_every:
                    sensor_sequence += 1
                    sensor_data['sequence'] = sensor_sequence
                    if api_post_json(session, base, '/api/sensor', sensor_data, key):
                        last_sensor_at = began
                changed = level != last_risk_level
                if changed or began - last_risk_at >= args.risk_every:
                    risk_payload = {
                        'event_id': f'SIM-{int(time.time()*1000)}-{sent}',
                        'camera_id': args.camera_id,
                        'risk_level': level,
                        'distance_cm': sensor_data['distance_cm'],
                        'simulation': True,
                        'description': {
                            'SAFE': '가상 시나리오: 작업자가 위험구역 밖에 있음',
                            'WARNING': '가상 시나리오: 가동 중인 설비에 작업자 접근',
                            'HIGH': '가상 시나리오: 접근 거리 임계값 또는 광전식 경계 침범',
                            'CRITICAL': '가상 시나리오: 설비 가동 중 광전식 경계 차단 및 근접 구역 진입',
                            'UNKNOWN': '가상 시나리오: 센서 입력 불명확',
                        }[level] + f' (거리 {sensor_data["distance_cm"]:.0f}cm; 규칙 기반, AI 아님)',
                    }
                    if api_post_json(session, base, '/api/risk', risk_payload, key):
                        if changed:
                            transitions += 1
                            print(f'  >>> Risk: {last_risk_level or "START"} -> {level} '
                                  f'({sensor_data["distance_cm"]:.1f}cm, beam={sensor_data["beam_blocked"]})')
                        last_risk_level = level
                        last_risk_at = began
            if args.preview:
                try:
                    cv2.imshow('PinchGuard Camera Sender', frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                except cv2.error as exc:
                    print(f'Preview failed (headless OpenCV?): {exc}', file=sys.stderr)
                    args.preview = False
            time.sleep(max(0.0, 1.0 / args.fps - (time.monotonic() - began)))
    except KeyboardInterrupt:
        print('\nStopped by user')
    finally:
        if cap is not None:
            cap.release()
        session.close()
        if args.preview:
            cv2.destroyAllWindows()
    elapsed = time.monotonic() - start
    print(f'Finished: {sent} frames, {transitions} acknowledged risk states, {elapsed:.1f}s')


if __name__ == '__main__':
    main()
