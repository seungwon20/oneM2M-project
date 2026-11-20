# TinyIoT IN-CSE — Monitoring-Side Routing Layer

**Component:** Computer B / Monitoring node  
**Project guide:** [PinchGuard](../README.md)

The Infrastructure Node CSE accepts configured remote MN-CSE registration, maintains its routing information, and forwards a Dashboard-initiated oneM2M **SP-relative GET** to the remote MN-CSE's advertised POA.

The intended path is **Dashboard backend → local IN-CSE → registered remote MN-CSE**. The Dashboard's browser UI itself does not directly retrieve each MEC resource.

## Source development

The package `IN-CSE/` contains the TinyIoT source, its CSE configuration scripts and runtime support. For standalone developer builds use a correctly prepared project-root `.env`, including `IN_CSE_SERVER_IP`, `IN_CSE_SERVER_PORT`, IN-CSE Base identity and RVI, and the allowed remote MN-CSE identifier.

From the **repository root**:

```bash
python3 IN-CSE/scripts/build.py
python3 IN-CSE/scripts/run.py
```

The source build reads configuration and produces a native binary; the runner uses an independent runtime directory. The IN-CSE can start before the MEC becomes reachable; that does **not** imply remote resource retrieval can succeed before registration and routing are available.

## Release configuration

For actual published binary packages, use the Monitoring package's own scripts:

```bash
./scripts/configure-monitoring
./scripts/start-monitoring
./scripts/status-monitoring
./scripts/healthcheck
./scripts/stop-monitoring
```

Run these from the extracted `Monitoring-Package-Linux-x86_64/` root—not the `IN-CSE/` source directory. Set the Monitoring host's reachable `IN_CSE_SERVER_IP`, and match the dashboard originator and the allowlisted MN-CSE identity to the paired MEC package. The default local IN-CSE port is `3001`. `PG_IN_CSE_URL=http://127.0.0.1:3001` is valid when Dashboard and IN-CSE share Computer B.

## Validation limits

The integration branch contains registration/forwarding code, and the release notes report local WSL/loopback testing. The ability to route a request across two **separate** computers, firewall and POA correctness, production ACP and TLS security and CSE failover must be demonstrated separately.

**Source entries:** [`scripts/build.py`](scripts/build.py) · [`scripts/run.py`](scripts/run.py) · [`main.c`](main.c).
