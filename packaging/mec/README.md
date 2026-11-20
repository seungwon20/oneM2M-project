# PinchGuard MEC Package — Computer A

**Linux x86_64 · FastAPI AI-AE + TinyIoT MN-CSE**  
[Project overview and two-node installation](https://github.com/seungwon20/oneM2M-project/blob/main/README.md) · [Release downloads](https://github.com/seungwon20/oneM2M-project/releases/tag/v0.1.0-hackathon)

This is the **source README copied into the MEC package by the builder**. The bundle includes the AI-AE runtime and trained synthetic-data model, a native TinyIoT MN-CSE executable, the seed database, SDT definitions, configuration metadata, and scripts for configuration, health checks, service start and stop. It does **not** include the Monitoring node or the optional source-only Mock PLC.

## Package layout

```text
MEC-Package-Linux-x86_64/
├── bin/ai-ae/                 # Bundled FastAPI runtime
├── bin/mec-control/           # CLI service controller
├── bin/tinyiot-mn-cse         # Native Linux executable
├── config/.env.example
├── config/build-info.json
├── data/seed.db
├── models/risk_model.joblib
├── share/sdt_definitions/
├── runtime/logs/              # Runtime output
├── runtime/pid/
├── scripts/
│   ├── configure-mec
│   ├── start-mec
│   ├── status-mec
│   ├── healthcheck
│   └── stop-mec
└── README.md
```

## First-time installation

From the extracted package directory:

```bash
./scripts/configure-mec
nano config/.env
```

`configure-mec` derives the CSE and **six Resource IDs** from the bundled seed and generates `config/.env` without overwriting an existing file. Complete the user-specific settings:

| Setting | Required value |
|:--|:--|
| `AE_ID` | Originator accepted by the CSE; match the paired Monitoring `PG_IN_CSE_ORIGIN` for this demo |
| `TINYIOT_SERVER_IP` | Computer A address reachable from Computer B, advertised in the MN-CSE POA |
| `REMOTE_CSE_ID` | IN-CSE identifier in the paired Monitoring `config/build-info.json` |
| `REMOTE_CSE_NAME` | Corresponding IN-CSE base name |
| `REMOTE_CSE_HOST` | Monitoring node's reachable hostname/IP, without scheme or port |
| `REMOTE_CSE_PORT` | IN-CSE port, normally `3001` |

The localhost `CSE_BASE_URL` connects **AI-AE to MN-CSE inside Computer A**. It is not the address of Computer B and should not be replaced with the remote node address. Do not change seed-derived Resource IDs, base identity or RVI without regenerating a compatible pair of packages.

**Recommended order:** configure and start the Monitoring node first, then configure/start MEC. The MN-CSE includes a retry worker for temporarily unavailable IN-CSE registration.

## Runtime commands

```bash
./scripts/start-mec
./scripts/status-mec
./scripts/healthcheck
```

Startup validates configuration and seed mappings, initializes `runtime/data.db` on first run only, launches MN-CSE and waits for a healthy CSE Base, then starts AI-AE and checks `/health`.

Shutdown:

```bash
./scripts/stop-mec
```

**Readiness ≠ remote connectivity.** These commands establish local process and endpoint readiness, not an independently verified IN-CSE routing path or safety system.

Logs and PID files reside under `runtime/logs/` and `runtime/pid/`. Back up `runtime/` before upgrading. Subsequent starts **preserve** the existing runtime database. The native executable may still need compatible OpenSSL/libwebsockets runtime libraries on the target Linux host.

## Verification boundary

Published `v0.1.0-hackathon` release notes report joint local **WSL loopback testing**, not fresh-host deployment, two-computer LAN or firewall testing. An operational ETSI MEC platform and production-grade authentication/TLS are outside this demonstrated scope. Do not interpret an optional Mock PLC STOP as physical actuation.
