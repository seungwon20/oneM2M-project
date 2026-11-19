from __future__ import annotations

import json
import socket
import sys
import uuid
from pathlib import Path
from typing import Any, Dict
from urllib.parse import quote, urlsplit

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mec_safety.config import Layer2Config

EXPECTED_FIELDS = {
    "device1": {"zone_person_count", "total_person_count", "received_at"},
    "device2": {"weight_kg", "received_at"},
    "device3": {"beam_blocked", "received_at"},
    "device4": {"is_rotating", "speed_rpm", "received_at"},
    "device5": {"distance_cm", "received_at"},
    "risk": {"risk_level", "speed_rpm", "distance_cm", "evaluated_at"},
}
EXPECTED_NAMES = {
    "device1": "Camera",
    "device2": "Weight",
    "device3": "Infrared",
    "device4": "Encoder",
    "device5": "Distance",
    "risk": "Risk",
}
EXPECTED_WRAPPERS = {
    "device1": "eg:Device1",
    "device2": "eg:Device2",
    "device3": "eg:Device3",
    "device4": "eg:Device4",
    "device5": "eg:Device5",
    "risk": "eg:Device6",
}


def _load_config_without_importing_application() -> type[Layer2Config]:
    return Layer2Config


def _one_m2m_headers(config: Any) -> Dict[str, str]:
    return {
        "Accept": "application/json",
        "X-M2M-Origin": config.AE_ID,
        "X-M2M-RI": str(uuid.uuid4()),
        "X-M2M-RVI": config.CSE_RVI,
    }


def _validate_config(config: Any) -> tuple[list[str], Any]:
    errors = []
    raw_url = getattr(config, "CSE_BASE_URL", None)
    if not isinstance(raw_url, str) or not raw_url.strip():
        errors.append("CSE_BASE_URL is empty or missing")
        parsed = None
    else:
        parsed = urlsplit(raw_url.strip())
        try:
            valid_port = parsed.port
        except ValueError as exc:
            valid_port = None
            errors.append(f"CSE_BASE_URL has an invalid port: {exc}")

        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.path.startswith("//")
        ):
            errors.append(f"CSE_BASE_URL is malformed: {raw_url!r}")
        elif valid_port is None and parsed.netloc.count(":") > 1 and not parsed.netloc.startswith("["):
            errors.append(f"CSE_BASE_URL has an invalid authority: {raw_url!r}")

    for attribute in ("CSE_BASE_NAME", "AE_ID", "CSE_RVI"):
        value = getattr(config, attribute, None)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{attribute} is empty or missing")

    resource_ids = getattr(config, "FCNT_RI", None)
    if not isinstance(resource_ids, dict):
        errors.append("FCNT_RI is missing or is not a mapping")
    else:
        expected_keys = set(EXPECTED_FIELDS)
        if set(resource_ids) != expected_keys:
            errors.append(
                "FCNT_RI must contain exactly "
                + ", ".join(sorted(expected_keys))
            )
        for key in sorted(expected_keys):
            value = resource_ids.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"FCNT_RI[{key!r}] is empty or missing")

    return errors, parsed


def _tcp_check(host: str, port: int) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=5):
            return True, f"TCP connection successful to {host}:{port}"
    except socket.gaierror as exc:
        return False, f"DNS Resolution Failure: {exc}"
    except TimeoutError as exc:
        return False, f"Connection Timeout: {exc}"
    except ConnectionRefusedError as exc:
        return False, f"Connection Refused: {exc}"
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10051:
            reason = "Network Unreachable"
        elif getattr(exc, "winerror", None) == 10065:
            reason = "Host Unreachable"
        else:
            reason = f"Network error ({exc})"
        return False, f"{reason}: {exc}"


def _response_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except (ValueError, json.JSONDecodeError):
        return response.text


def _unwrap_resource(body: Any) -> tuple[str | None, Dict[str, Any]]:
    if not isinstance(body, dict):
        return None, {}
    for wrapper, value in body.items():
        if isinstance(value, dict):
            return wrapper, value
    return None, body


def _print_resource_result(
    name: str,
    resource_id: str,
    response: httpx.Response | None,
    request_id: str,
    expected_fields: set[str],
    expected_wrapper: str,
) -> tuple[bool, bool]:
    if response is None:
        print(
            f"{name}: RI={resource_id} HTTP=NO RESPONSE RSC=N/A "
            "Retrieval=FAIL SchemaValidation=NOT RUN"
        )
        return False, False

    body = _response_body(response)
    wrapper, resource = _unwrap_resource(body)
    actual_ri = resource.get("ri")
    resource_type = resource.get("ty")
    cnd = resource.get("cnd")
    custom_fields = sorted(set(resource) - {
        "ri", "ty", "cnd", "rn", "pi", "ct", "lt", "cr", "cs", "st",
        "cni", "cbs", "et", "lbl", "acpi", "at", "aa", "ast",
    })
    missing_fields = sorted(expected_fields - set(custom_fields))
    extra_fields = sorted(set(custom_fields) - expected_fields)

    retrieval_checks = {
        "HTTP 200": response.status_code == 200,
        "RSC 2000": response.headers.get("X-M2M-RSC") == "2000",
        "response RI": actual_ri == resource_id,
        "ty 28": resource_type == 28 or resource_type == "28",
        "cnd present": cnd is not None,
    }
    retrieval_ok = all(retrieval_checks.values())
    schema_ok = wrapper == expected_wrapper and not missing_fields
    retrieval_status = ", ".join(
        f"{label}={'PASS' if valid else 'FAIL'}"
        for label, valid in retrieval_checks.items()
    )
    print(
        f"{name}: RI={actual_ri!r} ty={resource_type!r} cnd={cnd!r} "
        f"wrapper={wrapper!r} expected_wrapper={expected_wrapper!r} "
        f"fields={custom_fields} missing_fields={missing_fields} "
        f"extra_fields={extra_fields} HTTP={response.status_code} "
        f"RSC={response.headers.get('X-M2M-RSC')!r} "
        f"request_RI={request_id!r} "
        f"Retrieval={'PASS' if retrieval_ok else 'FAIL'} "
        f"SchemaValidation={'PASS' if schema_ok else 'FAIL'}"
    )
    if not retrieval_ok or not schema_ok:
        print(
            f"  Retrieval checks: {retrieval_status}; "
            f"wrapper_match={wrapper == expected_wrapper}"
        )
        print(f"  Response body: {body!r}")
    return retrieval_ok, schema_ok


