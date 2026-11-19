# Monitoring Package

The Linux x86_64 Monitoring Package contains the TinyIoT IN-CSE binary and the
PinchGuard Dashboard backend/frontend. They run on the same Monitoring Node;
the Dashboard polls the registered MEC MN-CSE through IN-CSE.

## Configure and run

```bash
./scripts/configure-monitoring
```

Edit `config/.env` and set `IN_CSE_SERVER_IP` to the Monitoring Node's
reachable address, a strong `PG_INGEST_KEY`, and `PG_IN_CSE_ORIGIN` to an
originator accepted by the IN-CSE access-control policy. `PG_IN_CSE_URL`
defaults to the local IN-CSE because both services run on this node. Do not
set it to a MEC localhost address; the MEC MN-CSE is reached only by oneM2M
forwarding after registration.

```bash
./scripts/start-monitoring
./scripts/status-monitoring
./scripts/healthcheck
./scripts/stop-monitoring
```

The controller starts IN-CSE, checks its CSE Base, then starts the Dashboard.
It does not require the MEC Node to be online. The Dashboard reports an
unavailable MEC connection until a MN-CSE registers and its POA is reachable.
Logs, SQLite data, and PID files are stored under `runtime/`; back them up
before replacing the package.

## Build

Build on WSL/Linux x86_64 after configuring the project-root `.env` for both
CSEs and installing the build requirements:

```bash
python3 -m venv packaging/monitoring/.venv
source packaging/monitoring/.venv/bin/activate
python -m pip install -r packaging/monitoring/requirements-build.txt
python packaging/monitoring/build_package.py
```

The build produces a package directory, `.tar.gz`, and SHA-256 file. This
package has only been declared for Linux x86_64; other platforms require
separate builds and tests.
