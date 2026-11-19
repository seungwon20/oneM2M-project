"""Risk scenario generator is explicitly simulated (not vision AI)."""
import importlib.util
from pathlib import Path
import numpy as np

module_path = Path(__file__).resolve().parents[1] / 'camera_sender.py'
spec = importlib.util.spec_from_file_location('pg_sender_auto', module_path)
sender = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sender)


def test_cycle_levels():
    levels = [sender.judge_risk(sender.sensor_scenario(t, 24, 1)) for t in range(25)]
    assert 'SAFE' in levels
    assert 'WARNING' in levels
    assert 'HIGH' in levels
    assert 'CRITICAL' in levels
    # The repeated cycle returns to SAFE.
    assert levels[0] == levels[-1] == 'SAFE'


def test_unknown_missing_fields():
    assert sender.judge_risk({'presence': True}) == 'UNKNOWN'


def test_overlay_is_valid_rgb_like_frame():
    sensor = sender.sensor_scenario(13, 24, 1)
    frame = sender.synthetic_image(20)
    out = sender.draw_scenario_overlay(frame, sensor, sender.judge_risk(sensor))
    assert isinstance(out, np.ndarray)
    assert out.shape == (540, 960, 3)


def test_dashboard_url_validation():
    assert sender.dashboard_base_from_frame_url('http://localhost:8000/api/frame') == 'http://localhost:8000'
    try:
        sender.dashboard_base_from_frame_url('http://localhost:8001/frames')
    except ValueError:
        pass
    else:
        raise AssertionError('should reject wrong API URL')


def test_four_severity_rules():
    base={'distance_cm':12,'presence':True,'beam_blocked':True,'machine_running':True}
    assert sender.judge_risk(base)=='CRITICAL'
    assert sender.judge_risk({**base,'distance_cm':31})=='HIGH'
    assert sender.judge_risk({**base,'distance_cm':78,'beam_blocked':False})=='WARNING'
    assert sender.judge_risk({**base,'distance_cm':165,'beam_blocked':False,'presence':False})=='SAFE'
    assert sender.judge_risk({**base,'machine_running':None})=='UNKNOWN'
