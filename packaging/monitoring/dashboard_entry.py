from __future__ import annotations

import os

import uvicorn

from app import app


def main() -> None:
    host = os.environ.get("PG_DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("PG_DASHBOARD_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, workers=1)


if __name__ == "__main__":
    main()
