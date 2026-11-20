# TinyIoT MN-CSE — Edge Resource Layer

**Component:** Computer A / MEC-oriented node  
**Project guide:** [PinchGuard](../README.md)

This directory is the actual TinyIoT C source root—not a wrapper containing another `tinyIoT/` subdirectory. In the integrated topology it operates as the **oneM2M Middle Node CSE**, hosting six predefined SDT-backed FlexContainers and registering to the Monitoring node's IN-CSE when configured.

## Relevant implementation

- [`sdt.c`](sdt.c) loads specialized definitions and validates custom FlexContainer attributes, types and required fields.
- [`resources/fcnt.c`](resources/fcnt.c) validates and updates the FlexContainer representation.
- [`sqlite_implement.c`](sqlite_implement.c) stores resource and custom-attribute state.
- [`main.c`](main.c) starts the Remote CSE registration worker and retries the configured IN-CSE registration when needed.
- [`scripts/build.py`](scripts/build.py) validates root `.env`, CSE identity and the six seed resource mappings before generating `config.h`/`Makefile` and invoking the build.
- [`scripts/run.py`](scripts/run.py) operates against a separate runtime directory.

The seed `MN-CSE/data.db` already contains CSEBase and Device1–6 resource definitions. **An empty DB does not automatically regenerate the six application FlexContainers.** First run copies seed state to `MN-CSE/runtime/data.db`; subsequent runs preserve the runtime DB.

## Source build and run (WSL / Linux)

From repository root, after configuring `.env`:

```bash
python3 MN-CSE/scripts/build.py
python3 MN-CSE/scripts/run.py
```

Use separate terminals for other services. Development dependencies include GCC, Make, pkg-config, OpenSSL headers and libwebsockets development files. `config.h` and `Makefile` are generated; do not edit or commit them as configuration sources.

## Network configuration

| Setting | Meaning |
|:--|:--|
| `CSE_BASE_URL` | Local AI-AE → MN-CSE HTTP origin; normally `http://127.0.0.1:3000` |
| `TINYIOT_SERVER_IP` | Advertised MN-CSE POA, reachable from Computer B |
| `TINYIOT_SERVER_PORT` | MN-CSE listener port, default `3000` |
| `REMOTE_CSE_ID`, `REMOTE_CSE_NAME` | Identity of the Monitoring IN-CSE |
| `REMOTE_CSE_HOST`, `REMOTE_CSE_PORT` | IN-CSE endpoint reachable from Computer A |

The HTTP listener binds to `0.0.0.0`; its **advertised POA** is a separate setting. Never advertise `127.0.0.1` as Computer A's address when Computer B is on another host.

The **release MEC package** uses `./scripts/configure-mec`, `./scripts/start-mec`, `./scripts/status-mec`, `./scripts/healthcheck`, `./scripts/stop-mec` instead of these source entry points. See [the consolidated installation guide](../README.md#configure-the-two-nodes).

## Security and validation

Resource identifiers and originators come from the source `.env`/seed mapping; they must match the intended access policies. Remote registration and request forwarding exist in the implementation, but passing the local build or unit tests does not prove independently validated LAN/firewall connectivity, least-privilege ACP policy or secure inter-node TLS deployment.