def main() -> int:
    config = _load_config_without_importing_application()
    errors, parsed = _validate_config(config)
    print("Preflight configuration:")
    if errors:
        for error in errors:
            print(f"  FAIL: {error}")
        print("\nCSE Connection: BLOCKED — configuration must be corrected by its owner.")
        print("No network requests were made.")
        print("\nFlexContainer Retrieval:")
        for key, name in EXPECTED_NAMES.items():
            resource_id = getattr(config, "FCNT_RI", {}).get(key, "<missing>")
            print(f"{name}: RI={resource_id} HTTP=NOT RUN RSC=N/A Result=BLOCKED")
        print("\nFinal Assessment: Unable to assess because configuration preflight failed.")
        return 2

    assert parsed is not None
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    tcp_ok, tcp_message = _tcp_check(host, port)
    print(f"\nTCP Connection: {'PASS' if tcp_ok else 'FAIL'} — {tcp_message}")
    if not tcp_ok:
        print("HTTP Response: NOT RUN")
        print("CSE Base Retrieval: NOT RUN")
        print("FlexContainer Retrieval: NOT RUN")
        print("\nFinal Assessment: Network connection failed.")
        return 1

    base_url = f"{parsed.scheme}://{parsed.netloc}"
    base_target = f"{base_url}/{quote(config.CSE_BASE_NAME, safe='')}?rcn=1"
    all_http_ok = True
    with httpx.Client(timeout=8) as client:
        try:
            base_response = client.get(
                base_target, headers=_one_m2m_headers(config)
            )
            base_rsc_ok = base_response.headers.get("X-M2M-RSC") == "2000"
            base_ok = base_response.status_code == 200 and base_rsc_ok
            print(
                f"HTTP Response: {'PASS' if base_response.status_code < 500 else 'FAIL'} "
                f"(HTTP {base_response.status_code})"
            )
            print(
                f"CSE Base Retrieval: {'PASS' if base_ok else 'FAIL'} "
                f"(HTTP {base_response.status_code}, "
                f"RSC={base_response.headers.get('X-M2M-RSC')!r}, "
                f"body={_response_body(base_response)!r})"
            )
            all_http_ok = base_ok
        except httpx.HTTPError as exc:
            print(f"HTTP Response: FAIL — {exc}")
            print(f"CSE Base Retrieval: FAIL — {exc}")
            all_http_ok = False

        retrieval_results = []
        schema_results = []
        print("\nFlexContainer Retrieval:")
        for key, name in EXPECTED_NAMES.items():
            resource_id = config.FCNT_RI[key]
            encoded_id = quote(resource_id, safe="-")
            target = f"{base_url}/{encoded_id}?rcn=1"
            request_id = str(uuid.uuid4())
            try:
                response = client.get(
                    target,
                    headers={
                        **_one_m2m_headers(config),
                        "X-M2M-RI": request_id,
                    },
                )
            except httpx.HTTPError as exc:
                print(
                    f"{name}: RI={resource_id} HTTP=NO RESPONSE "
                    f"RSC=N/A Retrieval=FAIL SchemaValidation=NOT RUN "
                    f"Error={exc}"
                )
                retrieval_results.append(False)
                schema_results.append(False)
                continue
            retrieval_ok, schema_ok = _print_resource_result(
                name,
                resource_id,
                response,
                request_id,
                EXPECTED_FIELDS[key],
                EXPECTED_WRAPPERS[key],
            )
            retrieval_results.append(retrieval_ok)
            schema_results.append(schema_ok)

    if all_http_ok and all(retrieval_results) and all(schema_results):
        assessment = "CSE connection and all 6 resource retrievals and validations succeeded."
    elif all_http_ok and all(retrieval_results):
        assessment = (
            "CSE connection and all 6 GET retrievals succeeded, but resource "
            "wrapper or custom-field validation differed from the specification."
        )
    elif tcp_ok and any(retrieval_results):
        assessment = "CSE connected; some resource retrieval or validation failed."
    elif tcp_ok:
        assessment = "TCP connected, but oneM2M requests failed."
    else:
        assessment = "Network connection failed."
    print(f"\nFinal Assessment: {assessment}")
    return (
        0
        if all_http_ok and all(retrieval_results) and all(schema_results)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
