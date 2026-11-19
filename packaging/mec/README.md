# MEC Package

This package contains the AI-AE service and TinyIoT MN-CSE for Linux x86_64. It does not
include a developer Python installation requirement; AI-AE and the package controller are
bundled with their Python runtime. The TinyIoT executable still requires its linked Linux
runtime libraries, including OpenSSL and libwebsockets.

## Initial configuration

After extraction, create the package-local configuration:

```bash
./scripts/configure-mec
```

Edit `config/.env` and set:

- `AE_ID`: the Originator accepted by this CSE
- `TINYIOT_SERVER_IP`: the MEC node's reachable LAN address advertised in the CSE POA
- `REMOTE_CSE_ID`, `REMOTE_CSE_NAME`, `REMOTE_CSE_HOST`, `REMOTE_CSE_PORT`: the matching
  IN-CSE identity and reachable Monitoring Node endpoint from the companion Monitoring Package

The configure command fills the CSE Base and Device1-Device6 Resource IDs from the bundled
seed database without printing them. The service-provider ID is included in build metadata
because the seed database does not store it. Keep the seed-derived values aligned with that
database. The AI-AE connects locally using `CSE_BASE_URL`; Dashboard clients must use the MEC
node's LAN address, not `127.0.0.1`.

## Service commands

```bash
./scripts/start-mec
./scripts/status-mec
./scripts/healthcheck
./scripts/stop-mec
```

Startup validates configuration, initializes `runtime/data.db` only if it does not exist,
starts MN-CSE, waits for a successful CSE Base response, then starts AI-AE and checks its
`/health` endpoint. Logs and PID files are stored under `runtime/`. Stop signals are sent to
the recorded package processes; unrelated processes are not signalled.

## Database and updates

`data/seed.db` and `share/sdt_definitions/` are package inputs. First start copies the seed to
`runtime/data.db`; subsequent starts preserve the runtime database. Back up `runtime/` before
upgrading the package.

The current package is built for Linux x86_64 only. The complementary Monitoring Package contains
TinyIoT IN-CSE and the integrated PinchGuard Dashboard; build and two-node deployment status are
described in the repository's packaging and deployment guides.
