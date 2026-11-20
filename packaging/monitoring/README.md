# PinchGuard Monitoring Package — Computer B

**Linux x86_64 · TinyIoT IN-CSE + PinchGuard Dashboard**  
[Project overview and two-node installation](https://github.com/seungwon20/oneM2M-project/blob/main/in-cse-dashboard/README.md) · [Release downloads](https://github.com/seungwon20/oneM2M-project/releases/tag/v0.1.0-hackathon)

This README is copied into the Monitoring package by [the source package builder](https://github.com/seungwon20/oneM2M-project//blob/main/in-cse-dashboard/packaging/monitoring/build_package.py). The bundle contains the native TinyIoT IN-CSE, the packaged Dashboard backend/frontend, configuration metadata, and command-line service control. **Computer A must run the companion MEC package**; this archive does not include an MN-CSE.

## Package layout

```text
Monitoring-Package-Linux-x86_64/
├── bin/dashboard/             # Bundled Dashboard runtime and web assets
├── bin/monitor-control/       # CLI service controller
├── bin/tinyiot-in-cse         # Native Linux executable
├── config/.env.example
├── config/build-info.json
├── runtime/logs/
├── runtime/pid/
├── scripts/
│   ├── configure-monitoring
│   ├── start-monitoring
│   ├── status-monitoring
│   ├── healthcheck
│   └── stop-monitoring
└── README.md
```

The **release archive filename** is `Monitoring-Package-Linux-x86_64-final.tar.gz` but the **builder's package root** is `Monitoring-Package-Linux-x86_64/`. Inspect extracted archive paths before entering the package directory.

**Versioning:** A README inside an already published archive is a snapshot of the *release build*. Changes to the GitHub branch after the release do not silently update an existing `.tar.gz` file.

## First-time installation

```bash
./scripts/configure-monitoring
nano config/.env
```

`configure-monitoring` derives the remote MEC MN-CSE identity, Device1–6 Resource IDs and RVI from the packaged `build-info.json`, and refuses to overwrite an existing `config/.env`.

Set at least:

| Setting | Required value |
|:--|:--|
| `IN_CSE_SERVER_IP` | Computer B address reachable from Computer A and advertised in the IN-CSE POA |
| `IN_CSE_SERVER_PORT` | IN-CSE HTTP port (default `3001`) |
| `PG_IN_CSE_ORIGIN` | Dashboard originator permitted by both relevant CSE policies; this demo expects the paired MEC `AE_ID` |
| `PG_INGEST_KEY` | Random key with at least 16 characters |
| `PG_DASHBOARD_HOST` / `PG_DASHBOARD_PORT` | Dashboard listener (default `0.0.0.0:8000`) |
| `PG_IN_CSE_URL` | Local IN-CSE address, normally `http://127.0.0.1:3001` |

Do not modify the generated `PG_MN_CSE_ID` or `PG_MN_DEVICE1_RI` through `PG_MN_DEVICE6_RI` without a corresponding rebuilt matching MEC seed. Set `PG_IN_CSE_ORIGIN` **before the first IN-CSE startup**, as its initial access-control behavior uses that value. Keep `PG_ENABLE_DEMO=0` and `PG_DEMO_SEED=0` when demonstrating real CSE polling rather than local demo values.

**Pairing with MEC:** read the Monitoring package's `config/build-info.json`. On Computer A set `REMOTE_CSE_ID` and `REMOTE_CSE_NAME` to the advertised IN-CSE identity, `REMOTE_CSE_HOST` to Computer B's reachable address and `REMOTE_CSE_PORT` to its listener port. Conversely, Computer A must advertise a routable `TINYIOT_SERVER_IP` so IN-CSE can forward requests back to MN-CSE.

## Runtime commands

```bash
./scripts/start-monitoring
./scripts/status-monitoring
./scripts/healthcheck
```

Startup validates the configuration, starts IN-CSE and checks its CSEBase, then starts the Dashboard and checks `/health`. **Local health alone does not prove remote MN-CSE registration or telemetry freshness.**

Use the dashboard from a permitted browser at `http://<Computer-B-address>:8000`. Inspect the remote cache via:

```bash
curl -fsS http://127.0.0.1:8000/api/onem2m/devices
```

Look at individual device results, `connected` status and source freshness, not only the local dashboard `/health` response.

Shutdown:

```bash
./scripts/stop-monitoring
```

Logs and PID files are in `runtime/logs/` and `runtime/pid/`, and local dashboard SQLite state is under the configured `PG_DB_PATH`. **Back up `runtime/` before package updates.**

## Deployment and security limits

- The published release notes describe joint local **WSL loopback validation**, **not** tests across separate Computer A/B devices or a public network.
- Restrict CSE ports `3000`/`3001` and Dashboard port `8000` with LAN/VPN/firewall rules. The documented HTTP interfaces do not provide validated production TLS/mTLS.
- IN-CSE registration and Dashboard SP-relative forwarding require correct CSE IDs, advertised POAs, matching release metadata and originator privileges.
- No automatic CSE handover, service continuity guarantee, safety certification or real-world hazard-detection accuracy is claimed.
