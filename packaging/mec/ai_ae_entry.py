from __future__ import annotations

import os

import uvicorn
from mec_safety.app import app


def main() -> None:
    host = os.environ.get("AI_AE_HOST", "127.0.0.1")
    port = int(os.environ.get("AI_AE_PORT", "8001"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
