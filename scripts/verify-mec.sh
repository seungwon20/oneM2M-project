#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
AI_AE_DIR="${PROJECT_ROOT}/AI-AE"
PYTHON="${AI_AE_DIR}/.venv/bin/python"
RUNTIME_DB="${PROJECT_ROOT}/MN-CSE/runtime/data.db"
SEED_DB="${PROJECT_ROOT}/MN-CSE/data.db"

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

if [[ -z "${WSL_DISTRO_NAME:-}" ]] && ! grep -qiE 'microsoft|wsl' /proc/sys/kernel/osrelease; then
    fail "Run this verifier inside WSL."
fi

[[ -x "${PYTHON}" ]] || fail "AI-AE/.venv is missing; create and install the WSL virtual environment first."
[[ -f "${RUNTIME_DB}" ]] || fail "MN-CSE runtime database is missing; start MN-CSE with scripts/run.py first."

for command in curl grep mktemp timeout; do
    command -v "${command}" >/dev/null 2>&1 || fail "Required command is missing: ${command}"
done

printf 'AI-AE health: '
if ! curl --silent --show-error --fail --max-time 5 \
    http://127.0.0.1:8001/health >/dev/null 2>&1; then
    fail "AI-AE health endpoint is unavailable."
fi
printf 'PASS\n'

printf '\nInitial MN-CSE connection and schema check:\n'
"${PYTHON}" "${AI_AE_DIR}/tests/check_cse_connection.py" \
    || fail "MN-CSE connection or resource validation failed."

database_fingerprint() {
    "${PYTHON}" - "${RUNTIME_DB}" <<'PY'
import hashlib
import sqlite3
import sys

connection = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True, timeout=5)
try:
    rows = connection.execute(
        "SELECT g.rn, g.lt, f.custom_attrs "
        "FROM general g JOIN fcnt f ON f.id = g.id "
        "WHERE g.rn IN ('Device1', 'Device2', 'Device3', 'Device4', 'Device5', 'Device6') "
        "ORDER BY g.rn"
    ).fetchall()
finally:
    connection.close()

if len(rows) != 6:
    raise SystemExit("Runtime DB does not contain all six configured FlexContainers.")
print(hashlib.sha256(repr(rows).encode("utf-8")).hexdigest())
PY
}

seed_fingerprint() {
    "${PYTHON}" - "${SEED_DB}" <<'PY'
import hashlib
import sys

digest = hashlib.sha256()
with open(sys.argv[1], "rb") as seed:
    for chunk in iter(lambda: seed.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
}

before_update="$(database_fingerprint)" || fail "Could not read runtime DB in read-only mode."
seed_before="$(seed_fingerprint)" || fail "Could not fingerprint the seed DB."
sender_log="$(mktemp)"
trap 'rm -f -- "${sender_log}"' EXIT

set +e
(
    cd -- "${AI_AE_DIR}"
    timeout 90 "${PYTHON}" -m mec_safety.send_mock_data --once
) >"${sender_log}" 2>&1
sender_status=$?
set -e

if [[ ${sender_status} -ne 0 ]]; then
    fail "Mock sensor sender failed (exit ${sender_status}); output suppressed to avoid exposing configuration values."
fi

sensor_count="$(grep -Ec '^\[[^]]+\] device[1-5]: HTTP 200; Layer2 success=True RSC=2004$' "${sender_log}" || true)"
[[ "${sensor_count}" -eq 5 ]] || fail "Expected five successful sensor updates; received ${sensor_count}."
grep -Eq '^\[[^]]+\] ML=.*Device6 success=True RSC=2004$' "${sender_log}" \
    || fail "Risk assessment or Device6 update did not succeed."
grep -E '^\[[^]]+\] (device[1-5]: HTTP|ML=)' "${sender_log}"

critical_sample="$(PYTHONPATH="${AI_AE_DIR}" "${PYTHON}" - "${AI_AE_DIR}/mec_safety/mock_sensor_dataset.csv" <<'PY'
import csv
import json
from pathlib import Path
import sys

from mec_safety.sensorTriggerEngine import SensorTriggerEngine

dataset = Path(sys.argv[1])
engine = SensorTriggerEngine()
with dataset.open("r", newline="", encoding="utf-8") as source:
    for row in csv.DictReader(source):
        if row["device3_beam_blocked"] != "True" or row["device4_is_rotating"] != "True":
            continue
        features = [[
            int(row["device1_zone_person_count"]),
            int(row["device1_zone_total_count"]),
            float(row["device4_speed_rpm"]),
            float(row["device5_distance_cm"]),
        ]]
        if str(engine.model.predict(features)[0]) != "CRITICAL":
            continue
        print(json.dumps({
            "device1": {
                "zone_person_count": features[0][0],
                "total_person_count": features[0][1],
            },
            "device2": {"weight_kg": float(row["device2_weight_kg"])},
            "device4": {
                "is_rotating": True,
                "speed_rpm": features[0][2],
            },
            "device5": {"distance_cm": features[0][3]},
            "device3": {"beam_blocked": True},
        }))
        break
PY
)" || fail "Could not inspect model predictions for a critical mock sample."

