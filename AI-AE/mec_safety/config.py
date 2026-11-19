import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE, override=False)


def _required_setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    normalized = value.upper()
    is_placeholder = (
        normalized.startswith(
            ("YOUR_", "YOUR ", "PLACEHOLDER", "REPLACE_", "CHANGE_", "CHANGEME", "TODO", "TBD")
        )
        or (normalized.startswith("<") and normalized.endswith(">"))
    )
    if not value or is_placeholder:
        raise ValueError(
            f"Required AI-AE setting {name} is missing or is a placeholder. "
            f"Set a concrete value in the project-root {ENV_FILE.name}."
        )
    return value


class Layer2Config:
    CSE_BASE_URL = _required_setting("CSE_BASE_URL")
    CSE_BASE_NAME = _required_setting("CSE_BASE_NAME")
    CSE_RVI = _required_setting("CSE_RVI")
    AE_NAME = _required_setting("AE_NAME")
    AE_ID = _required_setting("AE_ID")

    FCNT_RI = {
        "device1": _required_setting("FCNT_DEVICE1_RI"),
        "device2": _required_setting("FCNT_DEVICE2_RI"),
        "device3": _required_setting("FCNT_DEVICE3_RI"),
        "device4": _required_setting("FCNT_DEVICE4_RI"),
        "device5": _required_setting("FCNT_DEVICE5_RI"),
        "risk": _required_setting("FCNT_RISK_RI"),
    }