if [[ -n "${critical_sample}" ]]; then
    critical_result="$("${PYTHON}" - "${critical_sample}" <<'PY'
import json
import sys

import httpx

payloads = json.loads(sys.argv[1])
with httpx.Client(timeout=30, trust_env=False) as client:
    result = None
    for device_id in ("device1", "device2", "device4", "device5", "device3"):
        response = client.post(
            f"http://127.0.0.1:8001/api/devices/{device_id}/data",
            json=payloads[device_id],
        )
        response.raise_for_status()
        result = response.json()

if not isinstance(result, dict):
    raise SystemExit(1)
risk = result.get("risk_assessment")
risk_handoff = result.get("risk_handoff")
plc = result.get("plc_result")
ack = plc.get("ack") if isinstance(plc, dict) else None
status = plc.get("status") if isinstance(plc, dict) else None
if (
    not isinstance(risk, dict)
    or risk.get("risk_level") != "Critical"
    or not isinstance(risk_handoff, dict)
    or not risk_handoff.get("success")
    or risk_handoff.get("x_m2m_rsc") != "2004"
    or not isinstance(plc, dict)
    or not plc.get("success")
    or not isinstance(ack, dict)
    or ack.get("status") != "STOP_ACCEPTED"
    or not isinstance(status, dict)
    or status.get("status") != "STOPPED"
):
    raise SystemExit(1)
print("Model-predicted CRITICAL and Device6 update: PASS")
print("Mock PLC STOP_ACCEPTED and STOPPED: PASS")
PY
    )" || fail "Model-predicted CRITICAL or Mock PLC STOP verification failed; details suppressed."
    printf '%s\n' "${critical_result}"
else
    printf 'Mock PLC CRITICAL STOP test: NOT RUN (no qualifying model-predicted sample).\n'
fi

after_update="$(database_fingerprint)" || fail "Could not verify runtime DB after sensor updates."
[[ "${before_update}" != "${after_update}" ]] \
    || fail "Runtime DB contents did not change after successful oneM2M updates."
printf 'Runtime DB update: PASS (seed DB was not modified)\n'
seed_after="$(seed_fingerprint)" || fail "Could not fingerprint the seed DB after updates."
[[ "${seed_before}" == "${seed_after}" ]] || fail "Seed DB changed during integration verification."
printf 'Seed DB unchanged: PASS\n'

printf '\nFinal MN-CSE connection and schema check:\n'
"${PYTHON}" "${AI_AE_DIR}/tests/check_cse_connection.py" \
    || fail "Final MN-CSE connection or resource validation failed."

printf '\nMEC integration verification: PASS\n'
